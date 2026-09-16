"""Futures curve state (spec sections 6.5 and 13): front and second settlements from
individual Datastream contracts, the gold and silver continuation splice, the sign of
the front spread and its winsorised percent slope."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import wrds

from options_series.db import query
from options_series.item1.config import (
    COMMODITY_LABELS,
    COMMON_END,
    COMMON_START,
    CONTINUATION_COMMODITIES,
    CONTINUATION_MATCH_FLOOR,
    CONTINUATION_SPLICE_DATE,
    CONTINUATION_TICKERS,
    CONTINUATION_TOLERANCE,
    CURVE_COVERAGE_FLOOR,
    FUTURES_CLASSES,
    NEGATIVE_FRONT_EXCLUSIONS,
    RAW_DIR,
    SLOPE_WINSOR_QUANTILES,
)

LOGGER = logging.getLogger(__name__)

FUTURES_DIR = RAW_DIR / "futures"
CANDIDATES_PATH = FUTURES_DIR / "continuation_candidates.parquet"
CURVE_COLUMNS = [
    "date",
    "front_settle",
    "second_settle",
    "front_contract",
    "second_contract",
]


def futures_paths(class_code: int) -> tuple[Path, Path]:
    """Parquet paths for one futures class's contracts and daily settlements."""
    return (
        FUTURES_DIR / f"contracts_{class_code}.parquet",
        FUTURES_DIR / f"settlements_{class_code}.parquet",
    )


def pull_futures_class(connection: wrds.Connection, class_code: int) -> None:
    """Write the contracts of one futures class, with last trading dates, and their
    daily settlements over the common window."""
    FUTURES_DIR.mkdir(parents=True, exist_ok=True)
    contracts = query(
        connection,
        "select futcode, lasttrddate from tr_ds_fut.dsfutcontrinfo "
        "where clscode = %(class_code)s",
        {"class_code": float(class_code)},
    )
    contracts["lasttrddate"] = pd.to_datetime(contracts["lasttrddate"])
    settlements = query(
        connection,
        "select futcode, date_ as date, settlement from tr_ds_fut.dsfutcontrval "
        "where futcode = any(%(futcodes)s) and date_ between %(start)s and %(end)s",
        {
            "futcodes": [float(code) for code in contracts.futcode],
            "start": COMMON_START,
            "end": COMMON_END,
        },
    )
    settlements["date"] = pd.to_datetime(settlements["date"])
    contracts_path, settlements_path = futures_paths(class_code)
    contracts.to_parquet(contracts_path, index=False)
    settlements.to_parquet(settlements_path, index=False)
    LOGGER.info("futures class %d: %d contracts", class_code, len(contracts))


def pull_continuation_candidates(connection: wrds.Connection) -> pd.DataFrame:
    """Write and return gold and silver classes on COMEX or NYMEX, by exchange ticker or
    contract name, with a contract trading after the splice date."""
    FUTURES_DIR.mkdir(parents=True, exist_ok=True)
    candidates = query(
        connection,
        "select distinct f.clscode, f.dsclsid, d.contrname, d.exchtickersymb "
        "from tr_ds_fut.dsfutclass f "
        "join tr_ds_fut.dsfutcontr d on d.contrcode = f.contrcode "
        "join tr_ds_fut.dsfutcontrinfo i on i.clscode = f.clscode "
        "where (d.contrname ilike '%%GOLD%%' or d.contrname ilike '%%SILVER%%') "
        "and (d.exchtickersymb = any(%(tickers)s) "
        "or d.contrname ilike '%%COMEX%%' or d.contrname ilike '%%NYMEX%%') "
        "and i.lasttrddate > %(splice)s order by f.clscode",
        {"tickers": list(CONTINUATION_TICKERS), "splice": CONTINUATION_SPLICE_DATE},
    )
    incumbents = [FUTURES_CLASSES[commodity] for commodity in CONTINUATION_COMMODITIES]
    candidates = candidates[~candidates.clscode.isin(incumbents)]
    candidates.to_parquet(CANDIDATES_PATH, index=False)
    return candidates


def pull_all_futures(connection: wrds.Connection) -> None:
    """Pull the curve-state classes, the continuation candidates and their contracts."""
    for class_code in FUTURES_CLASSES.values():
        pull_futures_class(connection, class_code)
    for class_code in pull_continuation_candidates(connection).clscode:
        pull_futures_class(connection, int(class_code))


