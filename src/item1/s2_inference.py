"""Section 7 inference machinery. Implemented once, reused by H1 and H2.

Four rows per test:
  NW    Newey-West HAC, Bartlett kernel, maxlags h
  HH    Hansen-Hodrick HAC, uniform (truncated) weights, maxlags h
  BOOT  stationary block bootstrap (Politis and Romano 1994), expected block length h,
        2,000 draws, seed 20260915. The p-value is the share of bootstrap statistics on
        the null side of zero, one-sided for H1 and two-sided for H2, exactly as the
        session instruction fixes it. With B draws the resolution floor is 1/B, so a
        reported 0.0000 means "below 1/B", not zero.
  GRID  the same statistic on the non-overlapping grid with a plain t-test

Holm is applied within each of the four blocks of section 7, separately to the NW and
the bootstrap p-values. The decision rule of section 7 is applied in `verdict`.
"""
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.sandwich_covariance import weights_uniform
from scipy import stats

SEED = 20260915
N_DRAWS_DEFAULT = 2000
ALPHA = 0.05


def _ols(y, X, cov, h):
    m = sm.OLS(y, X, missing="drop")
    if cov == "NW":
        return m.fit(cov_type="HAC", cov_kwds={"maxlags": h, "use_correction": False})
    if cov == "HH":
        return m.fit(cov_type="HAC", cov_kwds={"maxlags": h, "kernel": weights_uniform,
                                               "use_correction": False})
    return m.fit()


def hac_mean(y, h):
    """Mean of y with NW and HH standard errors. One-sided p for the alternative mean > 0."""
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    X = np.ones((len(y), 1))
    out = {"n": len(y), "estimate": float(y.mean())}
    for cov in ("NW", "HH"):
        r = _ols(y, X, cov, h)
        se = float(r.bse[0]); t = float(r.tvalues[0])
        out[cov] = {"se": se, "t": t, "p_one_sided": float(stats.norm.sf(t)),
                    "p_two_sided": float(2 * stats.norm.sf(abs(t)))}
    return out


def hac_slope(y, x, h):
    """OLS of y on a constant and x, with NW and HH standard errors. Two-sided p."""
    y = np.asarray(y, float); x = np.asarray(x, float)
    ok = np.isfinite(y) & np.isfinite(x)
    y, x = y[ok], x[ok]
    X = sm.add_constant(x, has_constant="add")
    out = {"n": len(y), "estimate": float(np.polyfit(x, y, 1)[0]) if len(y) > 1 else np.nan}
    for cov in ("NW", "HH"):
        r = _ols(y, X, cov, h)
        out["estimate"] = float(r.params[1])
        se = float(r.bse[1]); t = float(r.tvalues[1])
        out[cov] = {"se": se, "t": t, "p_two_sided": float(2 * stats.norm.sf(abs(t))),
                    "p_one_sided": float(stats.norm.sf(t))}
    return out


def _stationary_indices(n, h, rng):
    """Politis and Romano stationary bootstrap indices, expected block length h."""
    p = 1.0 / max(h, 1)
    idx = np.empty(n, dtype=np.int64)
    idx[0] = rng.integers(n)
    newblock = rng.random(n) < p
    steps = rng.integers(0, n, size=n)
    for i in range(1, n):
        idx[i] = steps[i] if newblock[i] else (idx[i - 1] + 1) % n
    return idx


def boot_mean(y, h, n_draws=N_DRAWS_DEFAULT, seed=SEED):
    """One-sided bootstrap p for the alternative mean > 0: share of draws at or below 0."""
    y = np.asarray(y, float); y = y[np.isfinite(y)]
    n = len(y)
    rng = np.random.default_rng(seed)
    stat = np.empty(n_draws)
    for b in range(n_draws):
        stat[b] = y[_stationary_indices(n, h, rng)].mean()
    return {"n_draws": n_draws, "mean_of_draws": float(stat.mean()),
            "sd_of_draws": float(stat.std(ddof=1)),
            "ci_lo": float(np.percentile(stat, 2.5)), "ci_hi": float(np.percentile(stat, 97.5)),
            "p_one_sided": float((stat <= 0).mean())}


