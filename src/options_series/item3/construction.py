"""Entry construction of spec section 3 at each cycle's entry close, from the row
filters and the parity forward through the strike strip and its fair variance strike K
to the at-the-money straddle, with the section 8 replication shortfall and
integer-rounding size.

K is item 1's model-free sum on the section 3 strip, so K and item 1's series share one
implementation. The flat-tail comparison runs item 2's grid construction, which calls
the same sum. Sections 3 and 8 leave the following choices open, and this module fixed
them before it read any quote.
- Any construction that prices or trades both legs at a strike uses that strike only
  when its call and its put both pass the row filters. An out-of-the-money strike enters
  the strip when its one traded leg passes.
- The rate is item 1's zerocd interpolation in days, falling back to the nearest earlier
  curve date.
- Strip quantities run in proportion to w_i = ΔK_i / K_i², and the call and the put at
  K_0 share its weight equally, which prices K_0 at the average of the two mids.
- The traded span on each side runs in log strike from F, ln(F / lowest strike) below
  and ln(highest strike / F) above, in units of σ_ATM √T.
- Flat-tail extrapolation inverts each strip mid to a Black volatility on the parity
  forward, takes the mean of the two at K_0, interpolates linearly in strike and holds
  the edge volatility flat beyond the outermost listed strike, on item 2's 1,000-strike
  grid.
- Rounding size is entry premium in dollars. The threshold is the smallest size on the
  geometric grid from which rounding every leg to the nearest contract moves K by less
  than one percent at that size and every larger one.
"""

from __future__ import annotations

from math import exp, sqrt

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from options_series.item1.model_free_variance import (
    black_scholes_price,
    expiry_variance,
    model_free_sum,
    standard_settlement_quotes,
    zero_rate,
)
from options_series.item2.surface_variance import (
    _node_curve,
    _strike_grid,
    grid_variance,
)
from options_series.item3.config import (
    CALENDAR_DAYS_PER_YEAR,
    ROUNDING_GRID_POINTS,
    ROUNDING_SIZE_RANGE,
    ROUNDING_TOLERANCE,
    SHORTFALL_GRID_POINTS,
    STANDARD_CONTRACT_SIZE,
    STANDARD_SETTLEMENT_FLAG,
    STRADDLE_MAX_DISTANCE,
    STRIP_MIN_SPAN,
    STRIP_MIN_STRIKES,
)

OK = "OK"
NO_QUOTES = "NO_QUOTES"
NO_PAIR = "NO_PAIR"
NO_K0 = "NO_K0"
ONE_SIDED = "ONE_SIDED"
BAD_VARIANCE = "BAD_VARIANCE"
FAR_FROM_FORWARD = "FAR_FROM_FORWARD"

LEG_COLUMNS = ["optionid", "cp_flag", "strike_price", "best_bid", "best_offer"]
ROUNDING_SIZES = np.geomspace(*ROUNDING_SIZE_RANGE, ROUNDING_GRID_POINTS)


class ZeroCurve:
    """Item 1's zero rate by date and days, falling back to the nearest earlier date."""

    def __init__(self, curve: pd.DataFrame) -> None:
        curve = curve.sort_values(["date", "days"])
        self.curves = {
            date: (group.days.values.astype(float), group.rate.values.astype(float))
            for date, group in curve.groupby("date")
        }
        self.dates = np.array(sorted(self.curves))

    def rate(self, date: pd.Timestamp, days: float) -> float:
        """Zero rate as a decimal per annum at the given days to maturity."""
        position = np.searchsorted(self.dates, np.datetime64(date), side="right") - 1
        if position < 0:
            raise ValueError(f"no zero curve on or before {date.date()}")
        return zero_rate(*self.curves[self.dates[position]], days)


def passes_filters(quotes: pd.DataFrame) -> pd.Series:
    """Section 3 row filters, which require a standard-settlement contract on 100 shares
    with a positive bid and an offer above it."""
    return (
        (quotes.ss_flag == STANDARD_SETTLEMENT_FLAG)
        & (quotes.contract_size == STANDARD_CONTRACT_SIZE)
        & (quotes.best_bid > 0)
        & (quotes.best_offer > quotes.best_bid)
    )


def strike_weights(strikes: np.ndarray) -> np.ndarray:
    """Weights w_i = ΔK_i / K_i² on an ascending strike ladder, with ΔK_i half the
    distance between the neighbouring strikes and each end strike's distance to its one
    neighbour. This is the spacing of item 1's sum, and build_entry checks that the
    weights reproduce it."""
    spacing = np.empty_like(strikes)
    spacing[1:-1] = (strikes[2:] - strikes[:-2]) / 2.0
    spacing[0] = strikes[1] - strikes[0]
    spacing[-1] = strikes[-1] - strikes[-2]
    return spacing / strikes**2


