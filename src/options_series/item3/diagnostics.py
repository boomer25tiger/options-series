"""Session 1 diagnostics of spec section 14, D1 to D11. Nothing here computes an option
gain, a hedge gain, a cycle return or realized variance over a cycle.

Section 14 leaves the following choices open, and this module fixed them before any
diagnostic ran.
- Hedge and mark diagnostics run from the entry close through the close before
  expiration. The expiration close settles every leg at intrinsic and closes the hedge,
  so neither diagnostic reads a delta or a mark there.
- A leg with no row on a date counts as a null delta with a null implied volatility,
  and as a carried mark.
- The prior day's implied volatility of the second fallback path is the leg's own
  opprcd value on the previous trading day, which the pull holds from the day before
  entry onward. A position day sits on a carried hedge when any leg falls through both
  paths.
- Any mark with a positive bid and an offer at or below it, or with one quote null and
  the other positive, fits none of the three section 3 cases, and the diagnostics count
  it as unclassified.
- Entry moneyness is ln(K / F) in units of σ_ATM √T.
"""

from __future__ import annotations

import tempfile
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import ndtr

from options_series.item1.config import STRIKE_FLOOR as ITEM1_STRIKE_FLOOR
from options_series.item1.model_free_variance import atm_implied_variance
from options_series.item3.config import (
    CALENDAR_DAYS_PER_YEAR,
    CONTINUITY_END,
    CONTINUITY_ETFS,
    CONTINUITY_START,
    CYCLE_QUOTES_DIR,
    EXECUTION_FRACTIONS,
    EXPECTED_ESTIMATION_CYCLES,
    EXPECTED_FIRST_ENTRY,
    EXPECTED_FIRST_HOLDOUT_ENTRY,
    EXPECTED_HOLDOUT_CYCLES,
    EXPECTED_LAST_ESTIMATION_ENTRY,
    EXPECTED_LAST_HOLDOUT_ENTRY,
    EXPECTED_LAST_HOLDOUT_EXPIRATION,
    EXPECTED_POOLED_ESTIMATION_CYCLES,
    FILTER_SHARE_FLOOR,
    ITEM1_OPTION_QUOTES_DIR,
    MONEYNESS_EDGES,
    PERCENTILES,
    STANDARD_CONTRACT_SIZE,
    STANDARD_SETTLEMENT_FLAG,
    STRIP_MIN_SPAN,
    STRIP_MIN_STRIKES,
)
from options_series.item3.construction import OK, ZeroCurve, passes_filters

ALL = "ALL"
HEDGE_PATHS = (
    "opprcd delta",
    "black-scholes own iv",
    "black-scholes prior iv",
    "carried",
)
QUOTE_FIELDS = [
    "optionid",
    "date",
    "best_bid",
    "best_offer",
    "delta",
    "impl_volatility",
    "ss_flag",
    "contract_size",
    "strike_price",
]


def _percentile_row(values: pd.Series, prefix: str = "") -> dict[str, float]:
    """Count and mean of a series alongside its reporting percentiles, ignoring NaN."""
    values = values.dropna()
    row = {f"{prefix}n": len(values), f"{prefix}mean": values.mean()}
    for level in PERCENTILES:
        row[f"{prefix}p{round(level * 100):02d}"] = values.quantile(level)
    return row


def _with_pooled(frame: pd.DataFrame, column: str = "ticker") -> pd.DataFrame:
    """The frame with its rows repeated under an ALL label in the given column."""
    return pd.concat([frame, frame.assign(**{column: ALL})], ignore_index=True)


# D1 --------------------------------------------------------------------------------


def adjustment_changes(prices: pd.DataFrame) -> pd.DataFrame:
    """Every date on which a fund's secprd cumulative adjustment factor changes, with
    the closes around it and the split ratio it implies."""
    prices = prices.sort_values(["ticker", "date"]).copy()
    grouped = prices.groupby("ticker")
    prices["cfadj_before"] = grouped.cfadj.shift()
    prices["close_before"] = grouped.close.shift()
    prices["date_before"] = grouped.date.shift()
    changes = prices[
        prices.cfadj_before.notna() & (prices.cfadj != prices.cfadj_before)
    ].copy()
    changes["factor"] = changes.cfadj / changes.cfadj_before
    changes["action"] = [
        f"split {factor:g}-for-1"
        if factor > 1
        else f"reverse split 1-for-{1 / factor:g}"
        for factor in changes.factor
    ]
    return changes[
        [
            "ticker",
            "date",
            "date_before",
            "close_before",
            "close",
            "cfadj_before",
            "cfadj",
            "factor",
            "action",
        ]
    ].rename(columns={"close": "close_after", "cfadj": "cfadj_after"})


