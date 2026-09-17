"""Implied variance: the model-free construction of spec section 6.1 from option
quotes, the at-the-money measure of section 6.2, and the checks on the construction.

Construction choices section 6.1 leaves open, recorded in spec section 13: an expiry
is identified by (exdate, am_settlement); the at-the-money midquote uses the single
usable leg when the other is missing; a quote is usable when best_bid > 0 and
best_offer >= best_bid; the stop after two consecutive zero-bid strikes is counted
along quoted rows; strike counts for the floor exclude the at-the-money strike; the
zero rate falls back to the nearest earlier curve date.
"""

from __future__ import annotations

import logging
from math import sqrt
from typing import NamedTuple

import numpy as np
import pandas as pd
from scipy.special import ndtr

from options_series.item1.config import (
    BENCHMARK,
    CALENDAR_DAYS_PER_YEAR,
    MIN_DAYS_TO_EXPIRY,
    NODES,
    ROBUSTNESS_STRIKE_FLOOR,
    SECIDS,
    STANDARD_CONTRACT_SIZE,
    STANDARD_SETTLEMENT_FLAG,
    STRIKE_FLOOR,
    VIX_MAX_MEDIAN_GAP,
    VIX_MIN_CORRELATION,
)
from options_series.item1.pull_options import load_option_quotes, option_years

LOGGER = logging.getLogger(__name__)

OK = "OK"
NO_QUOTES = "NO_QUOTES"
NO_BRACKET = "NO_BRACKET"
NO_FORWARD_NEAR = "NO_FORWARD_NEAR"
NO_FORWARD_FAR = "NO_FORWARD_FAR"
NO_ATM_STRIKE_NEAR = "NO_ATM_STRIKE_NEAR"
NO_ATM_STRIKE_FAR = "NO_ATM_STRIKE_FAR"
FEW_STRIKES_NEAR = "FEW_STRIKES_NEAR"
FEW_STRIKES_FAR = "FEW_STRIKES_FAR"
BAD_VARIANCE = "BAD_VARIANCE"

EXPIRY_KEY = ["exdate", "am_settlement", "cp_flag", "strike_price"]


class ExpiryVariance(NamedTuple):
    """Model-free variance of one expiry, annualised, and the ladder behind it."""

    variance: float
    forward: float
    atm_strike: float
    put_count: int
    call_count: int
    failure: str | None
    years_to_expiry: float


def standard_settlement_quotes(quotes: pd.DataFrame) -> pd.DataFrame:
    """Quotes on standard-settlement contracts of 100 shares only (spec section 13)."""
    return quotes[
        (quotes.ss_flag == STANDARD_SETTLEMENT_FLAG)
        & (quotes.contract_size == STANDARD_CONTRACT_SIZE)
    ]


def zero_rate(
    curve_days: np.ndarray, curve_rates: np.ndarray, days_to_expiry: float
) -> float:
    """Zero rate as a decimal per annum, interpolated linearly in days to expiry."""
    return float(np.interp(days_to_expiry, curve_days, curve_rates)) / 100.0


def _usable(bids: pd.Series, offers: pd.Series) -> pd.Series:
    """True where a quote has a positive bid and an offer at or above it."""
    return (bids > 0) & (offers >= bids)


def _out_of_the_money_ladder(
    strikes: np.ndarray, bids: np.ndarray, offers: np.ndarray, descending: bool
) -> tuple[np.ndarray, np.ndarray]:
    """Strikes and midquotes kept walking away from the money, stopping after two
    consecutive zero-bid strikes."""
    order = np.argsort(strikes)
    if descending:
        order = order[::-1]
    strikes, bids, offers = strikes[order], bids[order], offers[order]
    kept_strikes, kept_mids, zero_bid_run = [], [], 0
    for strike, bid, offer in zip(strikes, bids, offers):
        if bid > 0 and offer >= bid:
            zero_bid_run = 0
            kept_strikes.append(strike)
            kept_mids.append(0.5 * (bid + offer))
        else:
            zero_bid_run += 1
            if zero_bid_run >= 2:
                break
    return np.array(kept_strikes, float), np.array(kept_mids, float)


