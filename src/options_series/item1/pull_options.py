"""Pulls from OptionMetrics and CBOE, and loaders for what they write to disk."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import wrds

from options_series.db import query
from options_series.item1.config import (
    BENCHMARK,
    COMMON_END,
    COMMON_START,
    MAX_DAYS_TO_EXPIRY,
    MIN_DAYS_TO_EXPIRY,
    NODES,
    PULL_SPANS,
    RAW_DIR,
    SECIDS,
)

LOGGER = logging.getLogger(__name__)

OPTION_COLUMNS = (
    "date, exdate, cp_flag, strike_price, best_bid, best_offer, forward_price, "
    "am_settlement, impl_volatility, volume, open_interest, ss_flag, root, suffix, "
    "contract_size"
)
NUMERIC_OPTION_COLUMNS = (
    "best_bid",
    "best_offer",
    "forward_price",
    "am_settlement",
    "impl_volatility",
    "volume",
    "open_interest",
    "contract_size",
)
ATM_SURFACE_PATH = RAW_DIR / "atm_surface.parquet"
SECURITY_RETURNS_PATH = RAW_DIR / "security_returns.parquet"
ZERO_CURVE_PATH = RAW_DIR / "zero_curve.parquet"
VIX_PATH = RAW_DIR / "vix.parquet"


def option_years(ticker: str) -> range:
    """Calendar years whose OptionMetrics partitions the pull span of a ticker touches."""
    start, end = PULL_SPANS[ticker]
    return range(int(start[:4]), int(end[:4]) + 1)


def option_quotes_path(ticker: str, year: int) -> Path:
    """Parquet path for one ticker's option quotes in one year partition."""
    return RAW_DIR / "option_quotes" / f"{ticker}_{year}.parquet"


def pull_option_quotes(
    connection: wrds.Connection, ticker: str, year: int
) -> pd.DataFrame:
    """Option quotes for one ticker and year, 7 to 200 days to expiry, strike in points."""
    start, end = PULL_SPANS[ticker]
    sql = (
        f"select {OPTION_COLUMNS} from optionm.opprcd{year} "
        "where secid = %(secid)s and date between %(start)s and %(end)s "
        f"and exdate >= date + {MIN_DAYS_TO_EXPIRY} "
        f"and exdate <= date + {MAX_DAYS_TO_EXPIRY}"
    )
    quotes = query(
        connection, sql, {"secid": float(SECIDS[ticker]), "start": start, "end": end}
    )
    quotes["strike_price"] = quotes["strike_price"] / 1000.0
    quotes["date"] = pd.to_datetime(quotes["date"])
    quotes["exdate"] = pd.to_datetime(quotes["exdate"])
    for column in NUMERIC_OPTION_COLUMNS:
        quotes[column] = pd.to_numeric(quotes[column], errors="coerce")
    return quotes


def pull_atm_surface(connection: wrds.Connection) -> pd.DataFrame:
    """Implied volatility of the 50-delta call and minus-50-delta put at each node."""
    frames = []
    for ticker, secid in SECIDS.items():
        start, end = PULL_SPANS[ticker]
        for year in option_years(ticker):
            sql = (
                "select date, days, delta, cp_flag, impl_volatility "
                f"from optionm.vsurfd{year} "
                "where secid = %(secid)s and date between %(start)s and %(end)s "
                f"and days in {tuple(NODES)} and delta in (50, -50)"
            )
            rows = query(
                connection, sql, {"secid": float(secid), "start": start, "end": end}
            )
            rows["ticker"] = ticker
            rows["secid"] = secid
            frames.append(rows)
    surface = pd.concat(frames, ignore_index=True)
    surface["date"] = pd.to_datetime(surface["date"])
    for column in ("days", "delta", "impl_volatility"):
        surface[column] = pd.to_numeric(surface[column], errors="coerce")
    at_the_money = surface[
        ((surface.delta == 50) & (surface.cp_flag == "C"))
        | ((surface.delta == -50) & (surface.cp_flag == "P"))
    ]
    wide = at_the_money.pivot_table(
        index=["ticker", "secid", "date", "days"],
        columns="cp_flag",
        values="impl_volatility",
        aggfunc="first",
    ).reset_index()
    wide = wide.rename(columns={"days": "node", "C": "iv_call_50", "P": "iv_put_50"})
    wide["node"] = wide["node"].astype(int)
    return wide[["ticker", "secid", "date", "node", "iv_call_50", "iv_put_50"]]


