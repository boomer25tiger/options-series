"""The test family of spec section 9, the O1 slope of section 7, the tail statistics
reported with every mean, and breakeven k of section 6.

Choices the spec leaves open, fixed before any test ran.
- Mean tests are one-sided for a positive mean. Newey-West p-values come from item 1's
  HAC test; the stationary block bootstrap p-value is the share of bootstrap means at or
  below zero, with the mean block length equal to the Newey-West lag, item 1's convention.
- Holm runs within each block separately on the Newey-West and the bootstrap p-values.
  Block C's mean test stands alone at 5 percent, because section 7 says the slope's
  procedure is never combined with section 9's.
- The O1 slope's clustered standard error uses the usual small-sample factor and a t
  distribution with one fewer degree of freedom than clusters. The wild cluster bootstrap
  imposes the null of a zero slope and draws Rademacher signs per cycle date; its p-value
  is the share of bootstrap t statistics at least as large in magnitude as the sample's.
- CVaR at 5 percent is the mean of the returns at or below the 5th percentile. The worst
  5 percent's share of cumulative loss divides the summed returns of the worst 5 percent
  of cycles by the summed negative returns.
- Breakeven k is linear interpolation between the mean at k = 0 and at k = 1, exact
  because every cost and its financing enter the return linearly in k.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from options_series.item1.inference import (
    bootstrap_mean_test,
    decision,
    hac_mean_test,
    holm_levels,
    stationary_bootstrap_indices,
)

SEED = 20260917
DRAWS = 9999
ESTIMATION_LAG = 4
HOLDOUT_LAG = 3
ALPHA = 0.05
UNITS: tuple[str, ...] = ("GLD", "SLV", "USO", "UNG", "POOLED")


def tail_statistics(values: np.ndarray) -> dict[str, float]:
    """Median, skewness, 5 percent CVaR and the worst 5 percent's share of loss."""
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    cutoff = np.quantile(values, 0.05)
    worst = np.sort(values)[: max(int(np.ceil(0.05 * len(values))), 1)]
    losses = values[values < 0].sum()
    return {
        "median": float(np.median(values)),
        "skewness": float(stats.skew(values)),
        "cvar_5": float(values[values <= cutoff].mean()),
        "worst_5pct_loss_share": float(worst[worst < 0].sum() / losses)
        if losses < 0
        else np.nan,
    }


def mean_test(values: np.ndarray, lag: int) -> dict[str, float]:
    """Mean with its Newey-West and stationary block bootstrap one-sided p-values and
    the tail statistics."""
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    hac = hac_mean_test(values, lag)
    bootstrap = bootstrap_mean_test(values, lag, DRAWS, SEED)
    return {
        "n": hac["n"],
        "mean": hac["estimate"],
        "se_newey_west": hac["se_newey_west"],
        "p_newey_west": hac["p_newey_west"],
        "boot_ci_low": bootstrap["ci_low"],
        "boot_ci_high": bootstrap["ci_high"],
        "p_bootstrap": bootstrap["p_value"],
        **tail_statistics(values),
    }


def unit_series(
    rows: pd.DataFrame, column: str, pooled: pd.DataFrame
) -> dict[str, np.ndarray]:
    """Each fund's cycle returns in entry order and the pooled series."""
    series = {
        ticker: group.sort_values("entry")[column].to_numpy(float)
        for ticker, group in rows.groupby("ticker")
    }
    series["POOLED"] = pooled[column].to_numpy(float)
    return series


def block_tests(
    block: str,
    by_arm: dict[str, dict[str, np.ndarray]],
    lag: int,
    test: bool = True,
) -> pd.DataFrame:
    """One block's mean tests over funds and arms, Holm within the block when tested."""
    rows = []
    for arm, series in by_arm.items():
        for unit in UNITS:
            if unit in series and len(series[unit]):
                rows.append(
                    {
                        "block": block,
                        "arm": arm,
                        "unit": unit,
                        **mean_test(series[unit], lag),
                    }
                )
    table = pd.DataFrame(rows)
    if test and len(table):
        levels_nw, clears_nw = holm_levels(table.p_newey_west.to_numpy(), ALPHA)
        levels_boot, clears_boot = holm_levels(table.p_bootstrap.to_numpy(), ALPHA)
        table["holm_level_newey_west"] = levels_nw
        table["holm_level_bootstrap"] = levels_boot
        table["clears_newey_west"] = clears_nw
        table["clears_bootstrap"] = clears_boot
        table["verdict"] = [
            decision(nw, boot) for nw, boot in zip(clears_nw, clears_boot)
        ]
    return table


