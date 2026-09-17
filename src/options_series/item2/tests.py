"""The six registered tests of spec section 7 on item 1's inference module, the period
cells reported beside H2, the break date and the zero-days-to-expiry volume share of
section 6.7.

Choices sections 6.7 and 7 leave open, fixed before any test ran.
- H2's difference in mean gap is the slope on an indicator for the later period in a
  regression on the dates of both periods, so item 1's two-sided slope inference
  applies unchanged.
- Each hypothesis is one Holm block of two, its two maturities; the primary measure
  with equal weights is the family row, the surface measure unless stop rule 9.2 moves
  the primary to ATM, and the other measure and value-weighted rows sit beside it
  outside the family.
- The break date is the first year of the second regime in a one-break mean shift fitted
  by least squares to the annual mean gap, each regime at least 15 percent of the years.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import wrds

from options_series.db import query
from options_series.item1.inference import (
    bootstrap_mean_test,
    bootstrap_slope_test,
    decision,
    grid_mean_test,
    grid_slope_test,
    hac_mean_test,
    hac_slope_test,
    holm_levels,
)
from options_series.item2.config import (
    ALPHA,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    BREAK_TRIM,
    H2_AFTER,
    H2_BEFORE,
    NODES,
    SPX_SECID,
    WINDOW_TRADING_DAYS,
)
from options_series.item2.correlation import period_of
from options_series.item2.membership import sample_years, year_bounds

LOGGER = logging.getLogger(__name__)

NORMAL_95_QUANTILE = 1.96
GAP_ROWS = (
    ("surface", "equal", "gap_surface_ew"),
    ("atm", "equal", "gap_atm_ew"),
    ("surface", "value", "gap_surface_vw"),
    ("atm", "value", "gap_atm_vw"),
)
CORRELATION_ROWS = (
    ("surface", "rho_difference_surface"),
    ("atm", "rho_difference_atm"),
)


def _apply_holm(results: pd.DataFrame) -> pd.DataFrame:
    """Holm levels, clearance and the section 7 decision for the family rows, which form
    one block across the two maturities."""
    results = results.copy()
    for column in ("holm_level_newey_west", "holm_level_bootstrap"):
        results[column] = np.nan
    results["clears_newey_west"] = False
    results["clears_bootstrap"] = False
    results["verdict"] = ""
    block = results.index[results.in_family]
    levels_nw, clears_nw = holm_levels(results.loc[block, "p_newey_west"].values, ALPHA)
    levels_boot, clears_boot = holm_levels(
        results.loc[block, "p_bootstrap"].values, ALPHA
    )
    results.loc[block, "holm_level_newey_west"] = levels_nw
    results.loc[block, "holm_level_bootstrap"] = levels_boot
    results.loc[block, "clears_newey_west"] = clears_nw
    results.loc[block, "clears_bootstrap"] = clears_boot
    results.loc[block, "verdict"] = [
        decision(nw, boot) for nw, boot in zip(clears_nw, clears_boot)
    ]
    return results


def _mean_row(daily: pd.Series, grid: pd.Series, lags: int) -> dict[str, float]:
    """All four inference rows for a positive mean on a series in date order."""
    daily_values = daily.dropna().values
    hac = hac_mean_test(daily_values, lags)
    bootstrap = bootstrap_mean_test(daily_values, lags, BOOTSTRAP_DRAWS, BOOTSTRAP_SEED)
    on_grid = grid_mean_test(grid.dropna().values)
    return {
        "n": hac["n"],
        "estimate": hac["estimate"],
        "se_newey_west": hac["se_newey_west"],
        "nw_ci_low": hac["estimate"] - NORMAL_95_QUANTILE * hac["se_newey_west"],
        "nw_ci_high": hac["estimate"] + NORMAL_95_QUANTILE * hac["se_newey_west"],
        "p_newey_west": hac["p_newey_west"],
        "p_hansen_hodrick": hac["p_hansen_hodrick"],
        "boot_ci_low": bootstrap["ci_low"],
        "boot_ci_high": bootstrap["ci_high"],
        "p_bootstrap": bootstrap["p_value"],
        "n_grid": on_grid["n"],
        "grid_estimate": on_grid["estimate"],
        "p_grid": on_grid["p_value"],
    }


def _clearing_floor(frame: pd.DataFrame, node: int, floor: str) -> pd.DataFrame:
    """Rows of one maturity clearing a floor, in date order."""
    return frame[(frame.node == node) & frame[floor].eq(True)].sort_values("date")


def h1_tests(
    daily: pd.DataFrame, grid: pd.DataFrame, primary: str = "surface"
) -> pd.DataFrame:
    """H1: the index premium exceeds the equal-weighted constituent average, per
    maturity, with the ATM and value-weighted rows beside it."""
    rows = []
    for node in NODES:
        lags = WINDOW_TRADING_DAYS[node]
        day = _clearing_floor(daily, node, "clears_average_floor")
        on_grid = _clearing_floor(grid, node, "clears_average_floor")
        for measure, weighting, column in GAP_ROWS:
            rows.append(
                {
                    "node": node,
                    "measure": measure,
                    "weighting": weighting,
                    "in_family": measure == primary and weighting == "equal",
                    "first_date": day.loc[day[column].notna(), "date"].min(),
                    "last_date": day.loc[day[column].notna(), "date"].max(),
                    **_mean_row(day[column], on_grid[column], lags),
                }
            )
    return _apply_holm(pd.DataFrame(rows))


def _period_indicator(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows inside either H2 period with an indicator for the later one."""
    before = (frame.date >= H2_BEFORE[0]) & (frame.date <= H2_BEFORE[1])
    after = (frame.date >= H2_AFTER[0]) & (frame.date <= H2_AFTER[1])
    return frame[before | after].assign(later=after[before | after].astype(float))