def boot_slope(y, x, h, n_draws=N_DRAWS_DEFAULT, seed=SEED):
    """Two-sided bootstrap p for the slope: 2 x min(share at or below 0, share at or above 0)."""
    y = np.asarray(y, float); x = np.asarray(x, float)
    ok = np.isfinite(y) & np.isfinite(x)
    y, x = y[ok], x[ok]
    n = len(y)
    rng = np.random.default_rng(seed)
    stat = np.empty(n_draws)
    for b in range(n_draws):
        i = _stationary_indices(n, h, rng)
        yb, xb = y[i], x[i]
        xm = xb.mean(); den = ((xb - xm) ** 2).sum()
        stat[b] = np.nan if den == 0 else ((xb - xm) * (yb - yb.mean())).sum() / den
    stat = stat[np.isfinite(stat)]
    lo = float((stat <= 0).mean()); hi = float((stat >= 0).mean())
    return {"n_draws": len(stat), "mean_of_draws": float(stat.mean()),
            "sd_of_draws": float(stat.std(ddof=1)),
            "ci_lo": float(np.percentile(stat, 2.5)), "ci_hi": float(np.percentile(stat, 97.5)),
            "p_two_sided": float(min(1.0, 2 * min(lo, hi)))}


def grid_mean(y):
    y = np.asarray(y, float); y = y[np.isfinite(y)]
    if len(y) < 3:
        return {"n": len(y), "estimate": float(y.mean()) if len(y) else np.nan,
                "t": np.nan, "p_one_sided": np.nan}
    t, p2 = stats.ttest_1samp(y, 0.0)
    return {"n": len(y), "estimate": float(y.mean()), "t": float(t),
            "p_one_sided": float(p2 / 2 if t > 0 else 1 - p2 / 2)}


def grid_slope(y, x):
    y = np.asarray(y, float); x = np.asarray(x, float)
    ok = np.isfinite(y) & np.isfinite(x)
    y, x = y[ok], x[ok]
    if len(y) < 4:
        return {"n": len(y), "estimate": np.nan, "t": np.nan, "p_two_sided": np.nan}
    X = sm.add_constant(x, has_constant="add")
    r = sm.OLS(y, X).fit()
    return {"n": len(y), "estimate": float(r.params[1]), "t": float(r.tvalues[1]),
            "p_two_sided": float(r.pvalues[1])}


def holm(pvals, alpha=ALPHA):
    """Holm-Bonferroni. Returns per-test corrected level and reject flag, input order."""
    p = np.asarray(pvals, float)
    m = len(p)
    order = np.argsort(np.where(np.isfinite(p), p, np.inf))
    level = np.full(m, np.nan)
    rej = np.zeros(m, dtype=bool)
    still = True
    for rank, i in enumerate(order):
        lv = alpha / (m - rank)
        level[i] = lv
        if still and np.isfinite(p[i]) and p[i] <= lv:
            rej[i] = True
        else:
            still = False
    return level, rej


def verdict(nw_rej, boot_rej):
    if nw_rej and boot_rej:
        return "supported"
    if nw_rej != boot_rej:
        return "not robust to inference method"
    return "not supported"


def boot_slope_panel(df, h, ycol, xcol, keycol="date", n_draws=N_DRAWS_DEFAULT, seed=SEED):
    """Stationary block bootstrap for a pooled panel slope, resampling DATES jointly.

    Blocks are drawn over the ordered set of distinct dates and every ETF present on a
    sampled date is taken with it, so the draw preserves the cross-sectional dependence
    among the four commodity premia as well as the serial dependence. Used for the
    pooled H2 rows; the per-ETF rows have a single series and use boot_slope.
    """
    d = df[[keycol, ycol, xcol]].dropna()
    dates = np.sort(d[keycol].unique())
    n = len(dates)
    pos = {k: i for i, k in enumerate(dates)}
    groups = [g[[ycol, xcol]].to_numpy(float) for _, g in d.groupby(keycol, sort=True)]
    rng = np.random.default_rng(seed)
    stat = np.empty(n_draws)
    for b in range(n_draws):
        idx = _stationary_indices(n, h, rng)
        arr = np.vstack([groups[i] for i in idx])
        y, x = arr[:, 0], arr[:, 1]
        xm = x.mean(); den = ((x - xm) ** 2).sum()
        stat[b] = np.nan if den == 0 else ((x - xm) * (y - y.mean())).sum() / den
    stat = stat[np.isfinite(stat)]
    lo = float((stat <= 0).mean()); hi = float((stat >= 0).mean())
    return {"n_draws": len(stat), "mean_of_draws": float(stat.mean()),
            "sd_of_draws": float(stat.std(ddof=1)),
            "ci_lo": float(np.percentile(stat, 2.5)), "ci_hi": float(np.percentile(stat, 97.5)),
            "p_two_sided": float(min(1.0, 2 * min(lo, hi)))}
