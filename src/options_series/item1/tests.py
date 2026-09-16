"""The registered tests: the selection check that picks each ETF's headline series, the
eight level tests (H1), the ten curve-slope tests (H2), the pooled level used for
reporting, the curve-state split and the commonality measure (Q3)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from options_series.item1.config import (
    APRIL_2020_END,
    APRIL_2020_START,
    BENCHMARK,
    COMMODITY_ETFS,
    COMMON_END,
    COMMON_START,
    ETF_COMMODITY,
    NODES,
    NORMAL_95_QUANTILE,
    ROBUSTNESS_STRIKE_FLOOR,
    SELECTION_MAX_DIFFERENCE,
    SELECTION_MAX_P_VALUE,
    STATE_POWER_FLOOR,
    STATE_REPORT_FLOOR,
    STRIKE_FLOOR,
    WINDOW_TRADING_DAYS,
)
from options_series.item1.inference import (
    bootstrap_mean_test,
    bootstrap_panel_slope_test,
    bootstrap_slope_test,
    decision,
    grid_mean_test,
    grid_slope_test,
    hac_mean_test,
    hac_slope_test,
    holm_levels,
)
from options_series.item1.model_free_variance import OK

LOG_RATIO_COLUMN = {"model_free": "log_ratio_model_free", "atm": "log_ratio_atm"}
CURVE_COLUMNS = [
    "commodity",
    "date",
    "front_settle",
    "second_settle",
    "curve_state",
    "slope",
]
HEADLINE_MIX = "headline mix"


def assemble_panel(
    premium: pd.DataFrame,
    grid: pd.DataFrame,
    curve_state: pd.DataFrame,
    model_free: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily and grid premium joined to the curve state on the premium's own date, with
    the floor-of-two log ratio and the April 2020 flag."""
    robustness = model_free.loc[
        model_free.strike_floor == ROBUSTNESS_STRIKE_FLOOR,
        ["ticker", "date", "node", "implied_var"],
    ].rename(columns={"implied_var": "implied_var_model_free_floor2"})
    joined = []
    for frame in (premium, grid):
        frame = frame.assign(commodity=frame.ticker.map(ETF_COMMODITY))
        frame = frame.merge(
            curve_state[CURVE_COLUMNS], on=["commodity", "date"], how="left"
        )
        frame = frame.merge(robustness, on=["ticker", "date", "node"], how="left")
        frame["log_ratio_model_free_floor2"] = np.log(
            frame.implied_var_model_free_floor2 / frame.realized_var
        )
        frame["april_2020"] = (frame.date >= APRIL_2020_START) & (
            frame.date <= APRIL_2020_END
        )
        joined.append(frame)
    daily, grid_panel = joined
    daily = daily[(daily.date >= COMMON_START) & (daily.date <= COMMON_END)]
    return daily, grid_panel


def selection_check(model_free: pd.DataFrame, premium: pd.DataFrame) -> pd.DataFrame:
    """At-the-money log ratio on dates the model-free series keeps against dates it drops,
    per ticker and node, with the Welch test and whether the drops are selected."""
    retained = model_free.loc[
        (model_free.strike_floor == STRIKE_FLOOR) & (model_free.drop_code == OK),
        ["ticker", "date", "node"],
    ]
    rows = premium[["ticker", "date", "node", "log_ratio_atm"]].merge(
        retained, on=["ticker", "date", "node"], how="left", indicator=True
    )
    rows["retained"] = rows.pop("_merge") == "both"
    rows = rows[(rows.date >= COMMON_START) & (rows.date <= COMMON_END)]
    rows = rows.dropna(subset=["log_ratio_atm"])
    results = []
    for (ticker, node), group in rows.groupby(["ticker", "node"]):
        kept = group.loc[group.retained, "log_ratio_atm"].values
        dropped = group.loc[~group.retained, "log_ratio_atm"].values
        difference = (
            float(kept.mean() - dropped.mean())
            if len(kept) and len(dropped)
            else np.nan
        )
        p_value = (
            float(stats.ttest_ind(kept, dropped, equal_var=False).pvalue)
            if len(kept) >= 2 and len(dropped) >= 2
            else np.nan
        )
        results.append(
            {
                "ticker": ticker,
                "node": int(node),
                "retained": len(kept),
                "dropped": len(dropped),
                "difference": difference,
                "p_value": p_value,
                "selected": bool(
                    abs(difference) > SELECTION_MAX_DIFFERENCE
                    or p_value < SELECTION_MAX_P_VALUE
                ),
            }
        )
    return pd.DataFrame(results)


