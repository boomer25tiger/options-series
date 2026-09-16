"""Inference of spec section 7: Newey-West and Hansen-Hodrick standard errors, the
stationary block bootstrap of Politis and Romano (1994), the non-overlapping t-test,
the Holm correction and the decision rule."""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.regression.linear_model import RegressionResults
from statsmodels.stats.sandwich_covariance import weights_uniform

from options_series.item1.config import ALPHA, BOOTSTRAP_DRAWS, BOOTSTRAP_SEED


def _hac_fit(
    response: np.ndarray, regressors: np.ndarray, lags: int, kernel: str
) -> RegressionResults:
    """OLS fit with a HAC covariance: Bartlett weights for Newey-West, uniform weights
    for Hansen-Hodrick."""
    covariance = {"maxlags": lags, "use_correction": False}
    if kernel == "hansen_hodrick":
        covariance["kernel"] = weights_uniform
    return sm.OLS(response, regressors, missing="drop").fit(
        cov_type="HAC", cov_kwds=covariance
    )


def hac_mean_test(values: np.ndarray, lags: int) -> dict[str, float]:
    """Sample mean with Newey-West and Hansen-Hodrick standard errors and one-sided
    p-values for a positive mean."""
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    constant = np.ones((len(values), 1))
    result = {"n": len(values), "estimate": float(values.mean())}
    for kernel in ("newey_west", "hansen_hodrick"):
        fit = _hac_fit(values, constant, lags, kernel)
        result[f"se_{kernel}"] = float(fit.bse[0])
        result[f"p_{kernel}"] = float(stats.norm.sf(float(fit.tvalues[0])))
    return result


def hac_slope_test(
    response: np.ndarray, regressor: np.ndarray, lags: int
) -> dict[str, float]:
    """OLS slope of response on regressor with Newey-West and Hansen-Hodrick standard
    errors and two-sided p-values."""
    response = np.asarray(response, float)
    regressor = np.asarray(regressor, float)
    observed = np.isfinite(response) & np.isfinite(regressor)
    response, regressor = response[observed], regressor[observed]
    design = sm.add_constant(regressor, has_constant="add")
    result: dict[str, float] = {"n": len(response)}
    for kernel in ("newey_west", "hansen_hodrick"):
        fit = _hac_fit(response, design, lags, kernel)
        result["estimate"] = float(fit.params[1])
        result[f"se_{kernel}"] = float(fit.bse[1])
        result[f"p_{kernel}"] = float(2 * stats.norm.sf(abs(float(fit.tvalues[1]))))
    return result


def stationary_bootstrap_indices(
    length: int, mean_block_length: int, generator: np.random.Generator
) -> np.ndarray:
    """Resampling indices with geometrically distributed block lengths of the given mean."""
    new_block_probability = 1.0 / max(mean_block_length, 1)
    indices = np.empty(length, dtype=np.int64)
    indices[0] = generator.integers(length)
    starts_new_block = generator.random(length) < new_block_probability
    block_starts = generator.integers(0, length, size=length)
    for position in range(1, length):
        indices[position] = (
            block_starts[position]
            if starts_new_block[position]
            else (indices[position - 1] + 1) % length
        )
    return indices


def _percentile_interval(draws: np.ndarray) -> tuple[float, float]:
    """2.5th and 97.5th percentiles of bootstrap draws."""
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def _slope(response: np.ndarray, regressor: np.ndarray) -> float:
    """OLS slope of response on regressor, missing when the regressor has no variance."""
    centred = regressor - regressor.mean()
    denominator = (centred**2).sum()
    if denominator == 0:
        return np.nan
    return float((centred * (response - response.mean())).sum() / denominator)


def _two_sided_share(draws: np.ndarray) -> float:
    """Twice the smaller share of bootstrap draws on either side of zero, capped at one."""
    at_or_below = float((draws <= 0).mean())
    at_or_above = float((draws >= 0).mean())
    return float(min(1.0, 2 * min(at_or_below, at_or_above)))


def bootstrap_mean_test(
    values: np.ndarray,
    mean_block_length: int,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, float]:
    """Bootstrap 95 percent interval for the mean and the one-sided p-value: the share
    of bootstrap means at or below zero."""
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    generator = np.random.default_rng(seed)
    means = np.empty(draws)
    for draw in range(draws):
        means[draw] = values[
            stationary_bootstrap_indices(len(values), mean_block_length, generator)
        ].mean()
    low, high = _percentile_interval(means)
    return {"ci_low": low, "ci_high": high, "p_value": float((means <= 0).mean())}


