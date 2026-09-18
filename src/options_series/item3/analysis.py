"""Replication analysis (amendment A1's open question) and the stress, exploratory and
remaining reporting of spec sections 11 and 12.

Choices the spec and its amendments leave open, fixed before this analysis ran.
- r is the listed-strike K over the flat-tail K of section 8 on the entry date. The
  implied bias in the mean return is the mean over cycles of (RV / K_flat)(1 - 1/r),
  the listed-strike target less the flat-tail target, and also reported at RV = K_flat
  as 1 - E[1/r]. A positive bias raises the measured return, in the seller's favour.
- eta is the realized return at k = 0 and c = 0 with borrow at the zero rate, less its
  target. The strip's spec target is 1 - RV/K; because RV annualizes by 252 over trading
  days while K annualizes by calendar time, the total-variance target
  1 - (sum of squared log returns)/(K T) is reported beside it. The straddle's targets
  are the section 12 approximation 1 - sqrt(RV)/sigma_ATM and its total-variance form.
- The loss split of a split cycle uses entry Greeks: gamma from -1/2 of the position's
  entry gamma times each daily squared price move, theta from the entry theta over the
  elapsed calendar time, vega from each leg's entry vega times its implied volatility
  change to the last day it was quoted, and a residual.
- The jump term of the log contract is 2(R - ln(1 + R)) - ln(1 + R)^2 summed over daily
  simple returns R; the hedge accrual gap is the prior-close share value times R - ln(1+R).
- Drawdowns and recovery run on the pooled daily marked equity. Recovery counts trading
  days from the trough until equity regains the prior peak. Daily Sharpe annualizes the
  mean daily equity change by the square root of 252, its Newey-West error at the lag of
  section 9's rule on the daily count.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pandas as pd
from scipy import stats

from options_series.item1.inference import hac_mean_test
from options_series.item3.samples import pooled_returns
from options_series.item3.tests import breakeven

HOLDOUT_YEARS = (2022, 2023, 2024, 2025)
STRIKE_BUCKETS = (0, 1, 2, 3, 4, 5, 6, 10, 20, np.inf)


def _describe(values: pd.Series) -> dict[str, float]:
    """Mean, median, standard deviation and the 5th and 95th percentiles."""
    values = values.dropna()
    return {
        "n": len(values),
        "mean": values.mean(),
        "median": values.median(),
        "sd": values.std(),
        "p05": values.quantile(0.05),
        "p95": values.quantile(0.95),
    }


def replication_populations(strip: pd.DataFrame) -> pd.DataFrame:
    """D1: the ratio r and the empirical E[1/r] on rule-2-passing and failing strip
    cycles, with the implied bias in the mean return."""
    rows = []
    strip = strip.assign(
        k_flat=strip.k_strip / strip.shortfall_ratio,
        inverse=1.0 / strip.shortfall_ratio,
    )
    strip["bias"] = strip.rv / strip.k_flat * (1.0 - strip.inverse)
    for name, group in (
        ("passes rule 2", strip[strip.floor_pass]),
        ("fails rule 2", strip[~strip.floor_pass]),
        ("every computable cycle", strip),
    ):
        described = _describe(group.shortfall_ratio)
        rows.append(
            {
                "population": name,
                **{f"r_{key}": value for key, value in described.items()},
                "mean_inverse_r": group.inverse.mean(),
                "bias_at_rv_equal_k": 1.0 - group.inverse.mean(),
                "bias_mean_return": group.bias.mean(),
                "bias_se": group.bias.std() / np.sqrt(group.bias.count()),
                "direction": "seller's favour"
                if group.bias.mean() > 0
                else "against the seller",
            }
        )
    return pd.DataFrame(rows)


def add_eta(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-cycle replication error against the spec target and the total-variance
    target."""
    realized = frame["return_k0_c0_borrow0"]
    total = frame.sum_squared_log_returns / frame.years_to_expiration
    strip = frame.arm == "strip"
    target = np.where(
        strip, 1 - frame.rv / frame.k_strip, 1 - np.sqrt(frame.rv) / frame.sigma_atm
    )
    target_total = np.where(
        strip, 1 - total / frame.k_strip, 1 - np.sqrt(total) / frame.sigma_atm
    )
    return frame.assign(
        target=target,
        target_total=target_total,
        eta=realized - target,
        eta_total=realized - target_total,
    )