def pull_security_returns(connection: wrds.Connection) -> pd.DataFrame:
    """Daily total return, as a decimal, for each underlying over its pull span."""
    frames = []
    for ticker, secid in SECIDS.items():
        start, end = PULL_SPANS[ticker]
        for year in option_years(ticker):
            sql = (
                f"select date, return from optionm.secprd{year} "
                "where secid = %(secid)s and date between %(start)s and %(end)s"
            )
            rows = query(
                connection, sql, {"secid": float(secid), "start": start, "end": end}
            )
            rows["ticker"] = ticker
            rows["secid"] = secid
            frames.append(rows)
    returns = pd.concat(frames, ignore_index=True)
    returns["date"] = pd.to_datetime(returns["date"])
    returns["return"] = pd.to_numeric(returns["return"], errors="coerce")
    returns = returns.sort_values(["ticker", "date"]).reset_index(drop=True)
    return returns[["ticker", "secid", "date", "return"]]


def pull_zero_curve(connection: wrds.Connection) -> pd.DataFrame:
    """OptionMetrics zero curve: rate in percent per annum by date and days."""
    curve = query(
        connection, "select date, days, rate from optionm.zerocd order by date, days"
    )
    curve["date"] = pd.to_datetime(curve["date"])
    return curve


def pull_vix(connection: wrds.Connection) -> pd.DataFrame:
    """Daily VIX close in volatility points over the common window."""
    vix = query(
        connection,
        "select date, vix from cboe.cboe where date between %(start)s and %(end)s "
        "order by date",
        {"start": COMMON_START, "end": COMMON_END},
    )
    vix["date"] = pd.to_datetime(vix["date"])
    vix["vix"] = pd.to_numeric(vix["vix"])
    return vix


def pull_all_options(connection: wrds.Connection) -> None:
    """Pull every option-side input and write it under the raw data directory."""
    (RAW_DIR / "option_quotes").mkdir(parents=True, exist_ok=True)
    for ticker in SECIDS:
        for year in option_years(ticker):
            quotes = pull_option_quotes(connection, ticker, year)
            quotes.to_parquet(
                option_quotes_path(ticker, year), index=False, compression="zstd"
            )
            LOGGER.info("option quotes %s %d: %d rows", ticker, year, len(quotes))
    pull_atm_surface(connection).to_parquet(ATM_SURFACE_PATH, index=False)
    pull_security_returns(connection).to_parquet(SECURITY_RETURNS_PATH, index=False)
    pull_zero_curve(connection).to_parquet(ZERO_CURVE_PATH, index=False)
    pull_vix(connection).to_parquet(VIX_PATH, index=False)


def load_option_quotes(ticker: str, year: int) -> pd.DataFrame:
    """Option quotes for one ticker and year partition from disk."""
    return pd.read_parquet(option_quotes_path(ticker, year))


def load_atm_surface() -> pd.DataFrame:
    """At-the-money call and put implied volatility per underlying, date and node."""
    surface = pd.read_parquet(ATM_SURFACE_PATH)
    surface["node"] = surface["node"].astype(int)
    return surface


def load_security_returns() -> pd.DataFrame:
    """Daily returns per underlying from disk."""
    return pd.read_parquet(SECURITY_RETURNS_PATH)


def load_zero_curve() -> pd.DataFrame:
    """Zero curve from disk."""
    return pd.read_parquet(ZERO_CURVE_PATH)


def load_vix() -> pd.DataFrame:
    """VIX close from disk."""
    return pd.read_parquet(VIX_PATH)


def benchmark_trade_dates(returns: pd.DataFrame) -> pd.DatetimeIndex:
    """SPX trade dates in the common window, which define coverage for every series."""
    dates = returns.loc[
        (returns.ticker == BENCHMARK)
        & (returns.date >= COMMON_START)
        & (returns.date <= COMMON_END),
        "date",
    ]
    return pd.DatetimeIndex(pd.to_datetime(dates).sort_values().unique())