def _cluster_fit(response: np.ndarray, design: np.ndarray, groups: np.ndarray):
    """OLS with standard errors clustered on groups."""
    return sm.OLS(response, design).fit(
        cov_type="cluster", cov_kwds={"groups": groups, "use_correction": True}
    )


def slope_test(frame: pd.DataFrame, response: str, regressor: str) -> dict[str, float]:
    """Section 7's registered O1 slope: OLS with cycle-date clustered errors and a
    restricted Rademacher wild cluster bootstrap."""
    rows = frame.dropna(subset=[response, regressor])
    groups = pd.factorize(rows.entry)[0]
    y = rows[response].to_numpy(float)
    x = sm.add_constant(rows[regressor].to_numpy(float))
    fit = _cluster_fit(y, x, groups)
    clusters = int(groups.max() + 1)
    t_quantile = stats.t.ppf(0.975, clusters - 1)
    estimate, error = float(fit.params[1]), float(fit.bse[1])
    t_sample = estimate / error
    restricted = y.mean()
    residual = y - restricted
    generator = np.random.default_rng(SEED)
    t_draws = np.empty(DRAWS)
    for draw in range(DRAWS):
        signs = generator.choice((-1.0, 1.0), size=clusters)[groups]
        boot = _cluster_fit(restricted + residual * signs, x, groups)
        t_draws[draw] = boot.params[1] / boot.bse[1]
    p_boot = float((np.abs(t_draws) >= abs(t_sample)).mean())
    low, high = estimate - t_quantile * error, estimate + t_quantile * error
    return {
        "n": len(rows),
        "clusters": clusters,
        "estimate": estimate,
        "se_clustered": error,
        "ci_low": low,
        "ci_high": high,
        "p_clustered": float(2 * stats.t.sf(abs(t_sample), clusters - 1)),
        "p_wild_bootstrap": p_boot,
        "clustered_clears": bool(low > 0 or high < 0),
        "bootstrap_clears": bool(p_boot < ALPHA),
    }


def diagnostic_regressions(frame: pd.DataFrame, response: str) -> pd.DataFrame:
    """Section 7's diagnostic regressions 2 and 3, coefficients only."""
    rows = []
    specs = (
        ("2: return on log K and log RV21", response),
        ("3: log cycle RV on log K and log RV21", "log_rv"),
        ("3: cycle RV on log K and log RV21", "rv"),
    )
    for label, dependent in specs:
        data = frame.dropna(subset=[dependent, "log_k", "log_rv21"])
        fit = sm.OLS(
            data[dependent].to_numpy(float),
            sm.add_constant(data[["log_k", "log_rv21"]].to_numpy(float)),
        ).fit()
        rows.append(
            {
                "regression": label,
                "n": len(data),
                "intercept": float(fit.params[0]),
                "coef_log_k": float(fit.params[1]),
                "coef_log_rv21": float(fit.params[2]),
                "r_squared": float(fit.rsquared),
            }
        )
    return pd.DataFrame(rows)


def breakeven(mean_zero: float, mean_one: float) -> float:
    """Execution fraction where the mean return crosses zero on the line through the
    means at k = 0 and k = 1."""
    slope = mean_one - mean_zero
    return float(-mean_zero / slope) if slope else np.nan


def breakeven_row(zero: np.ndarray, one: np.ndarray, lag: int) -> dict[str, object]:
    """Breakeven k with a stationary block bootstrap interval, or the verdict at an end
    of the grid."""
    zero, one = np.asarray(zero, float), np.asarray(one, float)
    mean_zero, mean_one = float(zero.mean()), float(one.mean())
    generator = np.random.default_rng(SEED)
    draws = np.empty(DRAWS)
    for draw in range(DRAWS):
        indices = stationary_bootstrap_indices(len(zero), lag, generator)
        draws[draw] = breakeven(zero[indices].mean(), one[indices].mean())
    if mean_zero < 0:
        outcome = "negative at mid"
    elif mean_one > 0:
        outcome = "survives the full quoted half-spread"
    else:
        outcome = "breaks even inside the grid"
    return {
        "n": len(zero),
        "mean_k0": mean_zero,
        "mean_k1": mean_one,
        "breakeven_k": breakeven(mean_zero, mean_one),
        "boot_ci_low": float(np.nanpercentile(draws, 2.5)),
        "boot_ci_high": float(np.nanpercentile(draws, 97.5)),
        "outcome": outcome,
    }