def model_free_sum(
    strikes: np.ndarray,
    prices: np.ndarray,
    forward: float,
    atm_strike: float,
    years_to_expiry: float,
    rate: float,
) -> float:
    """Annualised model-free variance from out-of-the-money prices on an ascending strike
    grid (spec section 6.1 step 4), each strike weighted by the half-distance between its
    neighbours and the end strikes by the distance to their one neighbour."""
    strike_spacing = np.empty_like(strikes)
    strike_spacing[1:-1] = (strikes[2:] - strikes[:-2]) / 2.0
    strike_spacing[0] = strikes[1] - strikes[0]
    strike_spacing[-1] = strikes[-1] - strikes[-2]

    variance = (2.0 / years_to_expiry) * np.sum(
        strike_spacing / strikes**2 * np.exp(rate * years_to_expiry) * prices
    ) - (1.0 / years_to_expiry) * (forward / atm_strike - 1.0) ** 2
    return float(variance)


def expiry_variance(
    quotes: pd.DataFrame, years_to_expiry: float, rate: float
) -> ExpiryVariance:
    """Model-free variance of one expiry, annualised (spec section 6.1 steps 2 to 4)."""
    calls = quotes[quotes.cp_flag == "C"]
    puts = quotes[quotes.cp_flag == "P"]
    if len(calls) == 0 or len(puts) == 0:
        return ExpiryVariance(
            np.nan, np.nan, np.nan, 0, 0, "no_forward", years_to_expiry
        )

    published_forward = quotes["forward_price"].dropna()
    if len(published_forward):
        forward = float(published_forward.iloc[0])
    else:
        price_columns = ["strike_price", "best_bid", "best_offer"]
        usable_calls = calls[_usable(calls.best_bid, calls.best_offer)][price_columns]
        usable_puts = puts[_usable(puts.best_bid, puts.best_offer)][price_columns]
        pairs = usable_calls.merge(
            usable_puts, on="strike_price", suffixes=("_call", "_put")
        )
        if not len(pairs):
            return ExpiryVariance(
                np.nan, np.nan, np.nan, 0, 0, "no_forward", years_to_expiry
            )
        call_mid = 0.5 * (pairs.best_bid_call + pairs.best_offer_call)
        put_mid = 0.5 * (pairs.best_bid_put + pairs.best_offer_put)
        closest = int(np.argmin(np.abs((call_mid - put_mid).values)))
        parity_strike = float(pairs.strike_price.values[closest])
        forward = parity_strike + np.exp(rate * years_to_expiry) * float(
            call_mid.values[closest] - put_mid.values[closest]
        )

    strikes = np.unique(quotes.strike_price.values)
    strikes_at_or_below = strikes[strikes <= forward]
    if not len(strikes_at_or_below):
        return ExpiryVariance(
            np.nan, forward, np.nan, 0, 0, "no_atm_strike", years_to_expiry
        )
    atm_strike = float(strikes_at_or_below.max())

    otm_puts = puts[puts.strike_price < atm_strike]
    otm_calls = calls[calls.strike_price > atm_strike]
    put_strikes, put_mids = _out_of_the_money_ladder(
        otm_puts.strike_price.values,
        otm_puts.best_bid.values,
        otm_puts.best_offer.values,
        descending=True,
    )
    call_strikes, call_mids = _out_of_the_money_ladder(
        otm_calls.strike_price.values,
        otm_calls.best_bid.values,
        otm_calls.best_offer.values,
        descending=False,
    )
    put_count, call_count = len(put_strikes), len(call_strikes)

    atm_mids = []
    for leg in (
        calls[calls.strike_price == atm_strike],
        puts[puts.strike_price == atm_strike],
    ):
        if len(leg):
            bid, offer = float(leg.best_bid.iloc[0]), float(leg.best_offer.iloc[0])
            if bid > 0 and offer >= bid:
                atm_mids.append(0.5 * (bid + offer))
    if not atm_mids:
        return ExpiryVariance(
            np.nan,
            forward,
            atm_strike,
            put_count,
            call_count,
            "no_atm_strike",
            years_to_expiry,
        )

    ladder_strikes = np.concatenate([put_strikes[::-1], [atm_strike], call_strikes])
    ladder_mids = np.concatenate(
        [put_mids[::-1], [float(np.mean(atm_mids))], call_mids]
    )
    order = np.argsort(ladder_strikes)
    ladder_strikes, ladder_mids = ladder_strikes[order], ladder_mids[order]
    if len(ladder_strikes) < 2:
        return ExpiryVariance(
            np.nan,
            forward,
            atm_strike,
            put_count,
            call_count,
            "no_atm_strike",
            years_to_expiry,
        )
    variance = model_free_sum(
        ladder_strikes, ladder_mids, forward, atm_strike, years_to_expiry, rate
    )
    return ExpiryVariance(
        variance,
        float(forward),
        atm_strike,
        int(put_count),
        int(call_count),
        None,
        years_to_expiry,
    )


