"""Implied variance from the OptionMetrics surface: the surface pulls, the surface-based
model-free construction of spec section 6.1 as amended by A1 in section 13, the two
synthetic checks on it, the SPX validation against item 1's strike-ladder series, and
the at-the-money measure of section 6.2.

Construction choices sections 6.1 and 13 leave open, fixed before the construction ran
on any real surface. The forward is the one the 50-delta call and the minus-50-delta put
imply under a Black-Scholes forward delta, where N(d1) = 1/2 puts the strike at
F exp(σ²T/2); it is averaged in logs over the two legs, which also cancels the
first-order effect of a dividend discount in a spot delta. T is d/365. The zero rate is
item 1's linear interpolation in days, falling back to the nearest earlier curve date.
Nodes that share a strike enter the interpolation once, at their mean volatility. On
each side the grid ends at F exp(±10 σ_edge √T), or at the last point of a 64-point
geometric scan outward from the outermost node where the out-of-the-money price at the
edge volatility is still at least 1e-10 F, whichever is nearer; between the two ends it
has exactly 1,000 strikes spaced evenly in log strike. K0 is the highest grid strike at
or below the forward. Grid strikes below K0 are priced as puts and above as calls at
their interpolated volatility, K0 takes the mean of the two, and item 1's sum runs over
the grid. Black-Scholes prices come from item 1's function with spot F e^{-rT}, which is
the Black price on the forward.
"""

from __future__ import annotations

import logging
import time
from math import exp, sqrt
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import wrds
from scipy.special import ndtri

from options_series.db import copy_query_to_csv, query
from options_series.item1.model_free_variance import (
    atm_implied_variance,
    black_scholes_price,
    model_free_sum,
    zero_rate,
)
from options_series.item2.config import (
    ATM_DELTA,
    CALENDAR_DAYS_PER_YEAR,
    CALL_DELTAS,
    ITEM1_LADDER_PATH,
    NODES,
    PULL_TIME_LIMIT_MINUTES,
    PUT_DELTAS,
    RAW_DIR,
    RESTRICTED_START,
    SAMPLE_START,
    SKEW_CALL_VOLATILITY,
    SKEW_PUT_VOLATILITY,
    SKEW_REFERENCE_POINTS,
    SPX_SECID,
    SURFACE_DIR,
    SURFACE_GRID_POINTS,
    SYNTHETIC_TOLERANCE,
    TAIL_PRICE_FLOOR,
    TAIL_STANDARD_DEVIATIONS,
    VALIDATION_GAP_THRESHOLD,
    VALIDATION_MIN_CORRELATION,
)
from options_series.item2.membership import year_bounds

LOGGER = logging.getLogger(__name__)

OK = "OK"
NO_SURFACE_ROWS = "NO_SURFACE_ROWS"
MISSING_NODE = "MISSING_NODE"
NULL_VOLATILITY = "NULL_VOLATILITY"
BAD_NODE = "BAD_NODE"
BAD_VARIANCE = "BAD_VARIANCE"

ZERO_CURVE_PATH = RAW_DIR / "zero_curve.parquet"
SURFACE_COLUMNS = "secid, date, days, delta, cp_flag, impl_volatility, impl_strike"
SURFACE_SCHEMA = {
    "secid": pa.int32(),
    "date": pa.date32(),
    "days": pa.int16(),
    "delta": pa.int16(),
    "cp_flag": pa.string(),
    "impl_volatility": pa.float64(),
    "impl_strike": pa.float64(),
}
# Node order used everywhere: the 17 calls from delta 10 to 90, then the 17 puts from
# delta -10 to -90. A put of delta -D sits where a call of delta 1 - D does.
NODE_DELTAS = np.array(CALL_DELTAS + PUT_DELTAS)
NODE_COUNT = len(NODE_DELTAS)
NODE_CALL_DELTAS = np.where(NODE_DELTAS > 0, NODE_DELTAS, 100 + NODE_DELTAS) / 100.0
ATM_PAIR = [
    int(np.flatnonzero(NODE_DELTAS == ATM_DELTA)[0]),
    int(np.flatnonzero(NODE_DELTAS == -ATM_DELTA)[0]),
]
TAIL_SCAN_POINTS = 64
CHECK_FORWARD = 100.0
CHECK_RATE = 0.02
FLAT_CHECK_VOLATILITY = 0.20


class SurfaceVariance(NamedTuple):
    """Annualised surface-based variance at one maturity, the forward behind it and the
    drop code, OK when the variance is valid."""

    variance: float
    forward: float
    drop_code: str


