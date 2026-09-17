"""Realized variance and the premiums (spec sections 6.3 and 6.4), their equal- and
value-weighted averages and the index-minus-average gap, implied and realized
correlation (6.5), the decomposition of the gap (6.6), the annual cross-section of
single-name premia (6.7), and the daily panel and non-overlapping grid the tests use.

Choices sections 6.4 to 6.7 leave open, fixed before any premium was computed.
- Returns sit on the SPX trade calendar before realized variance, so a trade date with
  no price record for a secid counts as a missing return and drops its windows. A
  return at or below -100 percent has no log return and counts as missing too.
- A name enters an average on a date when it is a constituent with a finite log ratio
  on that measure. The floors of section 5 count constituents with a valid implied
  variance on the primary measure, the surface-based one unless stop rule 9.2 moves the
  primary to ATM, and the other measure is reported on the same dates.
- A secid resolved for two member permnos on one date enters once, weighted by the
  permnos' combined previous-day market capitalisation.
- Implied and realized correlation run over the same names: constituents with the
  implied variance on that measure, a realized variance over the following window and
  a previous-day market capitalisation, weights renormalised over those names.
- A name's annual premium is the mean of its daily premium over the year's dates that
  clear the average floor; deciles and the share above the index are taken across names
  against the index's mean premium over the same dates.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import wrds

from options_series.db import query
from options_series.item1.config import STRIKE_FLOOR as ITEM1_STRIKE_FLOOR
from options_series.item1.realized_variance import realized_variance, variance_premium
from options_series.item2.config import (
    AVERAGE_FLOOR,
    CORRELATION_FLOOR,
    DATA_DIR,
    NODES,
    PERIODS,
    RAW_DIR,
    SAMPLE_END,
    SPX_SECID,
    WINDOW_TRADING_DAYS,
)
from options_series.item2.membership import sample_years, year_bounds

LOGGER = logging.getLogger(__name__)

RETURNS_DIR = RAW_DIR / "returns"
DAILY_PANEL_PATH = DATA_DIR / "daily_panel.parquet"
GRID_PANEL_PATH = DATA_DIR / "grid_panel.parquet"
NAME_PREMIUM_PATH = DATA_DIR / "name_premium.parquet"
MEASURES = ("surface", "atm")
LOG_RATIO = {"surface": "log_ratio_model_free", "atm": "log_ratio_atm"}
IMPLIED_VAR = {"surface": "implied_var_model_free", "atm": "implied_var_atm"}
RETURN_CHUNK_SECIDS = 250


def pull_returns(connection: wrds.Connection, secids: np.ndarray) -> None:
    """Daily return for every given secid and SPX, one year partition per file."""
    RETURNS_DIR.mkdir(parents=True, exist_ok=True)
    secid_list = tuple(float(secid) for secid in sorted({*map(int, secids), SPX_SECID}))
    for year in sample_years():
        start, end = year_bounds(year)
        rows = query(
            connection,
            f"select secid, date, return from optionm.secprd{year} "
            "where secid in %(secids)s and date between %(start)s and %(end)s",
            {"secids": secid_list, "start": start, "end": end},
        )
        rows["secid"] = rows["secid"].astype("int64")
        rows["date"] = pd.to_datetime(rows["date"])
        rows["return"] = pd.to_numeric(rows["return"]).astype(float)
        rows.to_parquet(RETURNS_DIR / f"returns_{year}.parquet", index=False)
        LOGGER.info("returns %d: %d rows", year, len(rows))


def load_returns() -> pd.DataFrame:
    """Daily returns for every pulled secid from disk."""
    return pd.concat(
        [pd.read_parquet(path) for path in sorted(RETURNS_DIR.glob("*.parquet"))],
        ignore_index=True,
    )


def calendar_returns(
    returns: pd.DataFrame, trade_dates: pd.DatetimeIndex
) -> pd.DataFrame:
    """Each secid's returns on the trade calendar from its first to its last record,
    with NaN on a trade date that has no record."""
    returns = returns[returns.date.isin(trade_dates)].drop_duplicates(["secid", "date"])
    returns = returns.assign(
        **{"return": returns["return"].where(returns["return"] > -1)}
    )
    dates = np.asarray(trade_dates, dtype="datetime64[ns]")
    spans = returns.groupby("secid").date.agg(["min", "max"])
    first = np.searchsorted(dates, spans["min"].values)
    last = np.searchsorted(dates, spans["max"].values)
    lengths = last - first + 1
    positions = np.concatenate(
        [np.arange(start, end + 1) for start, end in zip(first, last)]
    )
    calendar = pd.DataFrame(
        {"secid": np.repeat(spans.index.values, lengths), "date": dates[positions]}
    )
    return calendar.merge(returns, on=["secid", "date"], how="left")


def realized_variances(
    returns: pd.DataFrame, trade_dates: pd.DatetimeIndex, keep: pd.DataFrame
) -> pd.DataFrame:
    """Realized variance at both windows with item 1's function, for the secid-dates in
    keep, computed in chunks of secids."""
    on_calendar = calendar_returns(returns, trade_dates)
    secids = on_calendar.secid.unique()
    wanted = keep[["secid", "date"]].drop_duplicates()
    frames = []
    for start in range(0, len(secids), RETURN_CHUNK_SECIDS):
        chunk = on_calendar[
            on_calendar.secid.isin(secids[start : start + RETURN_CHUNK_SECIDS])
        ]
        realized = realized_variance(chunk.rename(columns={"secid": "ticker"}))
        realized = realized.rename(columns={"ticker": "secid"}).merge(
            wanted, on=["secid", "date"]
        )
        frames.append(realized)
    return pd.concat(frames, ignore_index=True)


def member_secids(constituents: pd.DataFrame, market_cap: pd.DataFrame) -> pd.DataFrame:
    """Constituents collapsed to one row per date and secid with the combined
    previous-day market capitalisation of the permnos resolved to it, missing when any
    of those permnos lacks a positive one."""
    mapped = constituents.dropna(subset=["secid"]).merge(
        market_cap[["permno", "date", "previous_market_cap"]],
        on=["permno", "date"],
        how="left",
    )
    mapped["secid"] = mapped["secid"].astype("int64")
    mapped["previous_market_cap"] = mapped.previous_market_cap.where(
        mapped.previous_market_cap > 0
    )
    grouped = mapped.groupby(["date", "secid"])
    collapsed = grouped.agg(
        permnos=("permno", "size"),
        capped=("previous_market_cap", "count"),
        previous_market_cap=("previous_market_cap", "sum"),
    ).reset_index()
    collapsed["previous_market_cap"] = collapsed.previous_market_cap.where(
        collapsed.capped == collapsed.permnos
    )
    return collapsed.drop(columns="capped")


def premiums(
    surface: pd.DataFrame, atm: pd.DataFrame, realized: pd.DataFrame
) -> pd.DataFrame:
    """Log ratio and variance difference on both implied measures per secid, date and
    maturity, through item 1's premium function."""
    model_free = surface.assign(ticker=surface.secid, strike_floor=ITEM1_STRIKE_FLOOR)
    premium = variance_premium(
        model_free,
        atm.assign(ticker=atm.secid),
        realized.assign(ticker=realized.secid),
    )
    return premium.drop(columns=["ticker"])