def _empty_record(drop_code: str) -> dict[str, object]:
    """Record for a node dropped before any expiry was selected."""
    return {
        "implied_var": np.nan,
        "expiry_near": pd.NaT,
        "expiry_far": pd.NaT,
        "near_put_count": 0,
        "near_call_count": 0,
        "far_put_count": 0,
        "far_call_count": 0,
        "drop_code": drop_code,
    }


def _node_record(
    node: int,
    near: pd.Series,
    far: pd.Series,
    near_variance: ExpiryVariance,
    far_variance: ExpiryVariance,
    strike_floor: int,
) -> dict[str, object]:
    """Node variance interpolated in total variance, or the step that dropped it."""
    record = {
        "implied_var": np.nan,
        "expiry_near": near.exdate,
        "expiry_far": far.exdate,
        "near_put_count": near_variance.put_count,
        "near_call_count": near_variance.call_count,
        "far_put_count": far_variance.put_count,
        "far_call_count": far_variance.call_count,
    }
    failures = (
        (near_variance.failure == "no_forward", NO_FORWARD_NEAR),
        (near_variance.failure == "no_atm_strike", NO_ATM_STRIKE_NEAR),
        (far_variance.failure == "no_forward", NO_FORWARD_FAR),
        (far_variance.failure == "no_atm_strike", NO_ATM_STRIKE_FAR),
        (
            near_variance.put_count < strike_floor
            or near_variance.call_count < strike_floor,
            FEW_STRIKES_NEAR,
        ),
        (
            far_variance.put_count < strike_floor
            or far_variance.call_count < strike_floor,
            FEW_STRIKES_FAR,
        ),
        (far_variance.years_to_expiry <= near_variance.years_to_expiry, NO_BRACKET),
    )
    for failed, drop_code in failures:
        if failed:
            return {**record, "drop_code": drop_code}

    node_years = node / CALENDAR_DAYS_PER_YEAR
    near_weight = (far_variance.years_to_expiry - node_years) / (
        far_variance.years_to_expiry - near_variance.years_to_expiry
    )
    total_variance = (
        near_weight * near_variance.variance * near_variance.years_to_expiry
        + (1.0 - near_weight) * far_variance.variance * far_variance.years_to_expiry
    )
    implied_var = total_variance / node_years
    if not np.isfinite(implied_var) or implied_var <= 0:
        return {**record, "drop_code": BAD_VARIANCE}
    return {**record, "implied_var": float(implied_var), "drop_code": OK}