def _node_curve(strikes: np.ndarray, vols: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Node strikes in ascending order with their volatilities, nodes that share a strike
    entering once at their mean volatility."""
    unique, inverse = np.unique(strikes, return_inverse=True)
    return unique, np.bincount(inverse, weights=vols) / np.bincount(inverse)


def _tail_end(
    forward: float,
    years: float,
    rate: float,
    edge_strike: float,
    edge_vol: float,
    cp_flag: str,
) -> float:
    """Outer end of the strike grid on one side under amendment A1: F exp(∓10 σ_edge √T),
    or nearer where the out-of-the-money price at the edge volatility falls below the
    price floor, and never inside the outermost node."""
    reach = TAIL_STANDARD_DEVIATIONS * edge_vol * sqrt(years)
    if cp_flag == "P":
        limit = min(forward * exp(-reach), edge_strike)
    else:
        limit = max(forward * exp(reach), edge_strike)
    scan = np.geomspace(edge_strike, limit, TAIL_SCAN_POINTS)
    spot = forward * exp(-rate * years)
    prices = black_scholes_price(spot, scan, years, rate, edge_vol, cp_flag)
    below = np.flatnonzero(prices < TAIL_PRICE_FLOOR * forward)
    if not len(below):
        return float(limit)
    return float(scan[max(below[0] - 1, 0)])


def _strike_grid(
    forward: float,
    years: float,
    rate: float,
    node_strikes: np.ndarray,
    node_vols: np.ndarray,
    points: int,
) -> np.ndarray:
    """Strikes spaced evenly in log strike between the two tail ends of amendment A1."""
    low = _tail_end(forward, years, rate, node_strikes[0], node_vols[0], "P")
    high = _tail_end(forward, years, rate, node_strikes[-1], node_vols[-1], "C")
    return np.exp(np.linspace(np.log(low), np.log(high), points))


def grid_variance(
    strikes: np.ndarray, vols: np.ndarray, forward: float, years: float, rate: float
) -> float:
    """Model-free variance from volatilities on an ascending strike grid around the
    forward: out-of-the-money Black prices at each strike's own volatility, the mean of
    call and put at K0, and item 1's sum."""
    atm_index = int(np.searchsorted(strikes, forward, side="right")) - 1
    if atm_index < 0 or atm_index == len(strikes) - 1:
        return np.nan
    spot = forward * exp(-rate * years)
    puts = black_scholes_price(
        spot, strikes[: atm_index + 1], years, rate, vols[: atm_index + 1], "P"
    )
    calls = black_scholes_price(
        spot, strikes[atm_index:], years, rate, vols[atm_index:], "C"
    )
    prices = np.concatenate([puts[:-1], [0.5 * (puts[-1] + calls[0])], calls[1:]])
    return model_free_sum(
        strikes, prices, forward, float(strikes[atm_index]), years, rate
    )


def surface_variance(
    vols: np.ndarray, strikes: np.ndarray, days: int, rate: float
) -> SurfaceVariance:
    """Model-free variance from one secid-date's 34 surface nodes at one maturity (spec
    section 6.1 as amended by A1), nodes in NODE_DELTAS order with a missing node as NaN
    in both arrays."""
    if np.isnan(strikes).any():
        return SurfaceVariance(np.nan, np.nan, MISSING_NODE)
    if np.isnan(vols).any():
        return SurfaceVariance(np.nan, np.nan, NULL_VOLATILITY)
    if (vols <= 0).any() or (strikes <= 0).any():
        return SurfaceVariance(np.nan, np.nan, BAD_NODE)
    years = days / CALENDAR_DAYS_PER_YEAR
    forward = float(
        np.exp(np.mean(np.log(strikes[ATM_PAIR]) - 0.5 * vols[ATM_PAIR] ** 2 * years))
    )
    node_strikes, node_vols = _node_curve(strikes, vols)
    grid = _strike_grid(
        forward, years, rate, node_strikes, node_vols, SURFACE_GRID_POINTS
    )
    variance = grid_variance(
        grid, np.interp(grid, node_strikes, node_vols), forward, years, rate
    )
    if not np.isfinite(variance) or variance <= 0:
        return SurfaceVariance(np.nan, forward, BAD_VARIANCE)
    return SurfaceVariance(variance, forward, OK)


def delta_strikes(
    call_deltas: np.ndarray, vols: np.ndarray, years: float, forward: float
) -> np.ndarray:
    """Strikes at call-equivalent deltas under the Black-Scholes forward delta, d1 = N⁻¹(D),
    each at its own volatility."""
    root = vols * np.sqrt(years)
    return forward * np.exp(0.5 * root**2 - root * ndtri(call_deltas))


def _skewed_volatility(call_deltas: np.ndarray) -> np.ndarray:
    """The skewed check's volatility, linear in call-equivalent delta from its put value
    at the 10-delta put, call delta 0.90, to its call value at the 10-delta call."""
    share = (call_deltas - 0.10) / 0.80
    return SKEW_CALL_VOLATILITY + (SKEW_PUT_VOLATILITY - SKEW_CALL_VOLATILITY) * share


def _skewed_volatility_at(strikes: np.ndarray, years: float) -> np.ndarray:
    """The skewed check's volatility at each strike from the delta function itself, by
    bisection on delta, flat beyond the 10-delta strikes."""
    low = np.full(len(strikes), 0.10)
    high = np.full(len(strikes), 0.90)
    for _ in range(60):
        middle = 0.5 * (low + high)
        strike_at_middle = delta_strikes(
            middle, _skewed_volatility(middle), years, CHECK_FORWARD
        )
        above = strike_at_middle > strikes
        low = np.where(above, middle, low)
        high = np.where(above, high, middle)
    return _skewed_volatility(0.5 * (low + high))


def check_flat_surface(
    vol: float = FLAT_CHECK_VOLATILITY, rate: float = CHECK_RATE
) -> pd.DataFrame:
    """Session check: 34 nodes at one volatility must return that volatility squared
    within the synthetic tolerance at both maturities."""
    rows = []
    for days in NODES:
        years = days / CALENDAR_DAYS_PER_YEAR
        vols = np.full(NODE_COUNT, vol)
        strikes = delta_strikes(NODE_CALL_DELTAS, vols, years, CHECK_FORWARD)
        result = surface_variance(vols, strikes, days, rate)
        recovered = result.variance / vol**2
        rows.append(
            {
                "days": days,
                "volatility": vol,
                "target_variance": vol**2,
                "variance": result.variance,
                "recovered_fraction": recovered,
                "drop_code": result.drop_code,
                "passed": bool(
                    result.drop_code == OK
                    and abs(recovered - 1.0) <= SYNTHETIC_TOLERANCE
                ),
            }
        )
    return pd.DataFrame(rows)


def check_skewed_surface(rate: float = CHECK_RATE) -> pd.DataFrame:
    """Session check: on a surface whose volatility is linear in delta between the 10-delta
    put and call, the 34-node measure must match the same integrand on a reference grid
    whose volatilities come from the delta function itself, within the synthetic
    tolerance at both maturities."""
    rows = []
    for days in NODES:
        years = days / CALENDAR_DAYS_PER_YEAR
        vols = _skewed_volatility(NODE_CALL_DELTAS)
        strikes = delta_strikes(NODE_CALL_DELTAS, vols, years, CHECK_FORWARD)
        measure = surface_variance(vols, strikes, days, rate)
        node_strikes, node_vols = _node_curve(strikes, vols)
        grid = _strike_grid(
            measure.forward, years, rate, node_strikes, node_vols, SKEW_REFERENCE_POINTS
        )
        reference = grid_variance(
            grid, _skewed_volatility_at(grid, years), measure.forward, years, rate
        )
        gap = measure.variance / reference - 1.0
        rows.append(
            {
                "days": days,
                "put_volatility": SKEW_PUT_VOLATILITY,
                "call_volatility": SKEW_CALL_VOLATILITY,
                "variance": measure.variance,
                "reference_variance": reference,
                "reference_points": SKEW_REFERENCE_POINTS,
                "relative_gap": gap,
                "drop_code": measure.drop_code,
                "passed": bool(
                    measure.drop_code == OK and abs(gap) <= SYNTHETIC_TOLERANCE
                ),
            }
        )
    return pd.DataFrame(rows)


def surface_path(year: int) -> Path:
    """Parquet path of one year partition of the surface pull."""
    return SURFACE_DIR / f"surface_{year}.parquet"


def pull_surface_year(
    connection: wrds.Connection, year: int, secids: np.ndarray
) -> int:
    """Every delta node at both maturities for one year's constituent secids and SPX,
    streamed to CSV and written as parquet; returns the row count."""
    SURFACE_DIR.mkdir(parents=True, exist_ok=True)
    start, end = year_bounds(year)
    secid_list = tuple(float(secid) for secid in sorted({*map(int, secids), SPX_SECID}))
    csv_path = SURFACE_DIR / f"surface_{year}.csv"
    copy_query_to_csv(
        connection,
        f"select {SURFACE_COLUMNS} from optionm.vsurfd{year} "
        "where secid in %(secids)s and date between %(start)s and %(end)s "
        f"and days in {tuple(NODES)}",
        {"secids": secid_list, "start": start, "end": end},
        csv_path,
    )
    table = pacsv.read_csv(
        csv_path,
        convert_options=pacsv.ConvertOptions(column_types=SURFACE_SCHEMA),
    )
    table = table.set_column(
        table.schema.get_field_index("date"),
        "date",
        table["date"].cast(pa.timestamp("ns")),
    )
    pq.write_table(table, surface_path(year), compression="zstd")
    csv_path.unlink()
    return table.num_rows


def pull_surfaces(
    connection: wrds.Connection, secids_by_year: dict[int, np.ndarray]
) -> tuple[pd.DataFrame, str]:
    """Pull every year partition, newest first, under stop rule 9.3: once the running
    wall clock passes the limit, years before the restricted start are not pulled.
    Returns the pull log and the sample start that applies."""
    log, elapsed, sample_start = [], 0.0, SAMPLE_START
    for year in sorted(secids_by_year, reverse=True):
        if sample_start == RESTRICTED_START and year < int(RESTRICTED_START[:4]):
            break
        started = time.time()
        rows = pull_surface_year(connection, year, secids_by_year[year])
        seconds = time.time() - started
        elapsed += seconds
        log.append(
            {
                "year": year,
                "secids": len(secids_by_year[year]) + 1,
                "rows": rows,
                "seconds": seconds,
                "running_minutes": elapsed / 60.0,
            }
        )
        LOGGER.info(
            "surface %d: %d rows in %.1f s, running total %.1f min",
            year,
            rows,
            seconds,
            elapsed / 60.0,
        )
        if (
            elapsed / 60.0 > PULL_TIME_LIMIT_MINUTES
            and sample_start != RESTRICTED_START
        ):
            sample_start = RESTRICTED_START
            LOGGER.info(
                "stop rule 9.3: sample restricted to %s onward", RESTRICTED_START
            )
    return pd.DataFrame(log), sample_start


def pull_zero_curve(connection: wrds.Connection) -> pd.DataFrame:
    """OptionMetrics zero curve in full: rate in percent per annum by date and days."""
    curve = query(connection, "select date, days, rate from optionm.zerocd")
    curve["date"] = pd.to_datetime(curve["date"])
    curve["days"] = pd.to_numeric(curve["days"]).astype(float)
    curve["rate"] = pd.to_numeric(curve["rate"]).astype(float)
    return curve.sort_values(["date", "days"]).reset_index(drop=True)


def load_surface_year(year: int) -> pd.DataFrame:
    """One year partition of the surface from disk, the option type as a category."""
    return pq.read_table(surface_path(year)).to_pandas(strings_to_categorical=True)


def node_arrays(surface: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """The surface reshaped to one row per secid, date and maturity, with volatility and
    strike arrays in NODE_DELTAS order and NaN for an absent node."""
    grouped = surface.groupby(["secid", "date", "days"], sort=True, observed=True)
    keys = grouped.size().index.to_frame(index=False)
    row = grouped.ngroup().values
    position = pd.Series(np.arange(NODE_COUNT), index=NODE_DELTAS)
    column = position.reindex(surface.delta.values).values
    known = ~np.isnan(column)
    vols = np.full((len(keys), NODE_COUNT), np.nan)
    strikes = np.full((len(keys), NODE_COUNT), np.nan)
    vols[row[known], column[known].astype(int)] = surface.impl_volatility.values[known]
    strikes[row[known], column[known].astype(int)] = surface.impl_strike.values[known]
    # A node whose row is absent or whose strike is null drops as missing; a node with a
    # strike and a null volatility drops as a null volatility.
    return keys, vols, strikes


class ZeroCurve:
    """Zero rate lookup with item 1's fallback to the nearest earlier curve date."""

    def __init__(self, curve: pd.DataFrame) -> None:
        self.curves = {
            date: (group.days.values, group.rate.values)
            for date, group in curve.groupby("date", sort=True)
        }
        self.dates = np.array(sorted(self.curves), dtype="datetime64[ns]")

    def rate(self, date: pd.Timestamp, days: float) -> float:
        """Zero rate as a decimal per annum on date for days to maturity."""
        key = np.datetime64(date, "ns")
        index = np.searchsorted(self.dates, key, side="right") - 1
        if index < 0:
            raise ValueError(f"no zero curve on or before {pd.Timestamp(date).date()}")
        curve_days, curve_rates = self.curves[pd.Timestamp(self.dates[index])]
        return zero_rate(curve_days, curve_rates, days)


def surface_variance_for_year(
    year: int, curve: pd.DataFrame, keep: pd.DataFrame
) -> pd.DataFrame:
    """Surface-based variance and drop code for the secid-dates in keep within one year
    partition, at both maturities."""
    surface = load_surface_year(year).merge(
        keep[["secid", "date"]].drop_duplicates(), on=["secid", "date"]
    )
    keys, vols, strikes = node_arrays(surface)
    zero_curve = ZeroCurve(curve[curve.date.dt.year.isin([year - 1, year])])
    rates = {
        (date, days): zero_curve.rate(date, days)
        for date, days in keys[["date", "days"]]
        .drop_duplicates()
        .itertuples(index=False)
    }
    variances = np.full(len(keys), np.nan)
    forwards = np.full(len(keys), np.nan)
    codes = np.empty(len(keys), dtype=object)
    for index, (date, days) in enumerate(zip(keys.date, keys.days)):
        result = surface_variance(
            vols[index], strikes[index], int(days), rates[(date, days)]
        )
        variances[index], forwards[index], codes[index] = result
    return keys.rename(columns={"days": "node"}).assign(
        implied_var=variances, forward=forwards, drop_code=codes
    )


def atm_variance(surface: pd.DataFrame) -> pd.DataFrame:
    """At-the-money variance per secid, date and maturity with item 1's construction."""
    at_the_money = surface[
        ((surface.delta == ATM_DELTA) & (surface.cp_flag == "C"))
        | ((surface.delta == -ATM_DELTA) & (surface.cp_flag == "P"))
    ]
    wide = at_the_money.pivot_table(
        index=["secid", "date", "days"],
        columns="cp_flag",
        values="impl_volatility",
        aggfunc="first",
        dropna=False,
        observed=True,
    ).reset_index()
    wide = wide.rename(columns={"days": "node", "C": "iv_call_50", "P": "iv_put_50"})
    wide = atm_implied_variance(wide)
    return wide[["secid", "date", "node", "implied_var_atm"]]


def load_ladder_series() -> pd.DataFrame:
    """Item 1's SPX strike-ladder model-free variance at its primary strike floor."""
    from options_series.item1.config import COMMON_END, COMMON_START, STRIKE_FLOOR
    from options_series.item1.model_free_variance import OK as LADDER_OK

    ladder = pd.read_parquet(ITEM1_LADDER_PATH)
    ladder = ladder[
        (ladder.ticker == "SPX")
        & (ladder.strike_floor == STRIKE_FLOOR)
        & (ladder.drop_code == LADDER_OK)
        & (ladder.date >= COMMON_START)
        & (ladder.date <= COMMON_END)
    ]
    return ladder[["date", "node", "implied_var"]].rename(
        columns={"implied_var": "ladder_var"}
    )


def validate_against_ladder(
    spx: pd.DataFrame, ladder: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Section 6.1 validation per maturity: correlation of variance levels, mean and
    median gap in variance points and in log units, and the share of dates where the
    surface variance differs from the ladder variance by more than the threshold."""
    merged = (
        spx[spx.drop_code == OK][["date", "node", "implied_var"]]
        .rename(columns={"implied_var": "surface_var"})
        .merge(ladder, on=["date", "node"])
    )
    merged["gap"] = merged.surface_var - merged.ladder_var
    merged["log_gap"] = np.log(merged.surface_var / merged.ladder_var)
    rows = []
    for node, group in merged.groupby("node"):
        correlation = float(np.corrcoef(group.surface_var, group.ladder_var)[0, 1])
        rows.append(
            {
                "node": int(node),
                "dates": len(group),
                "first_date": group.date.min(),
                "last_date": group.date.max(),
                "correlation": correlation,
                "mean_gap": float(group.gap.mean()),
                "median_gap": float(group.gap.median()),
                "mean_log_gap": float(group.log_gap.mean()),
                "median_log_gap": float(group.log_gap.median()),
                "share_beyond_threshold": float(
                    (
                        np.abs(group.surface_var / group.ladder_var - 1.0)
                        > VALIDATION_GAP_THRESHOLD
                    ).mean()
                ),
                "passed": correlation >= VALIDATION_MIN_CORRELATION,
            }
        )
    return pd.DataFrame(rows), merged


def drop_counts(variance: pd.DataFrame) -> pd.DataFrame:
    """Rows per year, maturity and drop code."""
    return (
        variance.assign(year=variance.date.dt.year)
        .groupby(["year", "node", "drop_code"], observed=True)
        .size()
        .rename("rows")
        .reset_index()
    )