def ss_flag_runs(counts: pd.DataFrame, changes: pd.DataFrame) -> pd.DataFrame:
    """Contiguous runs of option dates on which a fund carries rows off standard
    settlement or off 100 shares, per ss_flag and contract size, each with the latest
    adjustment-factor change on or before the run's first date."""
    rows = []
    for ticker, history in counts.groupby("ticker"):
        dates = np.sort(history.date.unique())
        position = {date: index for index, date in enumerate(dates)}
        off_standard = history[
            (history.ss_flag != STANDARD_SETTLEMENT_FLAG)
            | (history.contract_size != STANDARD_CONTRACT_SIZE)
        ]
        for (flag, size), group in off_standard.groupby(["ss_flag", "contract_size"]):
            group = group.sort_values("date")
            index = group.date.map(position).values
            breaks = np.flatnonzero(np.diff(index) != 1) + 1
            for run in np.split(np.arange(len(group)), breaks):
                run_rows = group.iloc[run]
                first = run_rows.date.iloc[0]
                prior = changes[(changes.ticker == ticker) & (changes.date <= first)]
                rows.append(
                    {
                        "ticker": ticker,
                        "ss_flag": flag,
                        "contract_size": size,
                        "first_date": first,
                        "last_date": run_rows.date.iloc[-1],
                        "dates": len(run_rows),
                        "max_rows_per_date": int(run_rows.rows.max()),
                        "latest_action_on_or_before": prior.action.iloc[-1]
                        if len(prior)
                        else "",
                        "latest_action_date": prior.date.iloc[-1]
                        if len(prior)
                        else pd.NaT,
                    }
                )
    return pd.DataFrame(rows).sort_values(["ticker", "first_date"])


# D2 --------------------------------------------------------------------------------


def missing_returns(
    cycles: pd.DataFrame, prices: pd.DataFrame, calendar: pd.DatetimeIndex
) -> pd.Series:
    """Per cycle, the trading days from the day after entry through expiration that lack
    a section 4 return, because a close is absent on the day or the day before or because
    the simple return sits at or below -100 percent. The count squares and sums no
    return."""
    adjusted = prices.assign(adjusted_close=prices.close * prices.cfadj)
    counts = []
    for cycle in cycles.itertuples():
        days = calendar[(calendar >= cycle.entry) & (calendar <= cycle.expiration)]
        closes = (
            adjusted[adjusted.ticker == cycle.ticker]
            .set_index("date")
            .adjusted_close.reindex(days)
        )
        simple = closes.values[1:] / closes.values[:-1] - 1.0
        counts.append(int((~np.isfinite(simple) | (simple <= -1.0)).sum()))
    return pd.Series(counts, index=cycles.index)


def cycle_inventory(entries: pd.DataFrame) -> pd.DataFrame:
    """Per fund and entry year, the cycle count and calendar days to expiration at entry,
    with the cycles that meet the section 3 filters for each arm and the strip floor."""
    frame = _with_pooled(entries)
    frame["strip_ok"] = frame.strip_status == OK
    frame["straddle_ok"] = frame.straddle_status == OK
    frame["strip_floor"] = frame.strip_ok & frame.floor_pass.eq(True)
    frame["complete_returns"] = frame.missing_returns == 0
    rows = []
    for (ticker, year), group in frame.groupby(["ticker", "entry_year"]):
        rows.append(
            {
                "ticker": ticker,
                "entry_year": year,
                "cycles": len(group),
                "estimation_cycles": int((group.window == "estimation").sum()),
                "holdout_cycles": int((group.window == "holdout").sum()),
                "days_to_expiration_min": group.days_to_expiration.min(),
                "days_to_expiration_median": group.days_to_expiration.median(),
                "days_to_expiration_max": group.days_to_expiration.max(),
                "strip_meets_section3": int(group.strip_ok.sum()),
                "strip_meets_section3_and_floor": int(group.strip_floor.sum()),
                "straddle_meets_section3": int(group.straddle_ok.sum()),
                "cycles_with_missing_return": int((~group.complete_returns).sum()),
            }
        )
    return pd.DataFrame(rows)


def stop_rule_one(entries: pd.DataFrame) -> pd.DataFrame:
    """Section 16 rule 1 on the estimation window, as the share of each fund's cycles
    that pass the section 3 filters per arm, with the strip also under the rule 2
    floor."""
    estimation = entries[entries.window == "estimation"]
    rows = []
    for ticker, group in estimation.groupby("ticker"):
        strip_ok = group.strip_status == OK
        passing = {
            ("strip", "section 3"): strip_ok,
            ("strip", "section 3 and rule 2 floor"): strip_ok
            & group.floor_pass.eq(True),
            ("straddle", "section 3"): group.straddle_status == OK,
        }
        for (arm, rule), mask in passing.items():
            share = mask.mean()
            rows.append(
                {
                    "ticker": ticker,
                    "arm": arm,
                    "rule": rule,
                    "estimation_cycles": len(group),
                    "passing": int(mask.sum()),
                    "share": share,
                    "floor": FILTER_SHARE_FLOOR,
                    "drops_from_family": bool(share < FILTER_SHARE_FLOOR),
                }
            )
    return pd.DataFrame(rows)


# D3 --------------------------------------------------------------------------------