def eta_table(frame: pd.DataFrame) -> pd.DataFrame:
    """D2: mean eta with its Newey-West standard error per fund and arm, per population
    for the strip."""
    rows = []
    for (arm, population), group in frame.groupby(["arm", "population"]):
        for ticker, subset in [*group.groupby("ticker"), ("ALL", group)]:
            row = {"arm": arm, "population": population, "ticker": ticker}
            for name in ("eta", "eta_total"):
                values = subset.sort_values("entry")[name].dropna().to_numpy(float)
                if len(values) > 5:
                    hac = hac_mean_test(values, 4)
                    row.update(
                        {
                            f"{name}_n": hac["n"],
                            f"{name}_mean": hac["estimate"],
                            f"{name}_se_newey_west": hac["se_newey_west"],
                        }
                    )
            rows.append(row)
    return pd.DataFrame(rows)


def eta_comparison(strip: pd.DataFrame) -> pd.DataFrame:
    """D2: Welch comparison of mean eta between the rule-2 populations."""
    rows = []
    passing, failing = strip[strip.floor_pass], strip[~strip.floor_pass]
    for name in ("eta", "eta_total"):
        a, b = passing[name].dropna(), failing[name].dropna()
        test = stats.ttest_ind(a, b, equal_var=False)
        rows.append(
            {
                "measure": name,
                "mean_passing": a.mean(),
                "mean_failing": b.mean(),
                "difference": a.mean() - b.mean(),
                "welch_t": float(test.statistic),
                "p_two_sided": float(test.pvalue),
                "n_passing": len(a),
                "n_failing": len(b),
            }
        )
    return pd.DataFrame(rows)


def by_strike_count(strip: pd.DataFrame) -> pd.DataFrame:
    """D3: r and eta against the smaller strike count of the two sides of K_0."""
    fewer = np.minimum(strip.strip_puts, strip.strip_calls)
    labels = [
        f"{int(low)}" if high - low == 1 else f"{int(low)} to {high - 1:g}"
        for low, high in pairwise(STRIKE_BUCKETS)
    ]
    buckets = pd.cut(fewer, STRIKE_BUCKETS, right=False, labels=labels)
    return (
        strip.assign(fewer_side_strikes=buckets)
        .groupby("fewer_side_strikes", observed=True)
        .agg(
            cycles=("shortfall_ratio", "size"),
            r_mean=("shortfall_ratio", "mean"),
            r_median=("shortfall_ratio", "median"),
            r_sd=("shortfall_ratio", "std"),
            eta_mean=("eta", "mean"),
            eta_total_mean=("eta_total", "mean"),
            eta_sd=("eta", "std"),
        )
        .reset_index()
    )