def model_free_variance_for_date(
    date: pd.Timestamp,
    quotes: pd.DataFrame,
    curve_days: np.ndarray,
    curve_rates: np.ndarray,
    nodes: tuple[int, ...] = NODES,
    strike_floors: tuple[int, ...] = (STRIKE_FLOOR,),
) -> dict[int, dict[int, dict[str, object]]]:
    """Annualised model-free variance per strike floor and node for one date's quotes
    (spec section 6.1 steps 1 to 6)."""
    if not len(quotes):
        return {
            floor: {node: _empty_record(NO_QUOTES) for node in nodes}
            for floor in strike_floors
        }
    if quotes.duplicated(EXPIRY_KEY).any():
        quotes = quotes.sort_values(
            ["open_interest", "volume", "best_bid"], ascending=False, na_position="last"
        ).drop_duplicates(EXPIRY_KEY)

    quotes = quotes.assign(days_to_expiry=(quotes.exdate - date).dt.days)
    quotes = quotes[quotes.days_to_expiry >= MIN_DAYS_TO_EXPIRY]
    if not len(quotes):
        return {
            floor: {node: _empty_record(NO_BRACKET) for node in nodes}
            for floor in strike_floors
        }

    expiries = (
        quotes.groupby(["exdate", "am_settlement"], dropna=False)
        .agg(
            days_to_expiry=("days_to_expiry", "first"),
            quote_count=("strike_price", "size"),
        )
        .reset_index()
        .sort_values(["days_to_expiry", "quote_count"], ascending=[True, False])
        .drop_duplicates("days_to_expiry")
    )

    variances: dict[tuple, ExpiryVariance] = {}

    def variance_of(expiry: pd.Series) -> ExpiryVariance:
        key = (expiry.exdate, expiry.am_settlement)
        if key not in variances:
            same_settlement = quotes.am_settlement.eq(expiry.am_settlement) | (
                quotes.am_settlement.isna() & pd.isna(expiry.am_settlement)
            )
            expiry_quotes = quotes[(quotes.exdate == expiry.exdate) & same_settlement]
            variances[key] = expiry_variance(
                expiry_quotes,
                expiry.days_to_expiry / CALENDAR_DAYS_PER_YEAR,
                zero_rate(curve_days, curve_rates, expiry.days_to_expiry),
            )
        return variances[key]

    results: dict[int, dict[int, dict[str, object]]] = {
        floor: {} for floor in strike_floors
    }
    for node in nodes:
        below = expiries[expiries.days_to_expiry <= node]
        above = expiries[expiries.days_to_expiry > node]
        if not len(below) or not len(above):
            for floor in strike_floors:
                results[floor][node] = _empty_record(NO_BRACKET)
            continue
        near = below.iloc[below.days_to_expiry.values.argmax()]
        far = above.iloc[above.days_to_expiry.values.argmin()]
        near_variance, far_variance = variance_of(near), variance_of(far)
        for floor in strike_floors:
            results[floor][node] = _node_record(
                node, near, far, near_variance, far_variance, floor
            )
    return results


def build_model_free_variance(
    zero_curve: pd.DataFrame,
    strike_floors: tuple[int, ...] = (STRIKE_FLOOR, ROBUSTNESS_STRIKE_FLOOR),
) -> pd.DataFrame:
    """Annualised model-free variance for every underlying, date, node and strike floor."""
    curves = {
        date: (group.days.values.astype(float), group.rate.values.astype(float))
        for date, group in zero_curve.sort_values(["date", "days"]).groupby("date")
    }
    curve_dates = np.array(sorted(curves))
    rows = []
    for ticker, secid in SECIDS.items():
        for year in option_years(ticker):
            quotes = standard_settlement_quotes(load_option_quotes(ticker, year))
            for date, day_quotes in quotes.groupby("date", sort=True):
                if date in curves:
                    curve_days, curve_rates = curves[date]
                else:
                    earlier = np.searchsorted(curve_dates, date) - 1
                    if earlier < 0:
                        raise ValueError(f"no zero curve on or before {date.date()}")
                    curve_days, curve_rates = curves[curve_dates[earlier]]
                by_floor = model_free_variance_for_date(
                    date, day_quotes, curve_days, curve_rates, NODES, strike_floors
                )
                for floor, by_node in by_floor.items():
                    for node, record in by_node.items():
                        rows.append(
                            {
                                "secid": secid,
                                "ticker": ticker,
                                "date": date,
                                "node": node,
                                "strike_floor": floor,
                                **record,
                            }
                        )
            LOGGER.info("model-free variance %s %d done", ticker, year)
    model_free = pd.DataFrame(rows)
    model_free["year"] = model_free.date.dt.year
    return model_free