def entry_spread_share(entries: pd.DataFrame) -> pd.DataFrame:
    """Entry quoted half-spread as a share of entry mid premium, per sample, arm, fund
    and year, with percentiles and the cost at each execution fraction k, which is k
    times the share."""
    strip = entries[entries.strip_status == OK].assign(
        arm="strip",
        share=lambda frame: (
            frame.strip_half_spread_per_weight / frame.strip_premium_per_weight
        ),
        rule="section 3",
    )
    strip_floor = strip[strip.floor_pass.eq(True)].assign(
        rule="section 3 and rule 2 floor"
    )
    straddle = entries[entries.straddle_status == OK].assign(
        arm="straddle",
        share=lambda frame: frame.straddle_half_spread / frame.straddle_premium,
        rule="section 3",
    )
    frame = _with_pooled(pd.concat([strip, strip_floor, straddle], ignore_index=True))
    frame = pd.concat(
        [frame.assign(year=frame.entry_year.astype(str)), frame.assign(year=ALL)],
        ignore_index=True,
    )
    rows = []
    for sample, subset in (
        ("full", frame),
        ("estimation", frame[frame.window == "estimation"]),
    ):
        for (arm, rule, ticker, year), group in subset.groupby(
            ["arm", "rule", "ticker", "year"]
        ):
            row = {
                "sample": sample,
                "arm": arm,
                "rule": rule,
                "ticker": ticker,
                "year": year,
                **_percentile_row(group.share),
            }
            for k in EXECUTION_FRACTIONS:
                row[f"mean_cost_k{k:g}"] = k * group.share.mean()
                row[f"median_cost_k{k:g}"] = k * group.share.median()
            rows.append(row)
    return pd.DataFrame(rows)


# D4 and D6 panel -------------------------------------------------------------------


def leg_day_panel(
    legs: pd.DataFrame,
    cycles: pd.DataFrame,
    quotes: pd.DataFrame,
    calendar: pd.DatetimeIndex,
) -> pd.DataFrame:
    """One row per leg and trading day from the day before entry through expiration,
    cycle day zero at entry, with the leg's opprcd row on that date where one exists."""
    frames = []
    for cycle in cycles.itertuples():
        days = calendar[
            (calendar >= cycle.previous_expiration) & (calendar <= cycle.expiration)
        ]
        frames.append(
            pd.DataFrame(
                {
                    "ticker": cycle.ticker,
                    "cycle": cycle.cycle,
                    "date": days,
                    "cycle_day": np.arange(len(days)) - 1,
                    "days_to_expiration": (cycle.expiration - days).days,
                }
            )
        )
    days = pd.concat(frames, ignore_index=True)
    panel = legs[
        ["ticker", "cycle", "arm", "optionid", "cp_flag", "strike_price", "moneyness"]
    ].merge(days, on=["ticker", "cycle"])
    rows = quotes[QUOTE_FIELDS].rename(columns={"strike_price": "row_strike"})
    panel = panel.merge(rows, on=["optionid", "date"], how="left", indicator=True)
    panel["present"] = panel.pop("_merge") == "both"
    return panel.sort_values(["ticker", "cycle", "arm", "optionid", "date"])