def _weighted_sums(frame: pd.DataFrame, value: str, weight: str) -> pd.DataFrame:
    """Per date and maturity: count, mean, weight sum and weighted mean of value over rows
    with a finite value, the weighted mean over rows that also carry a weight."""
    rows = frame[np.isfinite(frame[value])]
    weighted = rows[rows[weight] > 0]
    counts = rows.groupby(["date", "node"])[value].agg(["size", "mean"])
    weighted_mean = (weighted[value] * weighted[weight]).groupby(
        [weighted.date, weighted.node]
    ).sum() / weighted[weight].groupby([weighted.date, weighted.node]).sum()
    return counts.assign(weighted_mean=weighted_mean)


def daily_averages(
    names: pd.DataFrame, index: pd.DataFrame, primary: str = "surface"
) -> pd.DataFrame:
    """Equal- and value-weighted average premium on both measures, the index premium,
    the gaps, and the counts behind the two floors, per date and maturity. The floors
    count valid implied variances on the primary measure."""
    valid_surface = (
        names[names.drop_code == "OK"]
        .groupby(["date", "node"])
        .size()
        .rename("valid_surface")
    )
    valid_atm = (
        names[np.isfinite(names.implied_var_atm)]
        .groupby(["date", "node"])
        .size()
        .rename("valid_atm")
    )
    daily = pd.concat([valid_surface, valid_atm], axis=1)
    for measure in MEASURES:
        sums = _weighted_sums(names, LOG_RATIO[measure], "previous_market_cap")
        daily = daily.join(
            sums.rename(
                columns={
                    "size": f"names_{measure}",
                    "mean": f"ew_premium_{measure}",
                    "weighted_mean": f"vw_premium_{measure}",
                }
            ),
            how="outer",
        )
    daily = daily.rename_axis(["date", "node"]).reset_index()
    for measure in MEASURES:
        daily[f"valid_{measure}"] = daily[f"valid_{measure}"].fillna(0).astype(int)
    index_columns = {
        "log_ratio_model_free": "index_premium_surface",
        "log_ratio_atm": "index_premium_atm",
        "implied_var_model_free": "index_implied_var_surface",
        "implied_var_atm": "index_implied_var_atm",
        "realized_var": "index_realized_var",
    }
    daily = daily.merge(
        index[["date", "node", *index_columns]].rename(columns=index_columns),
        on=["date", "node"],
        how="left",
    )
    for measure in MEASURES:
        for weighting in ("ew", "vw"):
            daily[f"gap_{measure}_{weighting}"] = (
                daily[f"index_premium_{measure}"]
                - daily[f"{weighting}_premium_{measure}"]
            )
    daily["primary_measure"] = primary
    daily["clears_average_floor"] = daily[f"valid_{primary}"] >= AVERAGE_FLOOR
    daily["clears_correlation_floor"] = daily[f"valid_{primary}"] >= CORRELATION_FLOOR
    daily["year"] = daily.date.dt.year
    return daily


