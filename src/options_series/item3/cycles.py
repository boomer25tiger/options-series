"""Cycle calendar of spec sections 3 and 10. Each cycle enters on the first trading day
after a standard monthly expiration, and its entry date places it in the estimation or
the holdout window.

Section 3 leaves the following choices open, and this module fixed them before it read
any quote.
- The trading calendar is the union of the four funds' secprd dates.
- A month's standard expiration is its third Friday, or the last trading day before it
  when the Friday is an exchange holiday. The legs settle against the fund's close on
  that trading day, and T runs in calendar days from the entry date to it.
- OptionMetrics dates a standard monthly contract on the Saturday after the third
  Friday before February 2015 and on the last trading day of that week from then on.
  Each cycle takes the candidate exdate whose rows carry no expiry_indicator.
- A fund enters its first cycle on the first trading day after the first standard
  expiration that follows its first opprcd date, and its last cycle is the last one
  expiring on or before the feed end.
"""

from __future__ import annotations

import pandas as pd

from options_series.item3.config import (
    CALENDAR_DAYS_PER_YEAR,
    ESTIMATION_END,
    ETFS,
    FEED_END,
)


def trading_calendar(prices: pd.DataFrame) -> pd.DatetimeIndex:
    """Every date on which any of the four funds has a secprd record."""
    return pd.DatetimeIndex(sorted(prices.date.unique()))


def third_friday(month: pd.Timestamp) -> pd.Timestamp:
    """Third Friday of the month containing the given date."""
    first = month.replace(day=1)
    return first + pd.Timedelta(days=(4 - first.weekday()) % 7 + 14)


def standard_expirations(calendar: pd.DatetimeIndex) -> pd.DataFrame:
    """Every month's standard expiration trading day inside the calendar, with the
    three candidate exdates OptionMetrics may carry for it."""
    rows = []
    for month in pd.date_range(calendar[0].replace(day=1), calendar[-1], freq="MS"):
        friday = third_friday(month)
        if friday < calendar[0] or friday > calendar[-1]:
            continue
        expiration = calendar[calendar <= friday][-1]
        rows.append(
            {
                "month": month,
                "third_friday": friday,
                "expiration": expiration,
                "exdate_candidates": tuple(
                    sorted({friday + pd.Timedelta(days=1), friday, expiration})
                ),
            }
        )
    return pd.DataFrame(rows)


def next_trading_day(calendar: pd.DatetimeIndex, date: pd.Timestamp) -> pd.Timestamp:
    """First trading day strictly after the given date."""
    return calendar[calendar.searchsorted(date, side="right")]


def cycle_calendar(
    calendar: pd.DatetimeIndex, option_starts: dict[str, pd.Timestamp]
) -> pd.DataFrame:
    """Every fund's cycles, each with its entry, its expiration and the expiration
    before entry, the calendar days and years to expiration at entry, its window and its
    candidate exdates."""
    expirations = standard_expirations(calendar)
    feed_end = pd.Timestamp(FEED_END)
    rows = []
    for ticker in ETFS:
        after_start = expirations[expirations.expiration > option_starts[ticker]]
        after_start = after_start[after_start.expiration <= feed_end].reset_index(
            drop=True
        )
        for index in range(len(after_start) - 1):
            previous, current = after_start.iloc[index], after_start.iloc[index + 1]
            entry = next_trading_day(calendar, previous.expiration)
            days = (current.expiration - entry).days
            rows.append(
                {
                    "ticker": ticker,
                    "cycle": index + 1,
                    "entry": entry,
                    "expiration": current.expiration,
                    "previous_expiration": previous.expiration,
                    "days_to_expiration": days,
                    "years_to_expiration": days / CALENDAR_DAYS_PER_YEAR,
                    "trading_days_held": int(
                        ((calendar >= entry) & (calendar <= current.expiration)).sum()
                    ),
                    "window": "estimation"
                    if entry <= pd.Timestamp(ESTIMATION_END)
                    else "holdout",
                    "exdate_candidates": current.exdate_candidates,
                }
            )
    cycles = pd.DataFrame(rows)
    cycles["entry_year"] = cycles.entry.dt.year
    return cycles