def black_scholes_delta(
    spot: np.ndarray,
    strike: np.ndarray,
    years: np.ndarray,
    rate: np.ndarray,
    vol: np.ndarray,
    is_call: np.ndarray,
) -> np.ndarray:
    """Black-Scholes delta on a non-dividend underlying, NaN where an input is missing."""
    with np.errstate(divide="ignore", invalid="ignore"):
        d1 = (np.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (
            vol * np.sqrt(years)
        )
    call_delta = ndtr(d1)
    return np.where(is_call, call_delta, call_delta - 1.0)


def hedge_paths(
    panel: pd.DataFrame, prices: pd.DataFrame, curve: ZeroCurve
) -> pd.DataFrame:
    """The section 3 hedge path of every leg-day from entry to the close before
    expiration, which takes the opprcd delta when present, then Black-Scholes on the
    leg's own implied volatility, then Black-Scholes on the prior day's, and carries the
    hedge when all three fail."""
    panel = panel.copy()
    panel["prior_iv"] = panel.groupby(["ticker", "cycle", "arm", "optionid"])[
        "impl_volatility"
    ].shift()
    panel = panel[(panel.cycle_day >= 0) & (panel.days_to_expiration > 0)].copy()
    panel = panel.merge(
        prices[["ticker", "date", "close"]], on=["ticker", "date"], how="left"
    )
    years = panel.days_to_expiration.values / CALENDAR_DAYS_PER_YEAR
    tenors = panel[["date", "days_to_expiration"]].drop_duplicates()
    tenors["rate"] = [
        curve.rate(date, days)
        for date, days in zip(tenors.date, tenors.days_to_expiration)
    ]
    rates = (
        panel[["date", "days_to_expiration"]]
        .merge(tenors, on=["date", "days_to_expiration"], how="left")
        .rate.values
    )
    is_call = (panel.cp_flag == "C").values
    spot, strike = panel.close.values, panel.strike_price.values.astype(float)

    def usable(vol: pd.Series) -> np.ndarray:
        return (vol > 0).fillna(False).values

    own = black_scholes_delta(
        spot, strike, years, rates, panel.impl_volatility.values, is_call
    )
    prior = black_scholes_delta(
        spot, strike, years, rates, panel.prior_iv.values, is_call
    )
    has_delta = panel.delta.notna().values
    own_ok = ~has_delta & usable(panel.impl_volatility) & np.isfinite(own)
    prior_ok = ~has_delta & ~own_ok & usable(panel.prior_iv) & np.isfinite(prior)
    panel["path"] = np.select(
        [has_delta, own_ok, prior_ok], HEDGE_PATHS[:3], HEDGE_PATHS[3]
    )
    return panel


def _null_runs(null: pd.Series) -> list[int]:
    """Lengths of consecutive True runs."""
    values = null.values.astype(int)
    edges = np.diff(np.concatenate([[0], values, [0]]))
    return list(np.flatnonzero(edges == -1) - np.flatnonzero(edges == 1))


def delta_diagnostics(
    paths: pd.DataFrame, entries: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """D4 delta null rates and null run lengths. The other two tables give the success
    of each fallback path and, per cycle, the fallback count with the share of days on a
    carried hedge."""
    paths = paths.merge(
        entries[["ticker", "cycle", "entry_year", "window"]], on=["ticker", "cycle"]
    )
    paths["delta_null"] = paths.delta.isna()
    pooled = _with_pooled(paths)
    rates = []
    for (ticker, arm, year), group in pd.concat(
        [pooled.assign(year=pooled.entry_year.astype(str)), pooled.assign(year=ALL)]
    ).groupby(["ticker", "arm", "year"]):
        row = {
            "ticker": ticker,
            "arm": arm,
            "entry_year": year,
            "leg_days": len(group),
            "absent_share": 1.0 - group.present.mean(),
            "delta_null_share": group.delta_null.mean(),
        }
        shares = group.path.value_counts(normalize=True)
        for path in HEDGE_PATHS:
            row[f"share_{path.replace(' ', '_').replace('-', '_')}"] = shares.get(
                path, 0.0
            )
        rates.append(row)

    runs = []
    for (ticker, arm), group in paths.groupby(["ticker", "arm"]):
        lengths = [
            length
            for _, leg in group.groupby(["cycle", "optionid"])
            for length in _null_runs(leg.delta_null)
        ]
        for length, count in pd.Series(lengths).value_counts().sort_index().items():
            runs.append(
                {"ticker": ticker, "arm": arm, "run_length": length, "runs": count}
            )

    fallback = []
    for (ticker, arm), group in _with_pooled(paths).groupby(["ticker", "arm"]):
        null = group[group.delta_null]
        own = (null.path == "black-scholes own iv").sum()
        after_own = null[null.path != "black-scholes own iv"]
        prior = (after_own.path == "black-scholes prior iv").sum()
        fallback.append(
            {
                "ticker": ticker,
                "arm": arm,
                "null_delta_leg_days": len(null),
                "own_iv_attempts": len(null),
                "own_iv_successes": int(own),
                "own_iv_success_rate": own / len(null) if len(null) else np.nan,
                "prior_iv_attempts": len(after_own),
                "prior_iv_successes": int(prior),
                "prior_iv_success_rate": prior / len(after_own)
                if len(after_own)
                else np.nan,
                "carried_leg_days": int((null.path == "carried").sum()),
            }
        )

    per_day = (
        paths.assign(
            fallback_legs=paths.path != "opprcd delta",
            carried=paths.path == "carried",
        )
        .groupby(["ticker", "cycle", "arm", "date"])
        .agg(fallback_legs=("fallback_legs", "sum"), carried=("carried", "max"))
        .reset_index()
    )
    per_cycle = (
        per_day.groupby(["ticker", "cycle", "arm"])
        .agg(
            hedge_days=("date", "size"),
            fallback_leg_days=("fallback_legs", "sum"),
            carried_hedge_days=("carried", "sum"),
        )
        .reset_index()
    )
    per_cycle["carried_hedge_share"] = (
        per_cycle.carried_hedge_days / per_cycle.hedge_days
    )
    return (
        pd.DataFrame(rates),
        pd.DataFrame(runs),
        pd.DataFrame(fallback),
        per_cycle,
    )


# D5 --------------------------------------------------------------------------------


def strip_coverage(entries: pd.DataFrame) -> pd.DataFrame:
    """Per fund and entry year, the strip's strike counts and traded span each side,
    with the cycles that pass the section 16 rule 2 floor and the reason others fail."""
    strip = _with_pooled(entries[entries.strip_status == OK])
    strip = pd.concat(
        [strip.assign(year=strip.entry_year.astype(str)), strip.assign(year=ALL)],
        ignore_index=True,
    )
    rows = []
    for (ticker, year), group in strip.groupby(["ticker", "year"]):
        few = (group.strip_puts < STRIP_MIN_STRIKES) | (
            group.strip_calls < STRIP_MIN_STRIKES
        )
        no_sigma = group.sigma_atm.isna()
        short = ~no_sigma & (
            (group.span_put < STRIP_MIN_SPAN) | (group.span_call < STRIP_MIN_SPAN)
        )
        short_price = ~no_sigma & (
            (group.span_put_price < STRIP_MIN_SPAN)
            | (group.span_call_price < STRIP_MIN_SPAN)
        )
        rows.append(
            {
                "ticker": ticker,
                "entry_year": year,
                "strip_cycles": len(group),
                "median_puts": group.strip_puts.median(),
                "median_calls": group.strip_calls.median(),
                "min_puts": group.strip_puts.min(),
                "min_calls": group.strip_calls.min(),
                "median_span_put": group.span_put.median(),
                "median_span_call": group.span_call.median(),
                "min_span_put": group.span_put.min(),
                "min_span_call": group.span_call.min(),
                "fail_strike_count": int(few.sum()),
                "fail_span": int(short.sum()),
                "fail_no_sigma_atm": int(no_sigma.sum()),
                "pass_floor": int(group.floor_pass.eq(True).sum()),
                "pass_floor_span_in_price": int(
                    (~few & ~no_sigma & ~short_price).sum()
                ),
            }
        )
    return pd.DataFrame(rows)


# D6 --------------------------------------------------------------------------------


def mark_type(panel: pd.DataFrame) -> np.ndarray:
    """Section 3 mark case of each leg-day, one of mid, zero bid at half the offer,
    carried or unclassified."""
    bid, offer = panel.best_bid, panel.best_offer
    empty_bid = bid.isna() | (bid == 0)
    empty_offer = offer.isna() | (offer == 0)
    return np.select(
        [
            ~panel.present.values,
            ((bid > 0) & (offer > bid)).fillna(False).values,
            ((bid == 0) & (offer > 0)).fillna(False).values,
            (empty_bid & empty_offer).values,
        ],
        ["carried", "mid", "zero bid", "carried"],
        "unclassified",
    )


def moneyness_bucket(moneyness: pd.Series) -> pd.Series:
    """Entry moneyness bucket label from the configured edges."""
    edges = [-np.inf, *MONEYNESS_EDGES, np.inf]
    labels = [
        f"{low:g} to {high:g}".replace("-inf to ", "below ").replace(" to inf", " up")
        for low, high in pairwise(edges)
    ]
    return pd.cut(moneyness, edges, labels=labels, right=False)


def zero_bid_marks(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """D6 mark cases of strip legs by fund and entry moneyness bucket on each cycle day,
    and per cycle the count of zero-bid marks."""
    strip = panel[
        (panel.arm == "strip") & (panel.cycle_day >= 0) & (panel.days_to_expiration > 0)
    ].copy()
    strip["mark"] = mark_type(strip)
    strip["bucket"] = moneyness_bucket(strip.moneyness)
    table = (
        _with_pooled(strip)
        .groupby(["ticker", "bucket", "cycle_day"], observed=True)
        .mark.value_counts()
        .unstack(fill_value=0)
        .reset_index()
    )
    marks = ["mid", "zero bid", "carried", "unclassified"]
    for mark in marks:
        if mark not in table:
            table[mark] = 0
    table["leg_days"] = table[marks].sum(axis=1)
    for mark in marks:
        table[f"share_{mark.replace(' ', '_')}"] = table[mark] / table.leg_days
    per_cycle = (
        strip.assign(zero_bid=strip.mark == "zero bid")
        .groupby(["ticker", "cycle"])
        .agg(strip_leg_days=("mark", "size"), zero_bid_marks=("zero_bid", "sum"))
        .reset_index()
    )
    return table, per_cycle


# D7 --------------------------------------------------------------------------------


def chain_continuity(
    quotes: pd.DataFrame,
    cycles: pd.DataFrame,
    panel: pd.DataFrame,
    changes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """D7 for USO and UNG from 2020-03-01 to 2020-06-30, giving the daily state of the
    cycle expiry's chain and a trace of every entry leg of a cycle in the window,
    including legs that a cycle holds across an adjustment-factor change."""
    start, end = pd.Timestamp(CONTINUITY_START), pd.Timestamp(CONTINUITY_END)
    in_window = cycles[
        cycles.ticker.isin(CONTINUITY_ETFS)
        & (cycles.expiration >= start)
        & (cycles.entry <= end)
    ]
    daily = []
    for cycle in in_window.itertuples():
        chain = quotes[
            (quotes.ticker == cycle.ticker)
            & (quotes.exdate == cycle.exdate)
            & (quotes.date >= max(cycle.entry, start))
            & (quotes.date <= min(cycle.expiration, end))
        ]
        for date, day in chain.groupby("date"):
            standard = (day.ss_flag == STANDARD_SETTLEMENT_FLAG) & (
                day.contract_size == STANDARD_CONTRACT_SIZE
            )
            passing = day[passes_filters(day)]
            paired = set(passing[passing.cp_flag == "C"].strike_price) & set(
                passing[passing.cp_flag == "P"].strike_price
            )
            daily.append(
                {
                    "ticker": cycle.ticker,
                    "date": date,
                    "cycle": cycle.cycle,
                    "exdate": cycle.exdate,
                    "rows": len(day),
                    "standard_rows": int(standard.sum()),
                    "non_standard_rows": int((~standard).sum()),
                    "contract_sizes": " ".join(
                        f"{size:g}" for size in sorted(day.contract_size.unique())
                    ),
                    "passing_rows": len(passing),
                    "paired_strikes": len(paired),
                    "delta_null_rows": int(day.delta.isna().sum()),
                }
            )

    legs = panel[
        panel.set_index(["ticker", "cycle"]).index.isin(
            in_window.set_index(["ticker", "cycle"]).index
        )
        & (panel.cycle_day >= 0)
    ]
    traced = []
    for (ticker, cycle, arm, optionid), leg in legs.groupby(
        ["ticker", "cycle", "arm", "optionid"]
    ):
        leg = leg.sort_values("date")
        held = in_window[
            (in_window.ticker == ticker) & (in_window.cycle == cycle)
        ].iloc[0]
        actions = changes[
            (changes.ticker == ticker)
            & (changes.date > held.entry)
            & (changes.date <= held.expiration)
        ]
        standard = (leg.ss_flag == STANDARD_SETTLEMENT_FLAG) & (
            leg.contract_size == STANDARD_CONTRACT_SIZE
        )
        after = leg[leg.date >= actions.date.iloc[0]] if len(actions) else leg.iloc[0:0]
        after_standard = standard[after.index]
        traced.append(
            {
                "ticker": ticker,
                "cycle": cycle,
                "entry": held.entry,
                "expiration": held.expiration,
                "arm": arm,
                "optionid": optionid,
                "cp_flag": leg.cp_flag.iloc[0],
                "strike_price": leg.strike_price.iloc[0],
                "cycle_days": len(leg),
                "days_present": int(leg.present.sum()),
                "days_standard": int(standard.sum()),
                "action_in_cycle": actions.action.iloc[0] if len(actions) else "",
                "action_date": actions.date.iloc[0] if len(actions) else pd.NaT,
                "days_after_action": len(after),
                "days_after_action_present": int(after.present.sum()),
                "days_after_action_standard": int(after_standard.sum()),
                "survives_filter_after_action": bool(
                    len(after) and after_standard.all()
                ),
                "ss_flag_after_action": " ".join(
                    sorted(after.ss_flag.dropna().astype(str).unique())
                ),
                "contract_size_after_action": " ".join(
                    f"{size:g}"
                    for size in sorted(after.contract_size.dropna().unique())
                ),
                "delta_null_days_after_action": int(after.delta.isna().sum()),
            }
        )
    return pd.DataFrame(daily), pd.DataFrame(traced)


# D8 --------------------------------------------------------------------------------


def cycle_counts(cycles: pd.DataFrame) -> pd.DataFrame:
    """Estimation and holdout counts and the boundary dates against the section 10
    table, each with the spec's value and whether they agree."""
    rows = []

    def add(item: str, measured, expected) -> None:
        rows.append(
            {
                "item": item,
                "measured": str(measured),
                "spec": str(expected),
                "agrees": str(measured) == str(expected),
            }
        )

    for ticker, group in cycles.groupby("ticker"):
        add(
            f"{ticker} estimation cycles",
            int((group.window == "estimation").sum()),
            EXPECTED_ESTIMATION_CYCLES[ticker],
        )
        add(
            f"{ticker} holdout cycles",
            int((group.window == "holdout").sum()),
            EXPECTED_HOLDOUT_CYCLES,
        )
        add(
            f"{ticker} first entry",
            group.entry.min().date(),
            EXPECTED_FIRST_ENTRY[ticker],
        )
    estimation = cycles[cycles.window == "estimation"]
    holdout = cycles[cycles.window == "holdout"]
    add(
        "pooled estimation cycles",
        estimation.entry.nunique(),
        EXPECTED_POOLED_ESTIMATION_CYCLES,
    )
    add("pooled holdout cycles", holdout.entry.nunique(), EXPECTED_HOLDOUT_CYCLES)
    add(
        "last estimation entry",
        estimation.entry.max().date(),
        EXPECTED_LAST_ESTIMATION_ENTRY,
    )
    add("first holdout entry", holdout.entry.min().date(), EXPECTED_FIRST_HOLDOUT_ENTRY)
    add("last holdout entry", holdout.entry.max().date(), EXPECTED_LAST_HOLDOUT_ENTRY)
    add(
        "last holdout expiration",
        holdout.expiration.max().date(),
        EXPECTED_LAST_HOLDOUT_EXPIRATION,
    )
    return pd.DataFrame(rows)


# D9 --------------------------------------------------------------------------------


def implied_correlations(
    entries: pd.DataFrame, model_free: pd.DataFrame, surface: pd.DataFrame
) -> pd.DataFrame:
    """D9 correlations per fund and pooled, pairing entry K with item 1's 30-day
    model-free series on the entry date and with the same expiry under item 1's own
    rules, and pairing each implied measure with every other."""
    item1 = model_free[
        (model_free.node == 30)
        & (model_free.strike_floor == ITEM1_STRIKE_FLOOR)
        & (model_free.drop_code == OK)
    ][["ticker", "date", "implied_var"]].rename(
        columns={"date": "entry", "implied_var": "item1_model_free_30"}
    )
    iv30 = atm_implied_variance(surface[surface.node == 30])[
        ["ticker", "date", "implied_var_atm"]
    ].rename(columns={"date": "entry", "implied_var_atm": "iv30_squared"})
    frame = (
        entries[entries.strip_status == OK]
        .assign(sigma_atm_squared=lambda data: data.sigma_atm**2)
        .merge(item1, on=["ticker", "entry"], how="left")
        .merge(iv30, on=["ticker", "entry"], how="left")
    )
    pairs = [
        ("k_strip", "item1_model_free_30"),
        ("k_strip", "sigma_atm_squared"),
        ("k_strip", "iv30_squared"),
        ("sigma_atm_squared", "iv30_squared"),
        ("sigma_atm_squared", "item1_model_free_30"),
        ("iv30_squared", "item1_model_free_30"),
        ("k_strip", "k_item1_rules"),
    ]
    rows = []
    for ticker, group in _with_pooled(frame).groupby("ticker"):
        for left, right in pairs:
            both = group[[left, right]].dropna()
            ratio = both[left] / both[right]
            rows.append(
                {
                    "ticker": ticker,
                    "left": left,
                    "right": right,
                    "n": len(both),
                    "correlation": both[left].corr(both[right]),
                    "log_correlation": np.log(both[left]).corr(np.log(both[right])),
                    "median_ratio": ratio.median(),
                    "p05_ratio": ratio.quantile(0.05),
                    "p95_ratio": ratio.quantile(0.95),
                }
            )
    return pd.DataFrame(rows)


# D10 -------------------------------------------------------------------------------


def shortfall_and_rounding(entries: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """D10 distributions per fund and year, on every strip cycle and on the floor-passing
    subset, of K from listed strikes over the flat-tail K and of the entry premium in
    dollars at which integer rounding moves K by less than one percent."""
    strip = entries[entries.strip_status == OK]
    frame = pd.concat(
        [
            strip.assign(rule="section 3"),
            strip[strip.floor_pass.eq(True)].assign(rule="section 3 and rule 2 floor"),
        ],
        ignore_index=True,
    )
    frame = _with_pooled(frame)
    frame = pd.concat(
        [frame.assign(year=frame.entry_year.astype(str)), frame.assign(year=ALL)],
        ignore_index=True,
    )
    shortfall, rounding = [], []
    for (rule, ticker, year), group in frame.groupby(["rule", "ticker", "year"]):
        keys = {"rule": rule, "ticker": ticker, "entry_year": year}
        shortfall.append(
            {
                **keys,
                **_percentile_row(group.shortfall_ratio),
                "share_below_0.95": (group.shortfall_ratio < 0.95).mean(),
                "share_above_1": (group.shortfall_ratio > 1.0).mean(),
            }
        )
        rounding.append(
            {
                **keys,
                "never_settles": int(group.rounding_size.isna().sum()),
                **_percentile_row(group.rounding_size, "size_"),
                **_percentile_row(group.rounding_contracts, "contracts_"),
            }
        )
    return pd.DataFrame(shortfall), pd.DataFrame(rounding)


# D11 -------------------------------------------------------------------------------

ITEM1_CACHE_COLUMNS = [
    "date",
    "exdate",
    "cp_flag",
    "strike_price",
    "best_bid",
    "best_offer",
    "forward_price",
    "am_settlement",
    "impl_volatility",
    "volume",
    "open_interest",
    "ss_flag",
    "root",
    "suffix",
    "contract_size",
]
REUSE_KEY = ["date", "exdate", "cp_flag", "strike_price", "ss_flag", "contract_size"]
ITEM3_ONLY_COLUMNS = [
    "optionid",
    "delta",
    "gamma",
    "vega",
    "theta",
    "expiry_indicator",
    "cfadj",
]


def _parquet_bytes(frame: pd.DataFrame) -> int:
    """Size of a frame written as zstd parquet."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "frame.parquet"
        frame.to_parquet(path, index=False, compression="zstd")
        return path.stat().st_size


def data_reuse(quotes: pd.DataFrame, cycles: pd.DataFrame) -> pd.DataFrame:
    """D11 counts the item 3 opprcd rows that item 1's cached ladder files already hold
    and checks that the cached values agree. It also sizes the incremental pull item 3
    would need if it read the cache, which covers item 3's own columns on cached rows and
    every column on the rest."""
    windows = cycles[["ticker", "exdate", "previous_expiration", "expiration"]]
    rows = []
    for ticker, own in quotes.groupby("ticker"):
        cache = pd.concat(
            [
                pd.read_parquet(path)
                for path in sorted(ITEM1_OPTION_QUOTES_DIR.glob(f"{ticker}_*.parquet"))
            ],
            ignore_index=True,
        )
        cache = cache.merge(windows[windows.ticker == ticker], on="exdate")
        cache = cache[
            (cache.date >= cache.previous_expiration) & (cache.date <= cache.expiration)
        ]
        cache = cache.astype(
            {"ss_flag": object, "cp_flag": object, "contract_size": float}
        ).assign(strike_price=cache.strike_price.astype(float).round(6))
        cache_duplicates = int(cache.duplicated(REUSE_KEY).sum())
        cache = cache.drop_duplicates(REUSE_KEY)
        own = own.assign(strike_price=own.strike_price.round(6))
        merged = own.merge(
            cache[REUSE_KEY + ["best_bid", "best_offer", "impl_volatility"]],
            on=REUSE_KEY,
            how="left",
            suffixes=("", "_cache"),
            indicator=True,
        )
        cached = merged._merge == "both"
        days_left = (merged.exdate - merged.date).dt.days
        agree = (
            cached
            & np.isclose(
                merged.best_bid, merged.best_bid_cache.astype(float), equal_nan=True
            )
            & np.isclose(
                merged.best_offer, merged.best_offer_cache.astype(float), equal_nan=True
            )
        )
        own_columns = [column for column in quotes.columns if column != "ticker"]
        incremental = merged.loc[cached, REUSE_KEY + ITEM3_ONLY_COLUMNS]
        uncached = merged.loc[~cached, own_columns]
        pulled_bytes = sum(
            path.stat().st_size for path in CYCLE_QUOTES_DIR.glob(f"{ticker}_*.parquet")
        )
        rows.append(
            {
                "ticker": ticker,
                "item3_rows": len(merged),
                "cached_rows": int(cached.sum()),
                "cached_share": cached.mean(),
                "cache_duplicate_keys": cache_duplicates,
                "uncached_rows_under_7_days": int((~cached & (days_left < 7)).sum()),
                "uncached_rows_7_days_or_more": int((~cached & (days_left >= 7)).sum()),
                "cached_quotes_agree_share": agree[cached].mean(),
                "cached_iv_agree_share": np.isclose(
                    merged.impl_volatility[cached],
                    merged.impl_volatility_cache[cached].astype(float),
                    equal_nan=True,
                ).mean(),
                "item3_pull_bytes": pulled_bytes,
                "incremental_on_cached_rows_bytes": _parquet_bytes(incremental),
                "incremental_uncached_rows_bytes": _parquet_bytes(uncached),
                "cache_first_date": cache.date.min(),
                "cache_min_days_to_expiry": int(
                    (cache.exdate - cache.date).dt.days.min()
                ),
            }
        )
    reuse = pd.DataFrame(rows)
    reuse["incremental_total_bytes"] = (
        reuse.incremental_on_cached_rows_bytes + reuse.incremental_uncached_rows_bytes
    )
    return reuse


def column_reuse(quotes: pd.DataFrame) -> pd.DataFrame:
    """D11 lists every opprcd column item 3 reads with its use, and whether item 1's
    cached ladder files carry it."""
    uses = {
        "date": "row key",
        "exdate": "row key",
        "cp_flag": "row key",
        "strike_price": "row key and strip strikes",
        "ss_flag": "section 3 row filter",
        "contract_size": "section 3 row filter",
        "best_bid": "row filter, entry mid, cost, marks",
        "best_offer": "row filter, entry mid, cost, marks",
        "impl_volatility": "σ_ATM and the delta fallback",
        "optionid": "tracking a leg through its cycle",
        "delta": "daily hedge",
        "gamma": "section 11 entry Greeks",
        "vega": "section 11 entry Greeks",
        "theta": "section 11 entry Greeks",
        "expiry_indicator": "identifying the standard monthly expiry",
        "cfadj": "tracking contracts through a corporate action",
        "am_settlement": "expiry identity under item 1's rules",
        "forward_price": "item 1's rule comparison in D9",
        "root": "contract identity before 2010",
        "suffix": "contract identity before 2010",
        "volume": "not used in session 1",
        "open_interest": "not used in session 1",
    }
    return pd.DataFrame(
        [
            {
                "column": column,
                "use": uses.get(column, ""),
                "in_item1_cache": column in ITEM1_CACHE_COLUMNS,
            }
            for column in quotes.columns
            if column not in ("ticker", "secid")
        ]
    )


def locked_crossed(panel: pd.DataFrame) -> pd.DataFrame:
    """D6 companion: among the strip marks of the zero-bid table, the two-sided quotes
    with the offer at or below the bid, split into locked and crossed per fund."""
    strip = panel[
        (panel.arm == "strip") & (panel.cycle_day >= 0) & (panel.days_to_expiration > 0)
    ]
    bid, offer = strip.best_bid, strip.best_offer
    frame = strip.assign(
        locked=((bid > 0) & (offer == bid)).fillna(False),
        crossed=((bid > 0) & (offer > 0) & (offer < bid)).fillna(False),
    )
    table = (
        _with_pooled(frame)
        .groupby("ticker")
        .agg(
            marks=("locked", "size"),
            locked=("locked", "sum"),
            crossed=("crossed", "sum"),
        )
        .reset_index()
    )
    table["locked_or_crossed"] = table.locked + table.crossed
    table["share_locked_or_crossed"] = table.locked_or_crossed / table.marks
    return table


def k_ratio_by_exdate(entries: pd.DataFrame, model_free: pd.DataFrame) -> pd.DataFrame:
    """D9 companion: entry K over item 1's 30-day model-free value on the entry date,
    split by whether the contract's recorded exdate falls on a Saturday, the convention
    before February 2015."""
    item1 = model_free[
        (model_free.node == 30)
        & (model_free.strike_floor == ITEM1_STRIKE_FLOOR)
        & (model_free.drop_code == OK)
    ][["ticker", "date", "implied_var"]].rename(
        columns={"date": "entry", "implied_var": "item1_model_free_30"}
    )
    frame = entries[entries.strip_status == OK].merge(item1, on=["ticker", "entry"])
    frame = frame.assign(
        ratio=frame.k_strip / frame.item1_model_free_30,
        exdate_convention=np.where(
            pd.to_datetime(frame.exdate).dt.dayofweek == 5, "Saturday", "trading day"
        ),
    )
    return (
        frame.groupby("exdate_convention")
        .ratio.agg(cycles="size", median_ratio="median", mean_ratio="mean")
        .reset_index()
    )