def h2_tests(
    daily: pd.DataFrame, grid: pd.DataFrame, primary: str = "surface"
) -> pd.DataFrame:
    """H2: the mean gap over the later period minus the mean over the earlier one, per
    maturity, two-sided, with the ATM and value-weighted rows beside it."""
    rows = []
    for node in NODES:
        lags = WINDOW_TRADING_DAYS[node]
        day = _period_indicator(_clearing_floor(daily, node, "clears_average_floor"))
        on_grid = _period_indicator(_clearing_floor(grid, node, "clears_average_floor"))
        for measure, weighting, column in GAP_ROWS:
            day_rows = day.dropna(subset=[column])
            grid_rows = on_grid.dropna(subset=[column])
            hac = hac_slope_test(day_rows[column].values, day_rows.later.values, lags)
            bootstrap = bootstrap_slope_test(
                day_rows[column].values,
                day_rows.later.values,
                lags,
                BOOTSTRAP_DRAWS,
                BOOTSTRAP_SEED,
            )
            fitted_grid = grid_slope_test(
                grid_rows[column].values, grid_rows.later.values
            )
            rows.append(
                {
                    "node": node,
                    "measure": measure,
                    "weighting": weighting,
                    "in_family": measure == primary and weighting == "equal",
                    "n_before": int((day_rows.later == 0).sum()),
                    "n_after": int((day_rows.later == 1).sum()),
                    "mean_before": float(
                        day_rows.loc[day_rows.later == 0, column].mean()
                    ),
                    "mean_after": float(
                        day_rows.loc[day_rows.later == 1, column].mean()
                    ),
                    "n": hac["n"],
                    "estimate": hac["estimate"],
                    "se_newey_west": hac["se_newey_west"],
                    "nw_ci_low": hac["estimate"]
                    - NORMAL_95_QUANTILE * hac["se_newey_west"],
                    "nw_ci_high": hac["estimate"]
                    + NORMAL_95_QUANTILE * hac["se_newey_west"],
                    "p_newey_west": hac["p_newey_west"],
                    "p_hansen_hodrick": hac["p_hansen_hodrick"],
                    "boot_ci_low": bootstrap["ci_low"],
                    "boot_ci_high": bootstrap["ci_high"],
                    "p_bootstrap": bootstrap["p_value"],
                    "n_grid": fitted_grid["n"],
                    "grid_estimate": fitted_grid["estimate"],
                    "p_grid": fitted_grid["p_value"],
                }
            )
    return _apply_holm(pd.DataFrame(rows))