def atm_implied_variance(surface: pd.DataFrame) -> pd.DataFrame:
    """At-the-money implied variance: the squared mean of the call and put volatility."""
    surface = surface.copy()
    surface["atm_vol"] = surface[["iv_call_50", "iv_put_50"]].mean(axis=1, skipna=False)
    surface["implied_var_atm"] = surface.atm_vol**2
    return surface


def validate_against_vix(
    model_free: pd.DataFrame, vix: pd.DataFrame
) -> tuple[dict[str, float | int | bool], pd.DataFrame]:
    """Agreement of SPX 30-day model-free volatility with the VIX close, in vol points,
    and the merged daily series."""
    spx = model_free[
        (model_free.ticker == BENCHMARK)
        & (model_free.node == 30)
        & (model_free.strike_floor == STRIKE_FLOOR)
        & (model_free.drop_code == OK)
    ].copy()
    spx["model_free_vol"] = np.sqrt(spx.implied_var) * 100.0
    merged = spx[["date", "model_free_vol"]].merge(vix[["date", "vix"]], on="date")
    merged = merged.dropna(subset=["model_free_vol", "vix"])
    merged["gap"] = merged.model_free_vol - merged.vix
    correlation = float(np.corrcoef(merged.model_free_vol, merged.vix)[0, 1])
    median_abs_gap = float(merged.gap.abs().median())
    summary = {
        "dates": len(merged),
        "correlation": correlation,
        "mean_gap": float(merged.gap.mean()),
        "median_gap": float(merged.gap.median()),
        "median_abs_gap": median_abs_gap,
        "dates_over_two_points": int((merged.gap.abs() > 2).sum()),
        "passed": correlation >= VIX_MIN_CORRELATION
        and median_abs_gap <= VIX_MAX_MEDIAN_GAP,
    }
    return summary, merged


def black_scholes_price(
    spot: float,
    strike: float | np.ndarray,
    years: float,
    rate: float,
    vol: float | np.ndarray,
    cp_flag: str,
) -> float | np.ndarray:
    """Black-Scholes price of a European call or put on a non-dividend underlying,
    elementwise over arrays of strikes and volatilities."""
    d1 = (np.log(spot / strike) + (rate + 0.5 * vol * vol) * years) / (
        vol * np.sqrt(years)
    )
    d2 = d1 - vol * np.sqrt(years)
    if cp_flag == "C":
        return spot * ndtr(d1) - strike * np.exp(-rate * years) * ndtr(d2)
    return strike * np.exp(-rate * years) * ndtr(-d2) - spot * ndtr(-d1)


def _synthetic_chain(
    date: pd.Timestamp,
    spot: float,
    rate: float,
    vol: float,
    days_to_expiry: list[int],
    strikes: np.ndarray,
) -> pd.DataFrame:
    """Option quotes priced off a flat Black-Scholes volatility, half-cent wide."""
    rows = []
    for days in days_to_expiry:
        years = days / CALENDAR_DAYS_PER_YEAR
        exdate = date + pd.to_timedelta(int(days), unit="D")
        for strike in strikes:
            for cp_flag in ("C", "P"):
                price = black_scholes_price(spot, strike, years, rate, vol, cp_flag)
                rows.append(
                    {
                        "exdate": exdate,
                        "cp_flag": cp_flag,
                        "strike_price": float(strike),
                        "best_bid": max(price - 0.005, 0.0),
                        "best_offer": price + 0.005,
                        "forward_price": np.nan,
                        "am_settlement": 0.0,
                        "volume": 1.0,
                        "open_interest": 1.0,
                    }
                )
    return pd.DataFrame(rows)


