"""Index membership and the CRSP to OptionMetrics link (spec section 4): the daily
constituent set, one secid per permno per date, the coverage report behind stop rule
9.1, and the previous-day market capitalisation behind the value weights.

Link resolution, fixed before any surface was pulled. Where a permno links to more than
one secid on a date, the link table's score decides, 1 being its best match; a tie on
score goes to the secid with more sample dates carrying a 30-day 50-delta call on the
surface, and a tie on that to the lower secid.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import wrds

from options_series.db import query, table_columns
from options_series.item2.config import (
    DATA_DIR,
    LINK_COVERAGE_FLOOR,
    LINK_TABLE,
    MEMBERSHIP_TABLE,
    RAW_DIR,
    SAMPLE_END,
    SAMPLE_START,
    SPX_SECID,
    STOCK_DAILY_TABLE,
)

LOGGER = logging.getLogger(__name__)

MEMBERSHIP_PATH = RAW_DIR / "membership.parquet"
LINK_PATH = RAW_DIR / "link.parquet"
TRADE_DATES_PATH = RAW_DIR / "trade_dates.parquet"
SURFACE_PRESENCE_PATH = RAW_DIR / "surface_presence.parquet"
STOCK_DAILY_DIR = RAW_DIR / "stock_daily"
CONSTITUENTS_PATH = DATA_DIR / "constituents.parquet"
MARKET_CAP_PATH = DATA_DIR / "market_cap.parquet"

# Stock prices start a month before the sample so the first sample date has a previous
# trading day.
STOCK_DAILY_START = "1995-12-01"


def sample_years(start: str = SAMPLE_START, end: str = SAMPLE_END) -> range:
    """Calendar years whose partitions the sample touches."""
    return range(int(start[:4]), int(end[:4]) + 1)


def year_bounds(year: int, start: str = SAMPLE_START, end: str = SAMPLE_END) -> tuple:
    """First and last date of one calendar year clipped to the sample."""
    return max(f"{year}-01-01", start), min(f"{year}-12-31", end)


def pull_membership(connection: wrds.Connection) -> pd.DataFrame:
    """Every S&P 500 membership interval in the CRSP index list."""
    membership = query(
        connection,
        f"select permno, indno, mbrstartdt, mbrenddt, mbrflg, indfam from {MEMBERSHIP_TABLE}",
    )
    membership["permno"] = membership["permno"].astype("int64")
    for column in ("mbrstartdt", "mbrenddt"):
        membership[column] = pd.to_datetime(membership[column])
    return membership


def link_table_columns(connection: wrds.Connection) -> pd.DataFrame:
    """Columns of the link table as the server catalog lists them."""
    schema, table = LINK_TABLE.split(".")
    return table_columns(connection, schema, table)


def pull_link(connection: wrds.Connection) -> pd.DataFrame:
    """The permno to secid link with its date range and match score."""
    link = query(
        connection, f"select secid, sdate, edate, permno, score from {LINK_TABLE}"
    )
    link["secid"] = link["secid"].astype("int64")
    link["permno"] = link["permno"].astype("Int64")
    link["score"] = pd.to_numeric(link["score"]).astype(float)
    for column in ("sdate", "edate"):
        link[column] = pd.to_datetime(link[column])
    return link


def pull_trade_dates(connection: wrds.Connection) -> pd.DataFrame:
    """SPX trade dates in the sample from the security price file; they define the daily
    calendar of the item."""
    frames = []
    for year in sample_years():
        start, end = year_bounds(year)
        frames.append(
            query(
                connection,
                f"select date from optionm.secprd{year} "
                "where secid = %(secid)s and date between %(start)s and %(end)s",
                {"secid": float(SPX_SECID), "start": start, "end": end},
            )
        )
    dates = pd.concat(frames, ignore_index=True)
    dates["date"] = pd.to_datetime(dates["date"])
    return dates.drop_duplicates().sort_values("date").reset_index(drop=True)


def membership_span(membership: pd.DataFrame) -> dict[str, object]:
    """First interval start, last interval end and distinct permnos in the list."""
    return {
        "first_start": membership.mbrstartdt.min(),
        "last_end": membership.mbrenddt.max(),
        "intervals": len(membership),
        "permnos": int(membership.permno.nunique()),
        "covers_sample_start": bool(
            membership.mbrstartdt.min() <= pd.Timestamp(SAMPLE_START)
        ),
    }


def member_days(
    membership: pd.DataFrame, trade_dates: pd.DatetimeIndex
) -> pd.DataFrame:
    """One row per trade date and permno whose membership interval contains the date."""
    dates = np.asarray(trade_dates, dtype="datetime64[ns]")
    starts = np.searchsorted(dates, membership.mbrstartdt.values, side="left")
    ends = np.searchsorted(dates, membership.mbrenddt.values, side="right")
    lengths = np.maximum(ends - starts, 0)
    positions = np.concatenate(
        [np.arange(start, end) for start, end in zip(starts, ends) if end > start]
    )
    days = pd.DataFrame(
        {
            "date": dates[positions],
            "permno": np.repeat(membership.permno.values, lengths),
        }
    )
    return (
        days.drop_duplicates(["date", "permno"])
        .sort_values(["date", "permno"])
        .reset_index(drop=True)
    )


def link_candidates(members: pd.DataFrame, link: pd.DataFrame) -> pd.DataFrame:
    """Every link row whose date range contains a member's date."""
    usable = link.dropna(subset=["permno", "sdate", "edate"])
    usable = usable[usable.permno.isin(members.permno.unique())].astype(
        {"permno": "int64"}
    )
    pairs = members.merge(usable, on="permno")
    pairs = pairs[(pairs.date >= pairs.sdate) & (pairs.date <= pairs.edate)]
    return pairs[["date", "permno", "secid", "score"]].reset_index(drop=True)


