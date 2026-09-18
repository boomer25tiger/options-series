"""Pulls from OptionMetrics for item 3 and loaders for what they write to disk.

The secprd pull brings prices with the cumulative adjustment factor for the
corporate-action record and the hedge. A scan of opprcd finds each fund's first option
date, which fixes its first cycle, and a daily count of opprcd rows by ss_flag and
contract size across every expiry completes the corporate-action record. The main pull
takes every contract on each cycle's expiry from the trading day before entry through
expiration, with optionid and every Greek. Item 1's cache supplies the zero curve and the
at-the-money surface nodes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import wrds

from options_series.db import copy_query_to_csv, query
from options_series.item3.config import (
    CYCLE_QUOTES_DIR,
    FEED_END,
    ITEM1_ATM_SURFACE_PATH,
    ITEM1_ZERO_CURVE_PATH,
    OPTION_START_SCAN_YEARS,
    OPTION_YEARS,
    RAW_DIR,
    SECIDS,
    SECPRD_YEARS,
)

LOGGER = logging.getLogger(__name__)

PRICES_PATH = RAW_DIR / "secprd.parquet"
OPTION_STARTS_PATH = RAW_DIR / "option_starts.json"
SS_FLAG_COUNTS_PATH = RAW_DIR / "ss_flag_counts.parquet"
CYCLE_QUOTE_SCHEMA = {
    "secid": pa.int32(),
    "date": pa.date32(),
    "exdate": pa.date32(),
    "optionid": pa.int64(),
    "cp_flag": pa.string(),
    "strike_price": pa.float64(),
    "best_bid": pa.float64(),
    "best_offer": pa.float64(),
    "impl_volatility": pa.float64(),
    "delta": pa.float64(),
    "gamma": pa.float64(),
    "vega": pa.float64(),
    "theta": pa.float64(),
    "ss_flag": pa.string(),
    "contract_size": pa.float64(),
    "am_settlement": pa.float64(),
    "expiry_indicator": pa.string(),
    "forward_price": pa.float64(),
    "cfadj": pa.float64(),
    "root": pa.string(),
    "suffix": pa.string(),
    "volume": pa.float64(),
    "open_interest": pa.float64(),
}
CYCLE_QUOTE_COLUMNS = ", ".join(f"o.{column}" for column in CYCLE_QUOTE_SCHEMA)


def pull_prices(connection: wrds.Connection) -> pd.DataFrame:
    """Daily close, total return, cumulative adjustment factors and shares outstanding
    for each fund from its first secprd record through the feed end."""
    frames = []
    for ticker, secid in SECIDS.items():
        for year in SECPRD_YEARS:
            rows = query(
                connection,
                "select secid, date, close, return, cfadj, cfret, shrout "
                f"from optionm.secprd{year} "
                "where secid = %(secid)s and date <= %(end)s",
                {"secid": float(secid), "end": FEED_END},
            )
            if len(rows):
                rows["ticker"] = ticker
                frames.append(rows)
    prices = pd.concat(frames, ignore_index=True)
    prices["date"] = pd.to_datetime(prices["date"])
    prices["secid"] = prices["secid"].astype(int)
    for column in ("close", "return", "cfadj", "cfret", "shrout"):
        prices[column] = pd.to_numeric(prices[column], errors="coerce").astype(float)
    return prices.sort_values(["ticker", "date"]).reset_index(drop=True)


def pull_option_starts(connection: wrds.Connection) -> dict[str, str]:
    """Each fund's first opprcd date, scanning year partitions from the earliest."""
    starts = {}
    for ticker, secid in SECIDS.items():
        for year in OPTION_START_SCAN_YEARS:
            first = query(
                connection,
                f"select min(date) as first_date from optionm.opprcd{year} "
                "where secid = %(secid)s",
                {"secid": float(secid)},
            ).first_date.iloc[0]
            if first is not None and not pd.isna(first):
                starts[ticker] = str(pd.Timestamp(first).date())
                break
    return starts


def pull_ss_flag_counts(connection: wrds.Connection) -> pd.DataFrame:
    """Daily opprcd row counts per fund by ss_flag and contract size, every expiry."""
    frames = []
    for ticker, secid in SECIDS.items():
        for year in OPTION_YEARS:
            rows = query(
                connection,
                "select date, ss_flag, contract_size, count(*) as rows "
                f"from optionm.opprcd{year} where secid = %(secid)s "
                "group by date, ss_flag, contract_size",
                {"secid": float(secid)},
            )
            if len(rows):
                rows["ticker"] = ticker
                frames.append(rows)
    counts = pd.concat(frames, ignore_index=True)
    counts["date"] = pd.to_datetime(counts["date"])
    counts["contract_size"] = pd.to_numeric(counts["contract_size"]).astype(float)
    counts["rows"] = pd.to_numeric(counts["rows"]).astype(int)
    return counts.sort_values(["ticker", "date", "ss_flag"]).reset_index(drop=True)