def black_volatility(
    price: float, forward: float, strike: float, years: float, rate: float, cp_flag: str
) -> float:
    """Black volatility on the forward that reprices an option mid, NaN when the mid
    lies outside the no-arbitrage bounds."""
    discount = exp(-rate * years)
    intrinsic = discount * max(
        forward - strike if cp_flag == "C" else strike - forward, 0.0
    )
    ceiling = discount * (forward if cp_flag == "C" else strike)
    if not intrinsic < price < ceiling:
        return np.nan
    spot = forward * discount

    def gap(vol: float) -> float:
        return black_scholes_price(spot, strike, years, rate, vol, cp_flag) - price

    try:
        return brentq(gap, 1e-4, 20.0, xtol=1e-10)
    except ValueError:
        return np.nan


def _mids(legs: pd.DataFrame) -> np.ndarray:
    """Mid quotes of a leg frame."""
    return 0.5 * (legs.best_bid.values + legs.best_offer.values)


def _legs(
    passing: pd.DataFrame, strikes: np.ndarray, cp_flag: str, weight
) -> pd.DataFrame:
    """Passing legs of one option type at the given strikes, ascending, with a weight."""
    legs = passing[(passing.cp_flag == cp_flag) & passing.strike_price.isin(strikes)]
    return legs.sort_values("strike_price")[LEG_COLUMNS].assign(weight=weight)