def period_cells(daily: pd.DataFrame) -> pd.DataFrame:
    """Mean gap by reporting period per maturity, measure and weighting, with the date
    count; no test."""
    rows = []
    usable = daily[daily.clears_average_floor]
    usable = usable.assign(period=period_of(usable.date))
    for node in NODES:
        at_node = usable[usable.node == node]
        for measure, weighting, column in GAP_ROWS:
            for period, group in at_node.groupby("period", sort=False):
                values = group[column].dropna()
                rows.append(
                    {
                        "node": node,
                        "measure": measure,
                        "weighting": weighting,
                        "period": period,
                        "dates": len(values),
                        "mean_gap": float(values.mean()) if len(values) else np.nan,
                    }
                )
    return pd.DataFrame(rows)


def h3_tests(
    daily: pd.DataFrame, grid: pd.DataFrame, primary: str = "surface"
) -> pd.DataFrame:
    """H3: implied correlation exceeds the realized correlation over the following window,
    per maturity, with the ATM-based implied correlation beside it."""
    rows = []
    for node in NODES:
        lags = WINDOW_TRADING_DAYS[node]
        day = _clearing_floor(daily, node, "clears_correlation_floor")
        on_grid = _clearing_floor(grid, node, "clears_correlation_floor")
        for measure, column in CORRELATION_ROWS:
            present = day.dropna(subset=[column])
            rows.append(
                {
                    "node": node,
                    "measure": measure,
                    "in_family": measure == primary,
                    "mean_rho_implied": float(present[f"rho_implied_{measure}"].mean()),
                    "mean_rho_realized": float(
                        present[f"rho_realized_{measure}"].mean()
                    ),
                    "first_date": present.date.min(),
                    "last_date": present.date.max(),
                    **_mean_row(day[column], on_grid[column], lags),
                }
            )
    return _apply_holm(pd.DataFrame(rows))


def break_date(annual: pd.DataFrame, column: str = "gap_surface_ew") -> pd.DataFrame:
    """One break in the mean of the annual series per maturity by least squares (Bai and
    Perron 1998), no test: the first year of the second regime and the two means."""
    rows = []
    for node in NODES:
        series = annual[annual.node == node].dropna(subset=[column]).sort_values("year")
        years, values = series.year.values, series[column].values
        count = len(values)
        minimum = max(2, int(np.ceil(BREAK_TRIM * count)))
        if count < 2 * minimum:
            continue
        best = None
        for split in range(minimum, count - minimum + 1):
            first, second = values[:split], values[split:]
            residual = ((first - first.mean()) ** 2).sum() + (
                (second - second.mean()) ** 2
            ).sum()
            if best is None or residual < best[0]:
                best = (residual, split)
        residual, split = best
        rows.append(
            {
                "node": node,
                "series": column,
                "years": count,
                "first_year": int(years[0]),
                "last_year": int(years[-1]),
                "minimum_regime_years": minimum,
                "break_year": int(years[split]),
                "mean_before": float(values[:split].mean()),
                "mean_after": float(values[split:].mean()),
                "residual_sum_of_squares": float(residual),
                "total_sum_of_squares": float(((values - values.mean()) ** 2).sum()),
            }
        )
    return pd.DataFrame(rows)


def pull_zero_dte_share(connection: wrds.Connection) -> pd.DataFrame:
    """SPX option volume by year and the share traded at zero days to expiry, days to
    expiry being exdate minus date, one partition at a time."""
    rows = []
    for year in sample_years():
        start, end = year_bounds(year)
        volume = query(
            connection,
            f"select sum(volume) as volume, "
            "sum(case when exdate - date = 0 then volume else 0 end) as zero_dte_volume "
            f"from optionm.opprcd{year} "
            "where secid = %(secid)s and date between %(start)s and %(end)s",
            {"secid": float(SPX_SECID), "start": start, "end": end},
        )
        total = float(pd.to_numeric(volume.volume).iloc[0])
        zero_dte = float(pd.to_numeric(volume.zero_dte_volume).iloc[0])
        rows.append(
            {
                "year": year,
                "volume": total,
                "zero_dte_volume": zero_dte,
                "zero_dte_share": zero_dte / total if total else np.nan,
            }
        )
        LOGGER.info("zero-dte share %d: %.4f", year, rows[-1]["zero_dte_share"])
    return pd.DataFrame(rows)