def cycle_quotes_path(ticker: str, year: int) -> Path:
    """Parquet path for one fund's cycle-expiry quotes in one year partition."""
    return CYCLE_QUOTES_DIR / f"{ticker}_{year}.parquet"


def _cycle_windows(cycles: pd.DataFrame, year: int) -> str:
    """VALUES rows pairing each candidate exdate with the date span the pull covers for
    it, for the cycles whose span touches the year. The rows format dates from the
    calendar alone, so no outside input reaches the SQL."""
    rows = []
    for cycle in cycles.itertuples():
        if cycle.previous_expiration.year > year or cycle.expiration.year < year:
            continue
        for exdate in cycle.exdate_candidates:
            rows.append(
                f"(date '{exdate.date()}', date '{cycle.previous_expiration.date()}', "
                f"date '{cycle.expiration.date()}')"
            )
    return ", ".join(rows)


def pull_cycle_quotes_year(
    connection: wrds.Connection, ticker: str, year: int, cycles: pd.DataFrame
) -> int:
    """Stream every contract on the fund's cycle expiries in one year partition, from the
    trading day before entry through expiration, through CSV into parquet and return the
    row count."""
    windows = _cycle_windows(cycles[cycles.ticker == ticker], year)
    if not windows:
        return 0
    CYCLE_QUOTES_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = CYCLE_QUOTES_DIR / f"{ticker}_{year}.csv"
    copy_query_to_csv(
        connection,
        f"select {CYCLE_QUOTE_COLUMNS} from optionm.opprcd{year} o "
        f"join (values {windows}) as c(exdate, first_date, last_date) "
        "on o.exdate = c.exdate "
        "where o.secid = %(secid)s and o.date between c.first_date and c.last_date",
        {"secid": float(SECIDS[ticker])},
        csv_path,
    )
    table = pacsv.read_csv(
        csv_path,
        convert_options=pacsv.ConvertOptions(
            column_types=CYCLE_QUOTE_SCHEMA, strings_can_be_null=True
        ),
    )
    for column in ("date", "exdate"):
        table = table.set_column(
            table.schema.get_field_index(column),
            column,
            table[column].cast(pa.timestamp("ns")),
        )
    pq.write_table(table, cycle_quotes_path(ticker, year), compression="zstd")
    csv_path.unlink()
    return table.num_rows


def pull_calendar_inputs(connection: wrds.Connection) -> None:
    """Pull the inputs the cycle calendar and the corporate-action record need and write
    them under the raw directory."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    pull_prices(connection).to_parquet(PRICES_PATH, index=False)
    OPTION_STARTS_PATH.write_text(json.dumps(pull_option_starts(connection), indent=2))
    pull_ss_flag_counts(connection).to_parquet(SS_FLAG_COUNTS_PATH, index=False)


def pull_all_cycle_quotes(connection: wrds.Connection, cycles: pd.DataFrame) -> None:
    """Pull every fund's cycle-expiry quotes, one year partition at a time."""
    for ticker in SECIDS:
        for year in OPTION_YEARS:
            rows = pull_cycle_quotes_year(connection, ticker, year, cycles)
            LOGGER.info("cycle quotes %s %d: %d rows", ticker, year, rows)


def load_prices() -> pd.DataFrame:
    """secprd prices for the four funds from disk."""
    return pd.read_parquet(PRICES_PATH)


def load_option_starts() -> dict[str, pd.Timestamp]:
    """Each fund's first opprcd date from disk."""
    return {
        ticker: pd.Timestamp(date)
        for ticker, date in json.loads(OPTION_STARTS_PATH.read_text()).items()
    }


def load_ss_flag_counts() -> pd.DataFrame:
    """Daily row counts by ss_flag and contract size from disk."""
    return pd.read_parquet(SS_FLAG_COUNTS_PATH)


def load_cycle_quotes(ticker: str | None = None) -> pd.DataFrame:
    """Cycle-expiry quotes from disk, for one fund or all four."""
    paths = sorted(CYCLE_QUOTES_DIR.glob(f"{ticker or '*'}_*.parquet"))
    quotes = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    ticker_of = {secid: name for name, secid in SECIDS.items()}
    quotes["ticker"] = quotes.secid.map(ticker_of)
    quotes["strike_price"] = quotes["strike_price"] / 1000.0
    return quotes


def load_zero_curve() -> pd.DataFrame:
    """Item 1's zero curve, rate in percent per annum by date and days."""
    return pd.read_parquet(ITEM1_ZERO_CURVE_PATH)


def load_atm_surface() -> pd.DataFrame:
    """Item 1's 30- and 91-day 50-delta call and put volatilities per fund and date."""
    surface = pd.read_parquet(ITEM1_ATM_SURFACE_PATH)
    surface["node"] = surface["node"].astype(int)
    return surface