def build_entry(
    quotes: pd.DataFrame, years: float, rate: float
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    """Section 3 construction on one cycle's entry-close quotes for its expiry, returning
    the record of every entry quantity and the legs of each arm."""
    standard = (quotes.ss_flag == STANDARD_SETTLEMENT_FLAG) & (
        quotes.contract_size == STANDARD_CONTRACT_SIZE
    )
    passing = quotes[passes_filters(quotes)]
    record: dict[str, object] = {
        "rows": len(quotes),
        "standard_rows": int(standard.sum()),
        "passing_rows": len(passing),
        "duplicate_legs": int(passing.duplicated(["cp_flag", "strike_price"]).sum()),
        "strip_status": NO_QUOTES,
        "straddle_status": NO_QUOTES,
    }
    empty = pd.DataFrame(columns=[*LEG_COLUMNS, "weight"])
    if record["duplicate_legs"]:
        raise ValueError("duplicate passing legs at one strike; no rule selects one")
    if not len(passing):
        return record, empty, empty
    call_mid = passing[passing.cp_flag == "C"].set_index("strike_price")
    put_mid = passing[passing.cp_flag == "P"].set_index("strike_price")
    paired = np.sort(call_mid.index.intersection(put_mid.index).values)
    record["paired_strikes"] = len(paired)
    if not len(paired):
        record["strip_status"] = record["straddle_status"] = NO_PAIR
        return record, empty, empty
    call_mid = pd.Series(_mids(call_mid), index=call_mid.index)
    put_mid = pd.Series(_mids(put_mid), index=put_mid.index)

    # np.argmin returns the first minimum, the lower strike on a tie.
    gap = np.abs(call_mid[paired].values - put_mid[paired].values)
    parity_strike = float(paired[int(np.argmin(gap))])
    forward = parity_strike + exp(rate * years) * float(
        call_mid[parity_strike] - put_mid[parity_strike]
    )
    record["parity_strike"], record["forward"] = parity_strike, forward

    straddle_strike = float(paired[int(np.argmin(np.abs(paired - forward)))])
    straddle = pd.concat(
        [
            _legs(passing, [straddle_strike], "C", 1.0),
            _legs(passing, [straddle_strike], "P", 1.0),
        ],
        ignore_index=True,
    )
    atm_vols = passing[passing.strike_price == straddle_strike].impl_volatility
    record["straddle_strike"] = straddle_strike
    record["straddle_distance"] = abs(straddle_strike - forward) / forward
    record["sigma_atm"] = float(atm_vols.mean(skipna=False))
    if record["straddle_distance"] > STRADDLE_MAX_DISTANCE:
        record["straddle_status"] = FAR_FROM_FORWARD
        straddle = empty
    else:
        record["straddle_status"] = OK
        record["straddle_premium"] = float(_mids(straddle).sum())
        record["straddle_half_spread"] = float(
            (0.5 * (straddle.best_offer - straddle.best_bid)).sum()
        )

    below = paired[paired < forward]
    if not len(below):
        record["strip_status"] = NO_K0
        return record, empty, straddle
    k0 = float(below.max())
    put_strikes = np.sort(put_mid.index[put_mid.index < k0].values)
    call_strikes = np.sort(call_mid.index[call_mid.index > k0].values)
    record["k0"] = k0
    record["strip_puts"], record["strip_calls"] = len(put_strikes), len(call_strikes)
    if not len(put_strikes) or not len(call_strikes):
        record["strip_status"] = ONE_SIDED
        return record, empty, straddle

    strikes = np.concatenate([put_strikes, [k0], call_strikes])
    prices = np.concatenate(
        [
            put_mid[put_strikes].values,
            [0.5 * (call_mid[k0] + put_mid[k0])],
            call_mid[call_strikes].values,
        ]
    )
    fair_strike = model_free_sum(strikes, prices, forward, k0, years, rate)
    weights = strike_weights(strikes)
    replicated = (2.0 * exp(rate * years) / years) * float(np.sum(weights * prices)) - (
        forward / k0 - 1.0
    ) ** 2 / years
    if not np.isclose(replicated, fair_strike, rtol=1e-10, atol=0.0):
        raise AssertionError("strip weights do not reproduce item 1's sum")
    record["lowest_strike"], record["highest_strike"] = strikes[0], strikes[-1]
    record["k_strip"] = fair_strike
    if not np.isfinite(fair_strike) or fair_strike <= 0:
        record["strip_status"] = BAD_VARIANCE
        return record, empty, straddle
    record["strip_status"] = OK

    k0_weight = weights[len(put_strikes)] / 2.0
    strip = pd.concat(
        [
            _legs(passing, put_strikes, "P", weights[: len(put_strikes)]),
            _legs(passing, [k0], "C", k0_weight),
            _legs(passing, [k0], "P", k0_weight),
            _legs(passing, call_strikes, "C", weights[len(put_strikes) + 1 :]),
        ],
        ignore_index=True,
    )
    mids = _mids(strip)
    record["strip_premium_per_weight"] = float(np.sum(strip.weight * mids))
    record["strip_half_spread_per_weight"] = float(
        np.sum(strip.weight * 0.5 * (strip.best_offer - strip.best_bid))
    )

    scale = record["sigma_atm"] * sqrt(years)
    record["span_put"] = np.log(forward / strikes[0]) / scale
    record["span_call"] = np.log(strikes[-1] / forward) / scale
    record["span_put_price"] = (forward - strikes[0]) / forward / scale
    record["span_call_price"] = (strikes[-1] - forward) / forward / scale
    record["floor_pass"] = bool(
        len(put_strikes) >= STRIP_MIN_STRIKES
        and len(call_strikes) >= STRIP_MIN_STRIKES
        and record["span_put"] >= STRIP_MIN_SPAN
        and record["span_call"] >= STRIP_MIN_SPAN
    )

    record["k_flat_tail"] = flat_tail_variance(strikes, strip, k0, forward, years, rate)
    record["shortfall_ratio"] = fair_strike / record["k_flat_tail"]
    record["rounding_size"], record["rounding_contracts"] = rounding_threshold(
        strikes, strip, k0, forward, years, rate, fair_strike
    )
    return record, strip, straddle


def flat_tail_variance(
    strikes: np.ndarray,
    strip: pd.DataFrame,
    k0: float,
    forward: float,
    years: float,
    rate: float,
) -> float:
    """Model-free variance with flat-tail extrapolation on item 2's 1,000-strike grid
    from the strip's Black volatilities, the mean of call and put at K_0."""
    leg_vols = pd.Series(
        [
            black_volatility(mid, forward, leg.strike_price, years, rate, leg.cp_flag)
            for leg, mid in zip(strip.itertuples(), _mids(strip))
        ],
        index=strip.strike_price.values,
    )
    node_vols = leg_vols.groupby(level=0).mean().reindex(strikes).values
    valid = np.isfinite(node_vols)
    if valid.sum() < 2:
        return np.nan
    node_strikes, node_vols = _node_curve(strikes[valid], node_vols[valid])
    grid = _strike_grid(
        forward, years, rate, node_strikes, node_vols, SHORTFALL_GRID_POINTS
    )
    return grid_variance(
        grid, np.interp(grid, node_strikes, node_vols), forward, years, rate
    )


def rounding_threshold(
    strikes: np.ndarray,
    strip: pd.DataFrame,
    k0: float,
    forward: float,
    years: float,
    rate: float,
    fair_strike: float,
) -> tuple[float, float]:
    """Smallest entry premium in dollars from which rounding every leg to the nearest
    whole contract moves K by less than the tolerance at that size and every larger grid
    size, and the total contracts at that size; NaN when the grid never settles. Each
    rounded K runs item 1's sum on mids that each leg's rounded to continuous quantity
    ratio scales."""
    mids = _mids(strip)
    weights = strip.weight.values.astype(float)
    leg_strikes = strip.strike_price.values
    below, at_k0, above = leg_strikes < k0, leg_strikes == k0, leg_strikes > k0
    contracts = (
        ROUNDING_SIZES[:, None]
        * weights[None, :]
        / (float(np.sum(weights * mids)) * 100.0)
    )
    rounded = np.floor(contracts + 0.5)
    scaled = mids[None, :] * rounded / contracts
    deviations = np.array(
        [
            abs(
                model_free_sum(
                    strikes,
                    np.concatenate([row[below], [row[at_k0].mean()], row[above]]),
                    forward,
                    k0,
                    years,
                    rate,
                )
                / fair_strike
                - 1.0
            )
            for row in scaled
        ]
    )
    failing = np.flatnonzero(deviations >= ROUNDING_TOLERANCE)
    settled = failing[-1] + 1 if len(failing) else 0
    if settled == len(ROUNDING_SIZES):
        return np.nan, np.nan
    return float(ROUNDING_SIZES[settled]), float(rounded[settled].sum())


def item1_rule_variance(
    quotes: pd.DataFrame,
    date: pd.Timestamp,
    exdate: pd.Timestamp,
    curve: ZeroCurve,
) -> float:
    """The same expiry's variance under item 1's own rules and code path, with T running
    to the OptionMetrics exdate."""
    days = (exdate - date).days
    result = expiry_variance(
        standard_settlement_quotes(quotes),
        days / CALENDAR_DAYS_PER_YEAR,
        curve.rate(date, days),
    )
    return result.variance if result.failure is None else np.nan


def resolve_exdates(cycles: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    """Each cycle's OptionMetrics exdate, the candidate whose rows carry no
    expiry_indicator. A cycle that matches no candidate or more than one raises an
    error."""
    standard = quotes[quotes.expiry_indicator.isna()]
    held = set(zip(standard.ticker, standard.exdate))
    exdates = []
    for cycle in cycles.itertuples():
        found = [
            exdate
            for exdate in cycle.exdate_candidates
            if (cycle.ticker, exdate) in held
        ]
        if len(found) != 1:
            raise ValueError(
                f"{cycle.ticker} cycle {cycle.cycle}: {len(found)} standard exdates"
            )
        exdates.append(found[0])
    return cycles.assign(exdate=exdates)


def build_entries(
    cycles: pd.DataFrame, quotes: pd.DataFrame, curve: ZeroCurve
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The section 3 entry of every cycle, as one record per cycle with every entry
    quantity and the same expiry's variance under item 1's rules, and one row per leg of
    either arm with its entry moneyness in units of σ_ATM √T."""
    on_entry = quotes.merge(
        cycles[["ticker", "cycle", "entry", "exdate"]],
        left_on=["ticker", "date", "exdate"],
        right_on=["ticker", "entry", "exdate"],
    )
    by_cycle = dict(iter(on_entry.groupby(["ticker", "cycle"])))
    records, legs = [], []
    for cycle in cycles.itertuples():
        chain = by_cycle.get((cycle.ticker, cycle.cycle), on_entry.iloc[0:0])
        rate = curve.rate(cycle.entry, cycle.days_to_expiration)
        record, strip, straddle = build_entry(chain, cycle.years_to_expiration, rate)
        record["k_item1_rules"] = (
            item1_rule_variance(chain, cycle.entry, cycle.exdate, curve)
            if len(chain)
            else np.nan
        )
        records.append(
            {"ticker": cycle.ticker, "cycle": cycle.cycle, "rate": rate, **record}
        )
        scale = record.get("sigma_atm", np.nan) * sqrt(cycle.years_to_expiration)
        for arm, frame in (("strip", strip), ("straddle", straddle)):
            if len(frame):
                legs.append(
                    frame.assign(
                        ticker=cycle.ticker,
                        cycle=cycle.cycle,
                        arm=arm,
                        moneyness=np.log(
                            frame.strike_price.values.astype(float) / record["forward"]
                        )
                        / scale,
                    )
                )
    entries = cycles.merge(pd.DataFrame(records), on=["ticker", "cycle"])
    return entries, pd.concat(legs, ignore_index=True)