def pull_surface_presence(
    connection: wrds.Connection, candidates: pd.DataFrame
) -> pd.DataFrame:
    """Dates on which each candidate secid carries a non-null 30-day 50-delta call on the
    surface, one year partition at a time with that year's candidate secids."""
    frames = []
    for year in sample_years():
        secids = candidates.loc[candidates.date.dt.year == year, "secid"].unique()
        start, end = year_bounds(year)
        rows = query(
            connection,
            f"select secid, date from optionm.vsurfd{year} "
            "where secid in %(secids)s and date between %(start)s and %(end)s "
            "and days = 30 and delta = 50 and cp_flag = 'C' "
            "and impl_volatility is not null",
            {
                "secids": tuple(float(secid) for secid in sorted(secids)),
                "start": start,
                "end": end,
            },
        )
        LOGGER.info(
            "surface presence %d: %d secids, %d rows", year, len(secids), len(rows)
        )
        frames.append(rows)
    presence = pd.concat(frames, ignore_index=True)
    presence["secid"] = presence["secid"].astype("int64")
    presence["date"] = pd.to_datetime(presence["date"])
    return presence.drop_duplicates().reset_index(drop=True)


def resolve_links(
    candidates: pd.DataFrame, presence: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, int]]:
    """One secid per permno per date under the module's resolution rule, with counts of
    the permno-dates that linked to more than one secid and what decided them."""
    history = presence.groupby("secid").size()
    ranked = candidates.assign(
        surface_dates=candidates.secid.map(history).fillna(0).astype(int)
    )
    group = ["date", "permno"]
    ranked["links"] = ranked.groupby(group).secid.transform("size")
    best_score = ranked.groupby(group).score.transform("min")
    at_best_score = ranked.score == best_score
    ranked["tied_on_score"] = at_best_score.groupby(
        [ranked.date, ranked.permno]
    ).transform("sum")
    best_history = (
        ranked.surface_dates.where(at_best_score).groupby([ranked.date, ranked.permno])
    ).transform("max")
    ranked["tied_on_history"] = (
        (at_best_score & (ranked.surface_dates == best_history))
        .groupby([ranked.date, ranked.permno])
        .transform("sum")
    )
    chosen = ranked.sort_values(
        ["date", "permno", "score", "surface_dates", "secid"],
        ascending=[True, True, True, False, True],
    ).drop_duplicates(group)
    multiple = chosen[chosen.links > 1]
    summary = {
        "permno_dates_with_one_secid": int((chosen.links == 1).sum()),
        "permno_dates_with_several_secids": len(multiple),
        "permnos_with_several_secids": int(multiple.permno.nunique()),
        "decided_by_score": int((multiple.tied_on_score == 1).sum()),
        "decided_by_surface_history": int(
            ((multiple.tied_on_score > 1) & (multiple.tied_on_history == 1)).sum()
        ),
        "decided_by_lower_secid": int(
            ((multiple.tied_on_score > 1) & (multiple.tied_on_history > 1)).sum()
        ),
    }
    return chosen[["date", "permno", "secid", "score", "links"]], summary