def bootstrap_slope_test(
    response: np.ndarray,
    regressor: np.ndarray,
    mean_block_length: int,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, float]:
    """Bootstrap 95 percent interval for the OLS slope and its two-sided p-value."""
    response = np.asarray(response, float)
    regressor = np.asarray(regressor, float)
    observed = np.isfinite(response) & np.isfinite(regressor)
    response, regressor = response[observed], regressor[observed]
    generator = np.random.default_rng(seed)
    slopes = np.empty(draws)
    for draw in range(draws):
        indices = stationary_bootstrap_indices(
            len(response), mean_block_length, generator
        )
        slopes[draw] = _slope(response[indices], regressor[indices])
    slopes = slopes[np.isfinite(slopes)]
    low, high = _percentile_interval(slopes)
    return {"ci_low": low, "ci_high": high, "p_value": _two_sided_share(slopes)}


def bootstrap_panel_slope_test(
    panel: pd.DataFrame,
    mean_block_length: int,
    response_column: str,
    regressor_column: str,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, float]:
    """Bootstrap interval and two-sided p-value for a pooled slope, resampling blocks of
    dates and every unit on a sampled date so cross-sectional dependence is kept."""
    rows = panel[["date", response_column, regressor_column]].dropna()
    by_date = [
        group[[response_column, regressor_column]].to_numpy(float)
        for _, group in rows.groupby("date", sort=True)
    ]
    generator = np.random.default_rng(seed)
    slopes = np.empty(draws)
    for draw in range(draws):
        indices = stationary_bootstrap_indices(
            len(by_date), mean_block_length, generator
        )
        sample = np.vstack([by_date[index] for index in indices])
        slopes[draw] = _slope(sample[:, 0], sample[:, 1])
    slopes = slopes[np.isfinite(slopes)]
    low, high = _percentile_interval(slopes)
    return {"ci_low": low, "ci_high": high, "p_value": _two_sided_share(slopes)}


def grid_mean_test(values: np.ndarray) -> dict[str, float]:
    """Mean on the non-overlapping grid with a one-sided t-test for a positive mean."""
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    t_statistic, two_sided = stats.ttest_1samp(values, 0.0)
    one_sided = two_sided / 2 if t_statistic > 0 else 1 - two_sided / 2
    return {
        "n": len(values),
        "estimate": float(values.mean()),
        "p_value": float(one_sided),
    }


def grid_slope_test(response: np.ndarray, regressor: np.ndarray) -> dict[str, float]:
    """OLS slope on the non-overlapping grid with a two-sided t-test."""
    response = np.asarray(response, float)
    regressor = np.asarray(regressor, float)
    observed = np.isfinite(response) & np.isfinite(regressor)
    response, regressor = response[observed], regressor[observed]
    fit = sm.OLS(response, sm.add_constant(regressor, has_constant="add")).fit()
    return {
        "n": len(response),
        "estimate": float(fit.params[1]),
        "p_value": float(fit.pvalues[1]),
    }


def holm_levels(
    p_values: np.ndarray, alpha: float = ALPHA
) -> tuple[np.ndarray, np.ndarray]:
    """Holm-corrected significance level for each p-value and whether it clears, in input
    order."""
    p_values = np.asarray(p_values, float)
    count = len(p_values)
    order = np.argsort(np.where(np.isfinite(p_values), p_values, np.inf))
    levels = np.full(count, np.nan)
    clears = np.zeros(count, dtype=bool)
    still_rejecting = True
    for rank, position in enumerate(order):
        levels[position] = alpha / (count - rank)
        if still_rejecting and p_values[position] <= levels[position]:
            clears[position] = True
        else:
            still_rejecting = False
    return levels, clears


def decision(newey_west_clears: bool, bootstrap_clears: bool) -> str:
    """Section 7 decision rule applied to the two Holm-corrected outcomes."""
    if newey_west_clears and bootstrap_clears:
        return "supported"
    if newey_west_clears != bootstrap_clears:
        return "not robust to inference method"
    return "not supported"