def headline_series(selection: pd.DataFrame) -> dict[str, str]:
    """At-the-money headline for an ETF whose model-free drops are selected at either node,
    model-free otherwise."""
    selected = set(selection.loc[selection.selected, "ticker"])
    return {etf: "atm" if etf in selected else "model_free" for etf in COMMODITY_ETFS}


def _mean_row(daily: np.ndarray, grid: np.ndarray, lags: int) -> dict[str, float]:
    """All four inference rows for a mean."""
    hac = hac_mean_test(daily, lags)
    bootstrap = bootstrap_mean_test(daily, lags)
    on_grid = grid_mean_test(grid)
    return {
        "n": hac["n"],
        "estimate": hac["estimate"],
        "se_newey_west": hac["se_newey_west"],
        "p_newey_west": hac["p_newey_west"],
        "p_hansen_hodrick": hac["p_hansen_hodrick"],
        "boot_ci_low": bootstrap["ci_low"],
        "boot_ci_high": bootstrap["ci_high"],
        "p_bootstrap": bootstrap["p_value"],
        "n_grid": on_grid["n"],
        "grid_estimate": on_grid["estimate"],
        "p_grid": on_grid["p_value"],
    }


def _apply_holm(results: pd.DataFrame) -> pd.DataFrame:
    """Holm levels, clearance and the decision for family rows, block by node."""
    results = results.copy()
    results["holm_level_newey_west"] = np.nan
    results["holm_level_bootstrap"] = np.nan
    results["clears_newey_west"] = False
    results["clears_bootstrap"] = False
    results["verdict"] = ""
    for node in NODES:
        block = results.index[(results.node == node) & results.in_family]
        levels_nw, clears_nw = holm_levels(results.loc[block, "p_newey_west"].values)
        levels_boot, clears_boot = holm_levels(results.loc[block, "p_bootstrap"].values)
        results.loc[block, "holm_level_newey_west"] = levels_nw
        results.loc[block, "holm_level_bootstrap"] = levels_boot
        results.loc[block, "clears_newey_west"] = clears_nw
        results.loc[block, "clears_bootstrap"] = clears_boot
        results.loc[block, "verdict"] = [
            decision(nw, boot) for nw, boot in zip(clears_nw, clears_boot)
        ]
    return results


def _outside_april_2020(frame: pd.DataFrame) -> pd.DataFrame:
    """Rows whose window does not start in March or April 2020."""
    return frame[~frame.april_2020]


def level_tests(
    daily: pd.DataFrame, grid: pd.DataFrame, headline: dict[str, str]
) -> pd.DataFrame:
    """H1: mean log(IV²/RV) above zero per ETF and node, with the benchmark, both series,
    the April 2020, floor-of-two and IV² − RV robustness rows."""
    rows = []
    for node in NODES:
        lags = WINDOW_TRADING_DAYS[node]
        for ticker in (*COMMODITY_ETFS, BENCHMARK):
            day = daily[(daily.ticker == ticker) & (daily.node == node)]
            on_grid = grid[(grid.ticker == ticker) & (grid.node == node)]
            specifications = [
                (series, "log_ratio", "full", day, on_grid, column)
                for series, column in LOG_RATIO_COLUMN.items()
            ]
            specifications += [
                (
                    series,
                    "log_ratio",
                    "excluding April 2020",
                    _outside_april_2020(day),
                    _outside_april_2020(on_grid),
                    column,
                )
                for series, column in LOG_RATIO_COLUMN.items()
            ]
            specifications.append(
                (
                    "model_free_floor2",
                    "log_ratio",
                    "full",
                    day,
                    on_grid,
                    "log_ratio_model_free_floor2",
                )
            )
            specifications += [
                (
                    series,
                    "var_difference",
                    "full",
                    day,
                    on_grid,
                    f"var_difference_{series}",
                )
                for series in LOG_RATIO_COLUMN
            ]
            for series, measure, sample, day_rows, grid_rows, column in specifications:
                rows.append(
                    {
                        "node": node,
                        "ticker": ticker,
                        "series": series,
                        "measure": measure,
                        "sample": sample,
                        "in_family": ticker != BENCHMARK
                        and measure == "log_ratio"
                        and sample == "full"
                        and series == headline.get(ticker),
                        **_mean_row(
                            day_rows[column].values, grid_rows[column].values, lags
                        ),
                    }
                )
    return _apply_holm(pd.DataFrame(rows))