def correlations(names: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Implied and realized correlation per date and maturity on both implied measures,
    with the diagonal and off-diagonal sums behind them."""
    for measure in MEASURES:
        implied = IMPLIED_VAR[measure]
        rows = names[
            np.isfinite(names[implied])
            & (names[implied] > 0)
            & np.isfinite(names.realized_var)
            & (names.realized_var > 0)
            & (names.previous_market_cap > 0)
        ]
        keys = [rows.date, rows.node]
        weight = rows.previous_market_cap / rows.previous_market_cap.groupby(
            keys
        ).transform("sum")
        implied_vol = np.sqrt(rows[implied])
        realized_vol = np.sqrt(rows.realized_var)
        sums = pd.DataFrame(
            {
                "names": weight.groupby(keys).size(),
                "implied_diagonal": (weight**2 * rows[implied]).groupby(keys).sum(),
                "implied_linear": (weight * implied_vol).groupby(keys).sum(),
                "realized_diagonal": (weight**2 * rows.realized_var)
                .groupby(keys)
                .sum(),
                "realized_linear": (weight * realized_vol).groupby(keys).sum(),
            }
        )
        sums["implied_off_diagonal"] = sums.implied_linear**2 - sums.implied_diagonal
        sums["realized_off_diagonal"] = sums.realized_linear**2 - sums.realized_diagonal
        sums = sums.rename_axis(["date", "node"]).reset_index()
        merged = daily[["date", "node"]].merge(sums, on=["date", "node"], how="left")
        index_implied = daily[f"index_implied_var_{measure}"]
        rho_implied = (index_implied.values - merged.implied_diagonal.values) / (
            merged.implied_off_diagonal.values
        )
        rho_realized = (
            daily.index_realized_var.values - merged.realized_diagonal.values
        ) / merged.realized_off_diagonal.values
        daily[f"correlation_names_{measure}"] = merged.names.values
        daily[f"rho_implied_{measure}"] = rho_implied
        daily[f"rho_realized_{measure}"] = rho_realized
        daily[f"rho_difference_{measure}"] = rho_implied - rho_realized
        daily[f"implied_diagonal_{measure}"] = merged.implied_diagonal.values
        daily[f"implied_off_diagonal_{measure}"] = merged.implied_off_diagonal.values
    return daily


def decomposition(daily: pd.DataFrame) -> pd.DataFrame:
    """Section 6.6: the log index variance the correlation premium adds at the observed
    single-name implied variances, and the residual of the equal-weighted gap."""
    for measure in MEASURES:
        diagonal = daily[f"implied_diagonal_{measure}"]
        off_diagonal = daily[f"implied_off_diagonal_{measure}"]
        at_implied = daily[f"rho_implied_{measure}"] * off_diagonal + diagonal
        at_realized = daily[f"rho_realized_{measure}"] * off_diagonal + diagonal
        component = np.log(at_implied.where(at_implied > 0)) - np.log(
            at_realized.where(at_realized > 0)
        )
        daily[f"correlation_component_{measure}"] = component
        daily[f"residual_component_{measure}"] = daily[f"gap_{measure}_ew"] - component
    return daily


def surface_to_atm_ratio(variance: pd.DataFrame) -> pd.DataFrame:
    """Descriptive, no inference: surface-based over ATM implied variance by maturity,
    reporting period and group, the constituents or SPX, on rows where both are valid."""
    rows = variance[(variance.drop_code == "OK") & (variance.implied_var_atm > 0)]
    rows = rows.assign(
        ratio=rows.implied_var / rows.implied_var_atm,
        group=np.where(rows.secid == SPX_SECID, "SPX", "constituents"),
        period=period_of(rows.date),
    )
    table = (
        rows.groupby(["node", "group", "period"], sort=False)
        .ratio.agg(
            rows="size",
            p10=lambda ratio: ratio.quantile(0.10),
            median="median",
            p90=lambda ratio: ratio.quantile(0.90),
            mean_log_ratio=lambda ratio: np.log(ratio).mean(),
        )
        .reset_index()
    )
    table["period_order"] = table.period.map(
        {label: order for order, label in enumerate(PERIODS)}
    )
    return (
        table.sort_values(["node", "group", "period_order"])
        .drop(columns="period_order")
        .reset_index(drop=True)
    )


def period_of(dates: pd.Series) -> pd.Series:
    """Reporting period label of each date."""
    labels = pd.Series(pd.NA, index=dates.index, dtype="object")
    for label, (start, end) in PERIODS.items():
        labels[(dates >= start) & (dates <= end)] = label
    return labels


def decomposition_by_period(daily: pd.DataFrame) -> pd.DataFrame:
    """Mean gap, correlation component and residual by period and maturity on the dates
    clearing the correlation floor where all three exist."""
    rows = []
    for measure in MEASURES:
        columns = [
            f"gap_{measure}_ew",
            f"correlation_component_{measure}",
            f"residual_component_{measure}",
        ]
        usable = daily[daily.clears_correlation_floor].dropna(subset=columns)
        usable = usable.assign(period=period_of(usable.date))
        for (node, period), group in usable.groupby(["node", "period"]):
            rows.append(
                {
                    "node": int(node),
                    "measure": measure,
                    "period": period,
                    "dates": len(group),
                    "mean_gap": float(group[columns[0]].mean()),
                    "mean_correlation_component": float(group[columns[1]].mean()),
                    "mean_residual": float(group[columns[2]].mean()),
                }
            )
    table = pd.DataFrame(rows)
    table["period_order"] = table.period.map(
        {label: order for order, label in enumerate(PERIODS)}
    )
    return (
        table.sort_values(["node", "measure", "period_order"])
        .drop(columns="period_order")
        .reset_index(drop=True)
    )


def annual_cross_section(
    names: pd.DataFrame, daily: pd.DataFrame, primary: str = "surface", node: int = 30
) -> pd.DataFrame:
    """Per year at one maturity: deciles across names of the annual mean single-name
    premium on the primary measure, the index's annual mean premium over the same dates,
    and the share of names above it."""
    log_ratio, index_column = LOG_RATIO[primary], f"index_premium_{primary}"
    dates = daily.loc[
        (daily.node == node) & daily.clears_average_floor, ["date", index_column]
    ]
    rows = names[(names.node == node) & np.isfinite(names[log_ratio])].merge(
        dates[["date"]], on="date"
    )
    rows = rows.assign(year=rows.date.dt.year)
    by_name = rows.groupby(["year", "secid"]).agg(
        premium=(log_ratio, "mean"), days=("date", "size")
    )
    index_dates = dates.dropna().assign(year=dates.date.dt.year)
    index_annual = index_dates.groupby("year")[index_column].mean()
    table = []
    for year, group in by_name.groupby(level="year"):
        premia = group.premium.values
        index_premium = float(index_annual.get(year, np.nan))
        deciles = np.percentile(premia, np.arange(10, 100, 10))
        table.append(
            {
                "year": int(year),
                "names": len(premia),
                "median_days_per_name": float(group.days.median()),
                **{
                    f"p{10 * (position + 1)}": value
                    for position, value in enumerate(deciles)
                },
                "index_premium": index_premium,
                "share_above_index": float((premia > index_premium).mean())
                if np.isfinite(index_premium)
                else np.nan,
            }
        )
    return pd.DataFrame(table)


def annual_means(daily: pd.DataFrame) -> pd.DataFrame:
    """Annual means per maturity of the premia, gaps and correlations over the dates
    clearing each series' floor, with the date counts."""
    average_columns = [
        "index_premium_surface",
        "ew_premium_surface",
        "vw_premium_surface",
        "gap_surface_ew",
        "gap_surface_vw",
        "index_premium_atm",
        "ew_premium_atm",
        "vw_premium_atm",
        "gap_atm_ew",
        "gap_atm_vw",
    ]
    correlation_columns = [
        "rho_implied_surface",
        "rho_realized_surface",
        "rho_difference_surface",
        "rho_implied_atm",
        "rho_realized_atm",
        "rho_difference_atm",
    ]
    averages = (
        daily[daily.clears_average_floor]
        .groupby(["node", "year"])
        .agg(
            average_floor_dates=("date", "size"),
            gap_dates=("gap_surface_ew", "count"),
            **{column: (column, "mean") for column in average_columns},
        )
    )
    correlations_table = (
        daily[daily.clears_correlation_floor]
        .groupby(["node", "year"])
        .agg(
            correlation_floor_dates=("date", "size"),
            correlation_dates=("rho_difference_surface", "count"),
            **{column: (column, "mean") for column in correlation_columns},
        )
    )
    return averages.join(correlations_table, how="outer").reset_index()


def floor_counts(daily: pd.DataFrame, trade_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Per year and maturity: trade dates, dates clearing each floor and dates dropped by
    each."""
    rows = []
    calendar = pd.Series(trade_dates)
    for node in NODES:
        at_node = daily[daily.node == node].set_index("date")
        for year, dates in calendar.groupby(calendar.dt.year):
            present = at_node.reindex(dates.values)
            average = present.clears_average_floor.astype("boolean").fillna(False)
            correlation = present.clears_correlation_floor.astype("boolean").fillna(
                False
            )
            rows.append(
                {
                    "node": node,
                    "year": int(year),
                    "trade_dates": len(dates),
                    "median_valid_surface": float(present.valid_surface.median()),
                    "median_valid_atm": float(present.valid_atm.median()),
                    "clear_300": int(average.sum()),
                    "dropped_by_300": int((~average).sum()),
                    "clear_450": int(correlation.sum()),
                    "dropped_by_450": int((~correlation).sum()),
                }
            )
    return pd.DataFrame(rows)


def non_overlapping_grid(
    daily: pd.DataFrame, trade_dates: pd.DatetimeIndex, sample_start: str
) -> pd.DataFrame:
    """The daily panel sampled every h trading days from the first sample trade date."""
    calendar = pd.DatetimeIndex(trade_dates)
    calendar = calendar[(calendar >= sample_start) & (calendar <= SAMPLE_END)]
    frames = []
    for node, window in WINDOW_TRADING_DAYS.items():
        picks = calendar[::window]
        frames.append(
            pd.DataFrame(
                {"date": picks, "node": node, "grid_index": np.arange(len(picks))}
            )
        )
    grid = pd.concat(frames, ignore_index=True)
    return grid.merge(daily, on=["date", "node"], how="left")