def load_futures_class(class_code: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Contracts and daily settlements of one futures class from disk."""
    contracts_path, settlements_path = futures_paths(class_code)
    contracts = pd.read_parquet(contracts_path)
    settlements = pd.read_parquet(settlements_path)
    contracts["lasttrddate"] = pd.to_datetime(contracts["lasttrddate"])
    settlements["date"] = pd.to_datetime(settlements["date"])
    return contracts, settlements


def load_continuation_candidates() -> pd.DataFrame:
    """Continuation candidate classes from disk."""
    return pd.read_parquet(CANDIDATES_PATH)


def nearest_two_settlements(
    contracts: pd.DataFrame,
    settlements: pd.DataFrame,
    trade_dates: pd.DatetimeIndex,
    quoted_only: bool,
) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """Front and second settlement on each trade date, ranking contracts by last trading
    date on or after the date, and the dates dropped for a missing settlement.

    With quoted_only, contracts without a settlement that day are skipped before ranking,
    which compares quoted prices across classes. Without it, a missing settlement on
    either rank drops the date, as the curve state requires.
    """
    last_trading_date = contracts.dropna(subset=["lasttrddate"]).set_index("futcode")[
        "lasttrddate"
    ]
    rows = settlements.dropna(subset=["settlement"]) if quoted_only else settlements
    rows = rows.copy()
    rows["expiry"] = rows.futcode.map(last_trading_date)
    rows = rows.dropna(subset=["expiry"])
    trade_date_set = set(trade_dates)
    built, missing = [], []
    for date, day in rows.groupby("date"):
        if date not in trade_date_set:
            continue
        listed = day[day.expiry >= date].sort_values(["expiry", "futcode"])
        if len(listed) < 2:
            continue
        front_settle, second_settle = (
            listed.settlement.iloc[0],
            listed.settlement.iloc[1],
        )
        if pd.isna(front_settle) or pd.isna(second_settle):
            missing.append(date)
            continue
        built.append(
            {
                "date": date,
                "front_settle": float(front_settle),
                "second_settle": float(second_settle),
                "front_contract": listed.futcode.iloc[0],
                "second_contract": listed.futcode.iloc[1],
            }
        )
    return pd.DataFrame(built, columns=CURVE_COLUMNS), missing


def test_continuation_candidates(
    candidates: pd.DataFrame, trade_dates: pd.DatetimeIndex
) -> pd.DataFrame:
    """Share of overlap dates on which each candidate's front and second settlements
    match the incumbent gold or silver class within tolerance, and whether it passes."""
    splice = pd.Timestamp(CONTINUATION_SPLICE_DATE)
    incumbents = {
        commodity: nearest_two_settlements(
            *load_futures_class(FUTURES_CLASSES[commodity]),
            trade_dates,
            quoted_only=True,
        )[0]
        for commodity in CONTINUATION_COMMODITIES
    }
    rows = []
    for candidate in candidates.sort_values("clscode").itertuples():
        metal = "GC" if "GOLD" in str(candidate.contrname).upper() else "SI"
        candidate_curve = nearest_two_settlements(
            *load_futures_class(int(candidate.clscode)), trade_dates, quoted_only=True
        )[0]
        merged = incumbents[metal].merge(
            candidate_curve, on="date", suffixes=("_incumbent", "_candidate")
        )
        overlap = merged[(merged.date >= COMMON_START) & (merged.date <= splice)]
        front_match = float(
            (
                (overlap.front_settle_candidate - overlap.front_settle_incumbent).abs()
                / overlap.front_settle_incumbent.abs()
                <= CONTINUATION_TOLERANCE
            ).mean()
        )
        second_match = float(
            (
                (
                    overlap.second_settle_candidate - overlap.second_settle_incumbent
                ).abs()
                / overlap.second_settle_incumbent.abs()
                <= CONTINUATION_TOLERANCE
            ).mean()
        )
        rows.append(
            {
                "class_code": int(candidate.clscode),
                "class_id": candidate.dsclsid,
                "contract": candidate.contrname,
                "metal": metal,
                "overlap_dates": len(overlap),
                "front_match": front_match,
                "second_match": second_match,
                "dates_after_splice": int((candidate_curve.date > splice).sum()),
                "accepted": len(overlap) > 0
                and front_match >= CONTINUATION_MATCH_FLOOR
                and second_match >= CONTINUATION_MATCH_FLOOR,
            }
        )
    return pd.DataFrame(rows)


def choose_continuation(tests: pd.DataFrame) -> dict[str, int]:
    """Continuation class per metal among accepted classes that extend past the splice:
    highest second-rank match, then highest front match, then lowest class code."""
    extending = tests[tests.accepted & (tests.dates_after_splice > 0)]
    chosen = {}
    for metal in CONTINUATION_COMMODITIES:
        ranked = extending[extending.metal == metal].sort_values(
            ["second_match", "front_match", "class_code"],
            ascending=[False, False, True],
        )
        if len(ranked):
            chosen[metal] = int(ranked.class_code.iloc[0])
    return chosen


def build_curve(
    trade_dates: pd.DatetimeIndex, continuation: dict[str, int]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Front and second settlements per commodity on each trade date, spliced where a
    continuation class exists, with the coverage table the section 9 check reads."""
    splice = pd.Timestamp(CONTINUATION_SPLICE_DATE)
    curves, coverage = [], []
    for commodity, class_code in FUTURES_CLASSES.items():
        curve, missing = nearest_two_settlements(
            *load_futures_class(class_code), trade_dates, quoted_only=False
        )
        continuation_code = continuation.get(commodity)
        if continuation_code is not None:
            extension, extension_missing = nearest_two_settlements(
                *load_futures_class(continuation_code), trade_dates, quoted_only=False
            )
            curve = pd.concat(
                [curve[curve.date <= splice], extension[extension.date > splice]],
                ignore_index=True,
            )
            missing = [date for date in missing if date <= splice] + [
                date for date in extension_missing if date > splice
            ]
        curve = curve.sort_values("date").reset_index(drop=True)
        curve["front_switch"] = curve.front_contract != curve.front_contract.shift(1)
        curve.loc[0, "front_switch"] = False
        curve["commodity"] = commodity
        curves.append(curve)
        coverage_share = round(len(curve) / len(trade_dates), 4)
        coverage.append(
            {
                "commodity": commodity,
                "underlying_for": COMMODITY_LABELS[commodity],
                "incumbent_class": class_code,
                "continuation_class": continuation_code,
                "spliced_at": CONTINUATION_SPLICE_DATE
                if continuation_code is not None
                else None,
                "dates_built": len(curve),
                "dropped_null_settlement": len(missing),
                "first_date": curve.date.min(),
                "last_date": curve.date.max(),
                "coverage_share": coverage_share,
                "front_switches": int(curve.front_switch.sum()),
                "clears_floor": coverage_share >= CURVE_COVERAGE_FLOOR,
            }
        )
    return pd.concat(curves, ignore_index=True), pd.DataFrame(coverage)


def curve_slope_and_sign(curve: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sign of F2 − F1 and the winsorised percent slope (F2 − F1)/F1 per commodity, with
    the share of each state and the winsorisation bounds."""
    frames, summary = [], []
    lower_quantile, upper_quantile = SLOPE_WINSOR_QUANTILES
    for commodity in FUTURES_CLASSES:
        state = curve[curve.commodity == commodity].copy()
        state["spread"] = state.second_settle - state.front_settle
        state["curve_state"] = np.where(
            state.spread > 0,
            "contango",
            np.where(state.spread < 0, "backwardation", "equal"),
        )
        state["slope_raw"] = state.spread / state.front_settle
        excluded = pd.to_datetime(list(NEGATIVE_FRONT_EXCLUSIONS.get(commodity, ())))
        state.loc[state.date.isin(excluded), "slope_raw"] = np.nan
        lower, upper = state.slope_raw.quantile([lower_quantile, upper_quantile])
        state["slope"] = state.slope_raw.clip(lower, upper)
        total = len(state)
        summary.append(
            {
                "commodity": commodity,
                "share_contango": round(
                    int((state.curve_state == "contango").sum()) / total, 4
                ),
                "share_backwardation": round(
                    int((state.curve_state == "backwardation").sum()) / total, 4
                ),
                "dropped_equal": int((state.curve_state == "equal").sum()),
                "winsor_lower": float(lower),
                "winsor_upper": float(upper),
                "slope_nonnull": int(state.slope.notna().sum()),
                "excluded_dates_present": [
                    str(date.date()) for date in excluded if date in set(state.date)
                ],
            }
        )
        state.loc[state.curve_state == "equal", "curve_state"] = np.nan
        frames.append(state)
    return pd.concat(frames, ignore_index=True), pd.DataFrame(summary)