def pooled_level(daily: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """Equal-weighted average log ratio across the four commodity ETFs on dates all four
    exist, with all four inference rows; reported outside the test family."""
    rows = []
    for node in NODES:
        lags = WINDOW_TRADING_DAYS[node]
        for series in ("atm", "model_free"):
            column = LOG_RATIO_COLUMN[series]
            wide = (
                daily[daily.ticker.isin(COMMODITY_ETFS) & (daily.node == node)]
                .pivot_table(index="date", columns="ticker", values=column)
                .reindex(columns=list(COMMODITY_ETFS))
                .dropna(how="any")
            )
            wide_grid = (
                grid[grid.ticker.isin(COMMODITY_ETFS) & (grid.node == node)]
                .pivot_table(index="date", columns="ticker", values=column)
                .reindex(columns=list(COMMODITY_ETFS))
                .dropna(how="any")
            )
            row = _mean_row(
                wide.mean(axis=1).values, wide_grid.mean(axis=1).values, lags
            )
            row.update(
                {
                    "node": node,
                    "series": series,
                    "first_date": wide.index.min(),
                    "last_date": wide.index.max(),
                    "nw_ci_low": row["estimate"]
                    - NORMAL_95_QUANTILE * row["se_newey_west"],
                    "nw_ci_high": row["estimate"]
                    + NORMAL_95_QUANTILE * row["se_newey_west"],
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)


def _slope_row(
    daily: pd.DataFrame, grid: pd.DataFrame, lags: int, pooled: bool
) -> dict[str, float]:
    """All four inference rows for the slope of log ratio on the curve slope."""
    hac = hac_slope_test(daily.log_ratio.values, daily.slope.values, lags)
    if pooled:
        bootstrap = bootstrap_panel_slope_test(daily, lags, "log_ratio", "slope")
    else:
        bootstrap = bootstrap_slope_test(
            daily.log_ratio.values, daily.slope.values, lags
        )
    on_grid = grid_slope_test(grid.log_ratio.values, grid.slope.values)
    return {
        "n": hac["n"],
        "estimate": hac["estimate"],
        "se_newey_west": hac["se_newey_west"],
        "p_newey_west": hac["p_newey_west"],
        "p_hansen_hodrick": hac["p_hansen_hodrick"],
        "boot_ci_low": bootstrap["ci_low"],
        "boot_ci_high": bootstrap["ci_high"],
        "p_bootstrap": bootstrap["p_value"],
        "n_grid": on_grid["n"],
        "p_grid": on_grid["p_value"],
    }


def _headline_rows(
    frame: pd.DataFrame, ticker: str, node: int, headline: dict[str, str]
) -> pd.DataFrame:
    """One ETF's rows at one node with its headline log ratio as log_ratio."""
    rows = frame[(frame.ticker == ticker) & (frame.node == node)]
    return rows.assign(log_ratio=rows[LOG_RATIO_COLUMN[headline[ticker]]])


def slope_tests(
    daily: pd.DataFrame, grid: pd.DataFrame, headline: dict[str, str]
) -> pd.DataFrame:
    """H2: slope of the headline log ratio on the curve slope per ETF and pooled within
    ETF, per node, with the April 2020 rows."""
    rows = []
    samples = (
        ("full", lambda frame: frame),
        ("excluding April 2020", _outside_april_2020),
    )
    for node in NODES:
        lags = WINDOW_TRADING_DAYS[node]
        for ticker in COMMODITY_ETFS:
            day = _headline_rows(daily, ticker, node, headline)
            on_grid = _headline_rows(grid, ticker, node, headline)
            for sample, restrict in samples:
                day_rows = restrict(day)
                slope_dates = day_rows.loc[day_rows.slope.notna(), "date"]
                rows.append(
                    {
                        "node": node,
                        "unit": ticker,
                        "series": headline[ticker],
                        "sample": sample,
                        "in_family": sample == "full",
                        "slope_first_date": slope_dates.min(),
                        "slope_last_date": slope_dates.max(),
                        **_slope_row(day_rows, restrict(on_grid), lags, pooled=False),
                    }
                )
        for sample, restrict in samples:
            day_parts, grid_parts = [], []
            for ticker in COMMODITY_ETFS:
                for frame, parts in ((daily, day_parts), (grid, grid_parts)):
                    rows_for_unit = restrict(
                        _headline_rows(frame, ticker, node, headline)
                    )
                    rows_for_unit = rows_for_unit[
                        ["date", "log_ratio", "slope"]
                    ].dropna()
                    parts.append(
                        rows_for_unit.assign(
                            log_ratio=rows_for_unit.log_ratio
                            - rows_for_unit.log_ratio.mean(),
                            slope=rows_for_unit.slope - rows_for_unit.slope.mean(),
                            ticker=ticker,
                        )
                    )
            pooled_daily = pd.concat(day_parts, ignore_index=True).sort_values(
                ["date", "ticker"]
            )
            pooled_grid = pd.concat(grid_parts, ignore_index=True)
            rows.append(
                {
                    "node": node,
                    "unit": "POOLED",
                    "series": HEADLINE_MIX,
                    "sample": sample,
                    "in_family": sample == "full",
                    "slope_first_date": pd.NaT,
                    "slope_last_date": pd.NaT,
                    **_slope_row(pooled_daily, pooled_grid, lags, pooled=True),
                }
            )
    return _apply_holm(pd.DataFrame(rows))


def slope_per_standard_deviation(
    daily: pd.DataFrame, slope_results: pd.DataFrame, headline: dict[str, str]
) -> pd.DataFrame:
    """H2 slopes and intervals scaled to a one-standard-deviation move in each unit's own
    curve slope; a change of units that leaves every p-value unchanged."""
    standard_deviation = {}
    for node in NODES:
        demeaned = []
        for ticker in COMMODITY_ETFS:
            rows = _headline_rows(daily, ticker, node, headline)[
                ["log_ratio", "slope"]
            ].dropna()
            standard_deviation[(node, ticker)] = float(rows.slope.std(ddof=1))
            demeaned.append(rows.slope - rows.slope.mean())
        standard_deviation[(node, "POOLED")] = float(pd.concat(demeaned).std(ddof=1))
    family = slope_results[slope_results.in_family].copy()
    family["slope_sd"] = [
        standard_deviation[(node, unit)] for node, unit in zip(family.node, family.unit)
    ]
    family["estimate_per_sd"] = family.estimate * family.slope_sd
    family["nw_low_per_sd"] = (
        family.estimate - NORMAL_95_QUANTILE * family.se_newey_west
    ) * family.slope_sd
    family["nw_high_per_sd"] = (
        family.estimate + NORMAL_95_QUANTILE * family.se_newey_west
    ) * family.slope_sd
    family["boot_low_per_sd"] = family.boot_ci_low * family.slope_sd
    family["boot_high_per_sd"] = family.boot_ci_high * family.slope_sd
    return family


def curve_state_split(
    daily: pd.DataFrame, grid: pd.DataFrame, headline: dict[str, str]
) -> pd.DataFrame:
    """Mean headline log ratio in contango and in backwardation per ETF and node, with a
    bootstrap interval and the non-overlapping window count; no test."""
    rows = []
    for node in NODES:
        lags = WINDOW_TRADING_DAYS[node]
        for ticker in COMMODITY_ETFS:
            day = _headline_rows(daily, ticker, node, headline)
            on_grid = _headline_rows(grid, ticker, node, headline)
            for state in ("contango", "backwardation"):
                values = day.loc[day.curve_state == state, "log_ratio"].dropna().values
                windows = int(
                    ((on_grid.curve_state == state) & on_grid.log_ratio.notna()).sum()
                )
                interval = bootstrap_mean_test(values, lags)
                if windows < STATE_REPORT_FLOOR:
                    status = (
                        f"reported, not tested (under {STATE_REPORT_FLOOR} windows)"
                    )
                elif windows < STATE_POWER_FLOOR:
                    status = f"underpowered ({STATE_REPORT_FLOOR} to {STATE_POWER_FLOOR - 1} windows)"
                else:
                    status = (
                        f"at or above the {STATE_POWER_FLOOR}-window power threshold"
                    )
                rows.append(
                    {
                        "node": node,
                        "ticker": ticker,
                        "state": state,
                        "daily_observations": len(values),
                        "windows": windows,
                        "mean_log_ratio": float(values.mean()),
                        "ci_low": interval["ci_low"],
                        "ci_high": interval["ci_high"],
                        "status": status,
                    }
                )
    return pd.DataFrame(rows)


def _first_component_share(correlation: pd.DataFrame) -> float:
    """Share of total variance in the first principal component of a correlation matrix."""
    eigenvalues = np.linalg.eigvalsh(correlation.values)
    return float(eigenvalues.max() / correlation.shape[0])


def _wide_log_ratios(
    daily: pd.DataFrame, node: int, column: str, residualise: bool
) -> pd.DataFrame:
    """Daily log ratio per commodity ETF in columns, optionally residualised on each ETF's
    own curve slope by OLS."""
    series = {}
    for ticker in COMMODITY_ETFS:
        rows = daily.loc[
            (daily.ticker == ticker) & (daily.node == node), ["date", column, "slope"]
        ].dropna(subset=[column])
        if residualise:
            rows = rows.dropna(subset=["slope"])
            design = sm.add_constant(rows.slope.values, has_constant="add")
            rows = rows.assign(
                **{column: sm.OLS(rows[column].values, design).fit().resid}
            )
        series[ticker] = rows.set_index("date")[column]
    return pd.DataFrame(series)


def commonality(daily: pd.DataFrame) -> dict[tuple[int, str], dict[str, object]]:
    """First-component share of the pairwise-complete correlation matrix of the four log
    ratios before and after conditioning on own curve slope, per node and series."""
    results = {}
    for node in NODES:
        for series, column in LOG_RATIO_COLUMN.items():
            slope_dates = None
            for ticker in COMMODITY_ETFS:
                rows = daily[(daily.ticker == ticker) & (daily.node == node)]
                dates = set(rows.loc[rows.slope.notna(), "date"])
                slope_dates = dates if slope_dates is None else slope_dates & dates
            slope_dates = pd.DatetimeIndex(sorted(slope_dates))
            before = _wide_log_ratios(daily, node, column, residualise=False)
            after = _wide_log_ratios(daily, node, column, residualise=True)
            correlation_before = before[before.index.isin(slope_dates)].corr(
                min_periods=30
            )
            correlation_after = after[after.index.isin(slope_dates)].corr(
                min_periods=30
            )
            upper = np.triu_indices(len(COMMODITY_ETFS), 1)
            results[(node, series)] = {
                "dates": len(slope_dates),
                "first_date": slope_dates.min(),
                "last_date": slope_dates.max(),
                "share_before": _first_component_share(correlation_before),
                "share_after": _first_component_share(correlation_after),
                "share_full_window": _first_component_share(
                    before.corr(min_periods=30)
                ),
                "full_window_dates": len(before.dropna(how="all")),
                "mean_abs_correlation_before": float(
                    np.abs(correlation_before.values[upper]).mean()
                ),
                "mean_abs_correlation_after": float(
                    np.abs(correlation_after.values[upper]).mean()
                ),
                "correlation_before": correlation_before,
                "correlation_after": correlation_after,
            }
    return results
