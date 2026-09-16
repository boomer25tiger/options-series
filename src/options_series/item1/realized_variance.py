"""Realized variance (spec section 6.3), the variance premium measures (section 6.4)
and the non-overlapping sampling grid (section 7)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from options_series.item1.config import (
    COMMON_END,
    COMMON_START,
    STRIKE_FLOOR,
    TRADING_DAYS_PER_YEAR,
    WINDOW_TRADING_DAYS,
)
from options_series.item1.model_free_variance import OK

PREMIUM_COLUMNS = [
    "secid",
    "ticker",
    "date",
    "node",
    "implied_var_model_free",
    "implied_var_atm",
    "realized_var",
    "log_ratio_model_free",
    "log_ratio_atm",
    "var_difference_model_free",
    "var_difference_atm",
    "drop_code",
    "year",
]


def realized_variance(returns: pd.DataFrame) -> pd.DataFrame:
    """Annualised realized variance over trading days t+1 to t+h: the sum of squared log
    returns times 252/h, missing where any return in the window is missing."""
    frames = []
    for ticker, history in returns.sort_values("date").groupby("ticker"):
        history = history.reset_index(drop=True)
        log_returns = np.log1p(history["return"].values.astype(float))
        observed = ~np.isnan(log_returns)
        squared = np.where(observed, log_returns * log_returns, 0.0)
        count = len(history)
        cumulative_squared = np.concatenate([[0.0], np.cumsum(squared)])
        cumulative_observed = np.concatenate([[0], np.cumsum(observed.astype(int))])
        start = np.arange(count)
        for node, window in WINDOW_TRADING_DAYS.items():
            end = start + window
            in_sample = end < count
            window_sum = np.full(count, np.nan)
            window_observed = np.zeros(count, dtype=int)
            window_sum[in_sample] = (
                cumulative_squared[end[in_sample] + 1]
                - cumulative_squared[start[in_sample] + 1]
            )
            window_observed[in_sample] = (
                cumulative_observed[end[in_sample] + 1]
                - cumulative_observed[start[in_sample] + 1]
            )
            complete = in_sample & (window_observed == window)
            realized_var = np.where(
                complete, window_sum * (TRADING_DAYS_PER_YEAR / window), np.nan
            )
            frames.append(
                pd.DataFrame(
                    {
                        "ticker": ticker,
                        "date": history.date.values,
                        "node": node,
                        "realized_var": realized_var,
                    }
                )
            )
    return pd.concat(frames, ignore_index=True)


def variance_premium(
    model_free: pd.DataFrame, atm: pd.DataFrame, realized: pd.DataFrame
) -> pd.DataFrame:
    """Daily log(IV²/RV) and IV² − RV, in annualised variance, for the model-free and
    the at-the-money implied variance."""
    primary = model_free[model_free.strike_floor == STRIKE_FLOOR]
    premium = (
        primary[["secid", "ticker", "date", "node", "implied_var", "drop_code"]]
        .rename(columns={"implied_var": "implied_var_model_free"})
        .merge(
            atm[["ticker", "date", "node", "implied_var_atm"]],
            on=["ticker", "date", "node"],
            how="left",
        )
        .merge(
            realized[["ticker", "date", "node", "realized_var"]],
            on=["ticker", "date", "node"],
            how="left",
        )
    )
    premium.loc[premium.drop_code != OK, "implied_var_model_free"] = np.nan
    premium.loc[premium.realized_var <= 0, "realized_var"] = np.nan
    premium["log_ratio_model_free"] = np.log(
        premium.implied_var_model_free / premium.realized_var
    )
    premium["log_ratio_atm"] = np.log(premium.implied_var_atm / premium.realized_var)
    premium["var_difference_model_free"] = (
        premium.implied_var_model_free - premium.realized_var
    )
    premium["var_difference_atm"] = premium.implied_var_atm - premium.realized_var
    premium["year"] = premium.date.dt.year
    return premium[PREMIUM_COLUMNS]


def non_overlapping_grid(returns: pd.DataFrame, premium: pd.DataFrame) -> pd.DataFrame:
    """Premium sampled every h trading days from the first common-window trade date."""
    frames = []
    for ticker, history in returns.sort_values("date").groupby("ticker"):
        dates = history.date.reset_index(drop=True)
        window_dates = dates[
            (dates >= pd.Timestamp(COMMON_START)) & (dates <= pd.Timestamp(COMMON_END))
        ]
        first, last = window_dates.index[0], window_dates.index[-1]
        for node, window in WINDOW_TRADING_DAYS.items():
            picks = list(range(first, last + 1, window))
            frames.append(
                pd.DataFrame(
                    {
                        "ticker": ticker,
                        "node": node,
                        "date": dates.iloc[picks].values,
                        "grid_index": range(len(picks)),
                    }
                )
            )
    grid = pd.concat(frames, ignore_index=True)
    return grid.merge(premium, on=["ticker", "date", "node"], how="left")