def split_cycles(
    frame: pd.DataFrame,
    equity: pd.DataFrame,
    hedges: pd.DataFrame,
    quotes: pd.DataFrame,
    legs: pd.DataFrame,
    prices: pd.DataFrame,
    primary: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """E1: every truncated arm-cycle's summary with the entry-Greek loss split, the jump
    term and the hedge accrual gap, and its daily equity and hedge trades."""
    truncated = frame[frame.truncated]
    closes = prices.pivot(index="date", columns="ticker", values="close")
    factors = prices.pivot(index="date", columns="ticker", values="cfadj")
    summary, daily = [], []
    for _, cycle in truncated.iterrows():
        arm_legs = legs[
            (legs.ticker == cycle.ticker)
            & (legs.cycle == cycle.cycle)
            & (legs.arm == cycle.arm)
        ]
        entry_rows = quotes[
            quotes.optionid.isin(arm_legs.optionid) & (quotes.date == cycle.entry)
        ].set_index("optionid")
        held = quotes[
            quotes.optionid.isin(arm_legs.optionid)
            & (quotes.date >= cycle.entry)
            & (quotes.date <= cycle.truncation_date)
        ]
        last_iv = held.dropna(subset=["impl_volatility"]).sort_values("date")
        last_iv = last_iv.groupby("optionid").impl_volatility.last()
        weights = arm_legs.set_index("optionid").weight.astype(float)
        if cycle.arm == "strip":
            contracts = (
                weights * 2.0 / (cycle.years_to_expiration * cycle.k_strip) / 100.0
            )
        else:
            contracts = weights * 0 + 1.0
        greeks = entry_rows.reindex(contracts.index)
        gamma = -float((contracts * 100.0 * greeks.gamma).sum())
        theta = -float((contracts * 100.0 * greeks.theta).sum())
        iv_change = last_iv.reindex(contracts.index) - greeks.impl_volatility
        vega_pnl = -float((contracts * 100.0 * greeks.vega * iv_change).sum())
        path_dates = pd.DatetimeIndex(
            sorted(
                hedges[
                    (hedges.ticker == cycle.ticker)
                    & (hedges.cycle == cycle.cycle)
                    & (hedges.arm == cycle.arm)
                ].date
            )
        )
        path_dates = path_dates[path_dates <= cycle.truncation_date]
        close = closes[cycle.ticker].reindex(path_dates).to_numpy(float)
        moves = np.diff(close)
        gamma_pnl = 0.5 * gamma * float(np.sum(moves**2))
        elapsed = (cycle.truncation_date - cycle.entry).days / 365.0
        theta_pnl = theta * elapsed
        total = cycle.return_k0_c0 * cycle.premium
        hedge = (
            hedges[
                (hedges.ticker == cycle.ticker)
                & (hedges.cycle == cycle.cycle)
                & (hedges.arm == cycle.arm)
            ]
            .set_index("date")
            .hedge_shares.reindex(path_dates)
            .to_numpy(float)
        )
        adjusted = (closes[cycle.ticker] * factors[cycle.ticker]).reindex(
            pd.DatetimeIndex(sorted(set(path_dates)))
        )
        simple = adjusted.pct_change().dropna().to_numpy(float)
        logs = np.log1p(simple)
        accrual_gap = float(np.sum(hedge[:-1] * close[:-1] * (simple - logs)))
        full = closes[cycle.ticker].loc[cycle.entry : cycle.expiration]
        full_adjusted = (
            (full * factors[cycle.ticker].loc[full.index]).pct_change().dropna()
        )
        full_logs = np.log1p(full_adjusted)
        summary.append(
            {
                "ticker": cycle.ticker,
                "cycle": cycle.cycle,
                "arm": cycle.arm,
                "entry": cycle.entry,
                "expiration": cycle.expiration,
                "truncation_date": cycle.truncation_date,
                "trading_days_held": cycle.trading_days_held,
                "return_to_truncation_k0_c0": cycle.return_k0_c0,
                "return_to_truncation_primary": cycle[primary],
                "gamma_component": gamma_pnl / cycle.premium,
                "theta_component": theta_pnl / cycle.premium,
                "vega_component": vega_pnl / cycle.premium,
                "residual": (total - gamma_pnl - theta_pnl - vega_pnl) / cycle.premium,
                "jump_term_to_truncation": float(np.sum(2 * (simple - logs) - logs**2)),
                "jump_term_full_cycle": float(
                    np.sum(2 * (full_adjusted - full_logs) - full_logs**2)
                ),
                "sum_squared_log_returns_full_cycle": float(np.sum(full_logs**2)),
                "hedge_accrual_simple_minus_log": accrual_gap / cycle.premium,
            }
        )
        path = equity[
            (equity.ticker == cycle.ticker)
            & (equity.cycle == cycle.cycle)
            & (equity.arm == cycle.arm)
            & (equity.marking == "half offer")
            & (equity.k == 0.0)
            & (equity.c == 0.0)
            & (equity.date <= cycle.truncation_date)
        ].sort_values("date")
        trades = np.diff(np.concatenate([[0.0], hedge]))
        daily.append(
            pd.DataFrame(
                {
                    "ticker": cycle.ticker,
                    "cycle": cycle.cycle,
                    "arm": cycle.arm,
                    "date": path_dates,
                    "close": close,
                    "hedge_shares": hedge,
                    "hedge_trade_shares": trades,
                    "equity_k0_c0": path.equity.to_numpy(float)[: len(path_dates)],
                }
            )
        )
    return pd.DataFrame(summary), (
        pd.concat(daily, ignore_index=True) if daily else pd.DataFrame()
    )


def drawdown(series: pd.DataFrame) -> dict[str, object]:
    """Maximum drawdown of a daily equity series, its dates and the recovery time in
    trading days, unrecovered when equity never regains the prior peak."""
    values = series.equity.to_numpy(float)
    dates = pd.DatetimeIndex(series.date)
    peaks = np.maximum.accumulate(values)
    depth = values - peaks
    trough = int(np.argmin(depth))
    peak = int(np.argmax(values[: trough + 1]))
    after = np.flatnonzero(values[trough:] >= values[peak])
    recovered = len(after) > 0
    return {
        "max_drawdown": float(depth[trough]),
        "peak_date": dates[peak],
        "trough_date": dates[trough],
        "recovery_date": dates[trough + after[0]] if recovered else pd.NaT,
        "recovery_trading_days": int(after[0]) if recovered else np.nan,
        "recovery": "recovered" if recovered else "unrecovered by 2025-08-29",
    }


def daily_sharpe(series: pd.DataFrame) -> dict[str, float]:
    """Annualized Sharpe ratio of daily equity changes with its Newey-West error."""
    changes = np.diff(series.sort_values("date").equity.to_numpy(float))
    lag = int(np.floor(4 * (len(changes) / 100) ** (2 / 9)))
    hac = hac_mean_test(changes, lag)
    scale = np.sqrt(252.0) / changes.std(ddof=1)
    return {
        "daily_sharpe": hac["estimate"] * scale,
        "daily_sharpe_se_newey_west": hac["se_newey_west"] * scale,
        "daily_sharpe_lag": lag,
    }


def worst_windows(pooled: pd.DataFrame, name: str) -> dict[str, object]:
    """Worst single pooled cycle and worst rolling three-cycle sum."""
    values = pooled[name].to_numpy(float)
    rolling = pd.Series(values).rolling(3).sum()
    worst = int(np.argmin(values))
    worst_three = int(rolling.idxmin())
    return {
        "worst_cycle": float(values[worst]),
        "worst_cycle_entry": pooled.entry.iloc[worst],
        "worst_three_cycles": float(rolling.min()),
        "worst_three_cycles_last_entry": pooled.entry.iloc[worst_three],
    }


def named_windows(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    """E3: cycle returns in the named stress windows of section 11 and the pre-named
    April 2020 cycle."""
    windows = {
        "autumn 2008": (("GLD", "USO", "UNG"), "2008-09-01", "2008-11-30"),
        "March 2020": (("GLD", "SLV", "USO", "UNG"), "2020-02-01", "2020-03-31"),
        "April 2020": (("GLD", "SLV", "USO", "UNG"), "2020-04-01", "2020-04-30"),
        "2022 UNG": (("UNG",), "2022-01-01", "2022-12-31"),
    }
    rows = []
    for window, (tickers, start, end) in windows.items():
        within = frame[
            frame.ticker.isin(tickers)
            & (frame.expiration >= pd.Timestamp(start))
            & (frame.entry <= pd.Timestamp(end))
        ]
        for (ticker, arm), group in within.groupby(["ticker", "arm"]):
            for _, cycle in group.iterrows():
                rows.append(
                    {
                        "window": window,
                        "ticker": ticker,
                        "arm": arm,
                        "entry": cycle.entry,
                        "expiration": cycle.expiration,
                        "excluded_by": cycle.excluded_by,
                        "truncated": cycle.truncated,
                        "return_k0_c0": cycle.return_k0_c0,
                        "return_primary": cycle[name],
                        "rv": cycle.rv,
                        "k_strip": cycle.k_strip,
                        "sigma_atm_squared": cycle.sigma_atm**2,
                    }
                )
    return pd.DataFrame(rows)


def cost_drift(
    frame: pd.DataFrame, columns: dict[float, tuple[str, str]]
) -> pd.DataFrame:
    """E4: breakeven k by calendar year and arm on the pooled series, and the entry
    half-spread share of premium by year, with holdout years marked."""
    rows = []
    for (arm, year), group in frame.groupby(["arm", "entry_year"]):
        row = {
            "arm": arm,
            "entry_year": year,
            "holdout": year in HOLDOUT_YEARS,
            "cycles": len(group),
            "half_spread_share_median": group.option_cost_share.median(),
            "half_spread_share_mean": group.option_cost_share.mean(),
        }
        for c, (zero, one) in columns.items():
            pooled_zero = pooled_returns(group[["ticker", "entry", zero]], zero)
            pooled_one = pooled_returns(group[["ticker", "entry", one]], one)
            if len(pooled_zero) == 0:
                pooled_zero = group[["entry", zero]]
                pooled_one = group[["entry", one]]
            mean_zero, mean_one = pooled_zero[zero].mean(), pooled_one[one].mean()
            row[f"mean_k0_c{c * 1e4:g}"] = mean_zero
            row[f"mean_k1_c{c * 1e4:g}"] = mean_one
            row[f"breakeven_k_c{c * 1e4:g}"] = breakeven(mean_zero, mean_one)
        rows.append(row)
    by_fund = (
        frame.groupby(["arm", "ticker", "entry_year"])
        .option_cost_share.median()
        .rename("half_spread_share_median")
        .reset_index()
        .assign(holdout=lambda data: data.entry_year.isin(HOLDOUT_YEARS))
    )
    return pd.DataFrame(rows), by_fund


def convexity(frame: pd.DataFrame, name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """E5: strip minus straddle return per cycle against u and g, the theoretical
    u - u^2/g, and the ex-ante wing gap log g; with a u-by-g table."""
    strip = frame[frame.arm == "strip"].set_index(["ticker", "cycle"])
    straddle = frame[frame.arm == "straddle"].set_index(["ticker", "cycle"])
    both = strip.join(straddle[[name]], rsuffix="_straddle", how="inner")
    both = both.assign(
        difference=both[name] - both[f"{name}_straddle"],
        u=np.sqrt(both.rv) / both.sigma_atm,
        g=both.k_strip / both.sigma_atm**2,
    )
    both["theory"] = both.u - both.u**2 / both.g
    both["wing_gap"] = np.log(both.g)
    series = both.reset_index()[
        [
            "ticker",
            "cycle",
            "entry",
            "window",
            name,
            f"{name}_straddle",
            "difference",
            "u",
            "g",
            "theory",
            "wing_gap",
        ]
    ]
    series["u_bin"] = pd.qcut(series.u, 5)
    series["g_bin"] = pd.qcut(series.g, 3)
    table = (
        series.groupby(["u_bin", "g_bin"], observed=True)
        .agg(
            cycles=("difference", "size"),
            difference_mean=("difference", "mean"),
            theory_mean=("theory", "mean"),
            wing_gap_mean=("wing_gap", "mean"),
        )
        .reset_index()
    )
    table["u_bin"] = table.u_bin.astype(str)
    table["g_bin"] = table.g_bin.astype(str)
    series["u_bin"] = series.u_bin.astype(str)
    series["g_bin"] = series.g_bin.astype(str)
    return series, table