def build_constituents(
    members: pd.DataFrame, resolved: pd.DataFrame, presence: pd.DataFrame
) -> pd.DataFrame:
    """Daily constituents with the resolved secid, its link score and whether the secid
    carries a 30-day 50-delta call on the surface that date."""
    panel = members.merge(resolved, on=["date", "permno"], how="left")
    panel["secid"] = panel["secid"].astype("Int64")
    present = presence.assign(surface_30=True)
    panel = panel.merge(present, on=["secid", "date"], how="left")
    panel["surface_30"] = panel["surface_30"].eq(True)
    panel["links"] = panel["links"].fillna(0).astype(int)
    return panel.sort_values(["date", "permno"]).reset_index(drop=True)


def shared_secids(panel: pd.DataFrame) -> pd.DataFrame:
    """Dates on which one secid is resolved for more than one member permno."""
    mapped = panel.dropna(subset=["secid"])
    counts = mapped.groupby(["date", "secid"]).permno.transform("size")
    return mapped[counts > 1]


def coverage(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily and yearly counts of members, members mapped to a secid and members whose
    secid carries the 30-day 50-delta call."""
    daily = (
        panel.groupby("date")
        .agg(
            members=("permno", "size"),
            mapped=("secid", "count"),
            with_surface=("surface_30", "sum"),
        )
        .reset_index()
    )
    daily["share_mapped"] = daily.mapped / daily.members
    daily["share_with_surface"] = daily.with_surface / daily.members
    by_year = (
        daily.groupby(daily.date.dt.year.rename("year"))
        .agg(
            dates=("date", "size"),
            mean_members=("members", "mean"),
            median_members=("members", "median"),
            mean_mapped=("mapped", "mean"),
            median_mapped=("mapped", "median"),
            mean_with_surface=("with_surface", "mean"),
            median_with_surface=("with_surface", "median"),
            median_share_with_surface=("share_with_surface", "median"),
        )
        .reset_index()
    )
    return daily, by_year


def link_coverage_check(daily: pd.DataFrame) -> dict[str, object]:
    """Stop rule 9.1: the median across sample dates of the share of members mapped to a
    secid with a 30-day surface, and the same share on the middle sample date."""
    middle = daily.sort_values("date").iloc[len(daily) // 2]
    median_share = float(daily.share_with_surface.median())
    return {
        "dates": len(daily),
        "median_share_with_surface": median_share,
        "middle_date": middle.date,
        "middle_date_share_with_surface": float(middle.share_with_surface),
        "floor": LINK_COVERAGE_FLOOR,
        "passed": median_share >= LINK_COVERAGE_FLOOR,
    }


def pull_stock_daily(connection: wrds.Connection, permnos: np.ndarray) -> None:
    """Daily CRSP price and shares outstanding for the given permnos, one calendar year
    per file."""
    STOCK_DAILY_DIR.mkdir(parents=True, exist_ok=True)
    permno_list = tuple(int(permno) for permno in sorted(permnos))
    for year in sample_years(STOCK_DAILY_START):
        start, end = year_bounds(year, STOCK_DAILY_START)
        rows = query(
            connection,
            f"select permno, dlycaldt, dlyprc, shrout from {STOCK_DAILY_TABLE} "
            "where permno in %(permnos)s and dlycaldt between %(start)s and %(end)s",
            {"permnos": permno_list, "start": start, "end": end},
        )
        rows = rows.rename(columns={"dlycaldt": "date"})
        rows["permno"] = rows["permno"].astype("int64")
        rows["date"] = pd.to_datetime(rows["date"])
        rows["dlyprc"] = pd.to_numeric(rows["dlyprc"]).astype(float)
        rows["shrout"] = pd.to_numeric(rows["shrout"]).astype(float)
        rows.to_parquet(STOCK_DAILY_DIR / f"stock_daily_{year}.parquet", index=False)
        LOGGER.info("stock daily %d: %d rows", year, len(rows))


def previous_day_market_cap() -> pd.DataFrame:
    """Market capitalisation on each permno's previous CRSP trading day: absolute price
    times shares outstanding, lagged one row within permno."""
    stock = pd.concat(
        [pd.read_parquet(path) for path in sorted(STOCK_DAILY_DIR.glob("*.parquet"))],
        ignore_index=True,
    )
    stock = stock.drop_duplicates(["permno", "date"]).sort_values(["permno", "date"])
    stock["market_cap"] = stock.dlyprc.abs() * stock.shrout
    stock["previous_market_cap"] = stock.groupby("permno").market_cap.shift(1)
    stock = stock[(stock.date >= SAMPLE_START) & (stock.date <= SAMPLE_END)]
    return stock[["permno", "date", "market_cap", "previous_market_cap"]].reset_index(
        drop=True
    )