def check_estimator_on_black_scholes() -> list[tuple[str, bool]]:
    """Checks that the estimator recovers a known volatility within 0.1 vol points and
    drops dates where section 6.1 says it should."""
    date = pd.Timestamp("2015-06-15")
    spot, rate, vol = 100.0, 0.02, 0.25
    curve_days = np.array([1.0, 30.0, 91.0, 365.0, 3669.0])
    curve_rates = np.full(5, rate * 100.0)
    strikes = np.arange(40.0, 200.5, 1.0)
    checks = []

    def at_node(quotes: pd.DataFrame, node: int) -> dict[str, object]:
        return model_free_variance_for_date(
            date, quotes, curve_days, curve_rates, (node,)
        )[STRIKE_FLOOR][node]

    chain = _synthetic_chain(date, spot, rate, vol, [21, 49, 80, 110], strikes)
    for node in NODES:
        record = at_node(chain, node)
        error = abs(sqrt(record["implied_var"]) - vol) * 100
        checks.append(
            (
                f"flat volatility at {node} days",
                record["drop_code"] == OK and error < 0.10,
            )
        )

    for true_vol in (0.10, 0.25, 0.60):
        single = _synthetic_chain(
            date, spot, rate, true_vol, [30], np.arange(20.0, 400.5, 0.5)
        )
        result = expiry_variance(single, 30 / CALENDAR_DAYS_PER_YEAR, rate)
        error = abs(sqrt(result.variance) - true_vol) * 100
        checks.append(
            (
                f"single expiry at volatility {true_vol}",
                result.failure is None and error < 0.10,
            )
        )

    thin = _synthetic_chain(
        date, spot, rate, vol, [21, 49], np.array([98.0, 99.0, 100.0, 101.0])
    )
    checks.append(
        ("thin ladder drops", at_node(thin, 30)["drop_code"] == FEW_STRIKES_NEAR)
    )
    short = _synthetic_chain(date, spot, rate, vol, [10, 20], strikes)
    checks.append(
        (
            "no expiry above the node drops",
            at_node(short, 30)["drop_code"] == NO_BRACKET,
        )
    )
    near_only = _synthetic_chain(date, spot, rate, vol, [2, 5], strikes)
    checks.append(
        (
            "expiries inside the seven-day floor drop",
            at_node(near_only, 30)["drop_code"] == NO_BRACKET,
        )
    )
    checks.append(
        ("empty quote set drops", at_node(pd.DataFrame(), 30)["drop_code"] == NO_QUOTES)
    )

    liquid = _synthetic_chain(date, spot, rate, vol, [21, 49], strikes)
    liquid["best_bid"] = np.maximum(liquid["best_bid"], 0.01)
    liquid["best_offer"] = liquid["best_bid"] + 0.01
    full_ladder = at_node(liquid, 30)["near_put_count"]
    two_zero_bids = liquid.copy()
    two_zero_bids.loc[
        (two_zero_bids.cp_flag == "P") & two_zero_bids.strike_price.isin([97.0, 96.0]),
        "best_bid",
    ] = 0.0
    record = at_node(two_zero_bids, 30)
    checks.append(
        (
            "two consecutive zero bids stop the ladder",
            record["near_put_count"] == 2 and record["drop_code"] == FEW_STRIKES_NEAR,
        )
    )
    one_zero_bid = liquid.copy()
    one_zero_bid.loc[
        (one_zero_bid.cp_flag == "P") & (one_zero_bid.strike_price == 97.0), "best_bid"
    ] = 0.0
    checks.append(
        (
            "one zero bid removes only that strike",
            at_node(one_zero_bid, 30)["near_put_count"] == full_ladder - 1,
        )
    )
    return checks
