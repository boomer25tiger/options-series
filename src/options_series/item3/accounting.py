"""Position, hedge and accounting layer of spec sections 3 to 6 as amended: daily marks,
the delta hedge, financing and borrow, settlement, truncation under A8, realized variance
and the cycle return on the 20-cell cost grid.

Choices the spec and its amendments leave open, fixed before any return was computed.
- Strip quantities are q_i = (2 / (T K)) w_i / 100 contracts, the variance notional
  N = 1/K of section 5, so P_entry is close to exp(-rT). The straddle holds one contract
  per leg.
- A leg's mark follows A6 on each day's quotes. The alternative marks of A10 change only
  the zero-bid branch, to the full offer or to zero.
- A leg's delta is its opprcd delta, else Black-Scholes on the ETF close, the zero rate
  to remaining tenor and the leg's opprcd implied volatility from the previous trading
  day (A3). When a leg has neither, that leg's previous delta carries into the hedge, and
  the day counts as a carried-hedge day. Deep wing legs often quote no delta at all, and
  holding the whole book's hedge fixed for one such leg would leave the position
  unhedged through a stress window; that whole-position reading is reported alongside
  as a sensitivity.
- Interest accrues from one close to the next on the prior close's cash balance at the
  prior close's zero rate for its remaining tenor, simple interest on actual/365. A short
  share position also pays that rate plus the borrow spread on its prior-close value.
- The expiration close settles every leg at intrinsic value and closes the hedge; the
  hedge cost applies to the share residual left after assignment nets against it.
- A cycle is truncated (A8) when a traded leg's contract_size leaves 100 or its ss_flag
  leaves '0'. It ends at the close before that day, its legs bought back at their marks
  with no option cost and its hedge closed at that close.
- Realized variance runs over the returns from the entry close to the expiration close
  on closes adjusted by cfadj (section 4). RV21 runs over the 21 returns ending at the
  entry close.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from options_series.item3.config import CALENDAR_DAYS_PER_YEAR, EXECUTION_FRACTIONS
from options_series.item3.construction import ZeroCurve
from options_series.item3.diagnostics import black_scholes_delta

HEDGE_COSTS: tuple[float, ...] = (0.0, 0.0002, 0.0005, 0.0010)
BORROW_SPREADS: tuple[float, ...] = (0.005, 0.0, 0.02)
MARKINGS: tuple[str, ...] = ("half offer", "full offer", "zero")
CELLS: list[tuple[float, float]] = list(product(EXECUTION_FRACTIONS, HEDGE_COSTS))
PRIMARY_CELL = CELLS.index((0.5, 0.0002))
GROSS_CELL = CELLS.index((0.0, 0.0))
TRADING_DAYS_PER_YEAR = 252.0
RV21_RETURNS = 21


def cell_label(k: float, c: float) -> str:
    """Column label of a cost cell, k and c in basis points."""
    return f"k{k:g}_c{c * 1e4:g}"


@dataclass
class ArmPath:
    """One arm-cycle's accounting: scalar results and the daily equity paths."""

    record: dict[str, object]
    dates: pd.DatetimeIndex
    equity: np.ndarray


def _marks(bid: np.ndarray, offer: np.ndarray, present: np.ndarray, marking: str):
    """A6 mark of every leg-day under a zero-bid convention, carried forward where no
    rule applies, with the zero-bid and carried masks."""
    positive_bid = np.nan_to_num(bid) > 0
    positive_offer = np.nan_to_num(offer) > 0
    two_sided = present & positive_bid & positive_offer
    zero_bid = present & (np.nan_to_num(bid, nan=-1.0) == 0) & positive_offer
    zero_value = {"half offer": 0.5, "full offer": 1.0, "zero": 0.0}[marking]
    marks = np.where(
        two_sided,
        0.5 * (np.nan_to_num(bid) + np.nan_to_num(offer)),
        np.where(zero_bid, zero_value * np.nan_to_num(offer), np.nan),
    )
    carried = ~(two_sided | zero_bid)
    filled = pd.DataFrame(marks.T).ffill().to_numpy().T
    return filled, zero_bid, carried


def simulate_arm(
    legs: pd.DataFrame, panel: pd.DataFrame, prices: pd.Series, rates: np.ndarray
) -> ArmPath:
    """Account one arm over one cycle on every cost cell, borrow spread and marking.

    legs holds optionid, cp_flag, strike_price, contracts, best_bid and best_offer at
    entry; panel holds the legs' daily rows from the day before entry through expiration
    with cycle_day and days_to_expiration; prices is the fund's raw close by date and
    rates the zero rate for the remaining tenor on each cycle date."""
    frame = panel[panel.cycle_day >= -1].assign(
        standard=lambda rows: rows.ss_flag.eq("0").astype(float)
    )
    order = legs.optionid.tolist()
    grid = np.sort(frame.cycle_day.unique())

    def matrix(column: str) -> np.ndarray:
        return (
            frame.pivot(index="optionid", columns="cycle_day", values=column)
            .reindex(index=order, columns=grid)
            .to_numpy(float)
        )

    days = frame.drop_duplicates("cycle_day").sort_values("cycle_day")
    days = days[days.cycle_day >= 0]
    dates = pd.DatetimeIndex(days.date)
    remaining = days.days_to_expiration.to_numpy(int)
    count = len(dates)
    bid_all, offer_all = matrix("best_bid"), matrix("best_offer")
    delta_all, iv_all = matrix("delta"), matrix("impl_volatility")
    size_all = matrix("contract_size")
    flags = matrix("standard")
    present_all = matrix("present") == 1
    has_prior_day = bid_all.shape[1] == count + 1
    shift = 1 if has_prior_day else 0
    bid, offer = bid_all[:, shift:], offer_all[:, shift:]
    delta = delta_all[:, shift:]
    prior_iv = (
        iv_all[:, :-1]
        if has_prior_day
        else np.column_stack([np.full(len(order), np.nan), iv_all[:, :-1]])
    )
    present = present_all[:, shift:]
    standard = (flags[:, shift:] == 1) & (size_all[:, shift:] == 100)

    leaves = np.flatnonzero((present & ~standard).any(axis=0)[1:]) + 1
    truncated = bool(len(leaves))
    last = int(leaves[0] - 1) if truncated else count - 1

    close = prices.reindex(dates).to_numpy(float)
    strikes = legs.strike_price.to_numpy(float)
    contracts = legs.contracts.to_numpy(float)
    is_call = (legs.cp_flag == "C").to_numpy()
    years = remaining / CALENDAR_DAYS_PER_YEAR

    fallback = black_scholes_delta(
        close[None, :],
        strikes[:, None],
        years[None, :],
        rates[None, :],
        prior_iv,
        is_call[:, None],
    )
    usable_prior = np.nan_to_num(prior_iv) > 0
    leg_delta = np.where(
        ~np.isnan(delta), delta, np.where(usable_prior, fallback, np.nan)
    )
    missing = np.isnan(leg_delta)
    carried = missing.any(axis=0)
    per_leg = pd.DataFrame(leg_delta.T).ffill().fillna(0.0).to_numpy().T
    hedge = (contracts[:, None] * 100.0 * per_leg).sum(axis=0)
    position_carry = np.zeros(count)
    for day in range(count):
        if carried[day]:
            position_carry[day] = position_carry[day - 1] if day else 0.0
        else:
            position_carry[day] = float(np.sum(contracts * 100.0 * leg_delta[:, day]))

    entry_mid = 0.5 * (legs.best_bid.to_numpy(float) + legs.best_offer.to_numpy(float))
    half_spread = 0.5 * (
        legs.best_offer.to_numpy(float) - legs.best_bid.to_numpy(float)
    )
    premium = float(np.sum(contracts * 100.0 * entry_mid))
    option_cost = float(np.sum(contracts * 100.0 * half_spread))

    ks = np.array([cell[0] for cell in CELLS])
    cs = np.array([cell[1] for cell in CELLS])
    spreads = np.array(BORROW_SPREADS)[:, None]
    intrinsic = np.where(
        is_call,
        np.maximum(close[last] - strikes, 0.0),
        np.maximum(strikes - close[last], 0.0),
    )
    assigned = np.sum(
        np.where(intrinsic > 0, np.where(is_call, -1.0, 1.0), 0.0) * contracts * 100.0
    )

    mark_sets = {marking: _marks(bid, offer, present, marking) for marking in MARKINGS}
    _, zero_bid_mask, carried_mask = mark_sets["half offer"]
    liability = {
        marking: (contracts[:, None] * 100.0 * marks).sum(axis=0)
        for marking, (marks, _, _) in mark_sets.items()
    }

    def account(path: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        """Cash on every borrow spread and cost cell at the final close, the daily
        equity under each marking at the primary borrow spread, and share turnover."""
        cash = np.broadcast_to(
            premium
            - ks * option_cost
            - path[0] * close[0]
            - cs * abs(path[0]) * close[0],
            (len(BORROW_SPREADS), len(CELLS)),
        ).copy()
        equity = np.full((len(MARKINGS), len(CELLS), count), np.nan)
        turnover = abs(path[0]) * close[0]
        for position, marking in enumerate(MARKINGS):
            equity[position, :, 0] = (
                cash[0] - liability[marking][0] + path[0] * close[0]
            )
        for day in range(1, last + 1):
            elapsed = (dates[day] - dates[day - 1]).days / CALENDAR_DAYS_PER_YEAR
            cash = cash + cash * rates[day - 1] * elapsed
            if path[day - 1] < 0:
                cash = (
                    cash
                    - (rates[day - 1] + spreads)
                    * abs(path[day - 1])
                    * close[day - 1]
                    * elapsed
                )
            if day < last:
                trade = path[day] - path[day - 1]
                turnover += abs(trade) * close[day]
                cash = cash - trade * close[day] - cs * abs(trade) * close[day]
                for position, marking in enumerate(MARKINGS):
                    equity[position, :, day] = (
                        cash[0] - liability[marking][day] + path[day] * close[day]
                    )
        if last == 0:
            cash = cash - cs * abs(path[0]) * close[0]
            cash = cash - liability["half offer"][0] + path[0] * close[0]
            turnover += abs(path[0]) * close[0]
        elif truncated:
            cash = cash - liability["half offer"][last] + path[last - 1] * close[last]
            cash = cash - cs * abs(path[last - 1]) * close[last]
            turnover += abs(path[last - 1]) * close[last]
        else:
            residual = path[last - 1] + assigned
            cash = cash - float(np.sum(contracts * 100.0 * intrinsic))
            cash = (
                cash + path[last - 1] * close[last] - cs * abs(residual) * close[last]
            )
            turnover += abs(residual) * close[last]
        equity[:, :, last] = cash[0]
        equity[:, :, last + 1 :] = cash[0][None, :, None]
        return cash, equity, turnover

    cash, equity, turnover = account(hedge)
    alternative_cash, _, _ = account(position_carry)

    record: dict[str, object] = {
        "premium": premium,
        "option_cost_full": option_cost,
        "option_cost_share": option_cost / premium,
        "hedge_turnover": turnover / premium,
        "truncated": truncated,
        "truncation_date": dates[last] if truncated else pd.NaT,
        "trading_days_held": last + 1,
        "hedge_days": last,
        "carried_hedge_days": int(carried[:last].sum()) if last else int(carried[0]),
        "carried_leg_days": int(missing[:, :last].sum())
        if last
        else int(missing[:, 0].sum()),
        "zero_bid_marks": int(zero_bid_mask[:, :last].sum()),
        "carried_marks": int(carried_mask[:, :last].sum()),
        "entry_hedge_shares": hedge[0],
    }
    for position, (k, c) in enumerate(CELLS):
        record[f"return_{cell_label(k, c)}"] = cash[0, position] / premium
    for spread_index, spread in enumerate(BORROW_SPREADS[1:], start=1):
        label = f"borrow{spread * 1e4:g}"
        record[f"return_{cell_label(*CELLS[GROSS_CELL])}_{label}"] = (
            cash[spread_index, GROSS_CELL] / premium
        )
        record[f"return_{cell_label(*CELLS[PRIMARY_CELL])}_{label}"] = (
            cash[spread_index, PRIMARY_CELL] / premium
        )
    for cell in (GROSS_CELL, PRIMARY_CELL):
        record[f"return_{cell_label(*CELLS[cell])}_position_carry"] = (
            alternative_cash[0, cell] / premium
        )
    record["gain_gross"] = cash[0, GROSS_CELL]
    record["gain_primary"] = cash[0, PRIMARY_CELL]
    return ArmPath(record, dates, equity / premium)


def adjusted_closes(prices: pd.DataFrame) -> pd.DataFrame:
    """Closes adjusted for corporate actions through cfadj, per fund and date."""
    return prices.assign(adjusted=prices.close * prices.cfadj).pivot(
        index="date", columns="ticker", values="adjusted"
    )


def realized_variances(
    cycles: pd.DataFrame, adjusted: pd.DataFrame, calendar: pd.DatetimeIndex
) -> pd.DataFrame:
    """Section 4 realized variance over each cycle and RV21 ending at its entry, with the
    return count, the missing-return count and the summed squared log returns."""
    rows = []
    for cycle in cycles.itertuples():
        series = adjusted[cycle.ticker]
        held = calendar[(calendar >= cycle.entry) & (calendar <= cycle.expiration)]
        closes = series.reindex(held).to_numpy(float)
        simple = closes[1:] / closes[:-1] - 1.0
        valid = np.isfinite(simple) & (simple > -1.0)
        logs = np.log1p(np.where(valid, simple, np.nan))
        position = calendar.searchsorted(cycle.entry)
        trailing = calendar[max(position - RV21_RETURNS, 0) : position + 1]
        before = series.reindex(trailing).to_numpy(float)
        trailing_logs = np.log(before[1:] / before[:-1])
        n = len(logs)
        rows.append(
            {
                "ticker": cycle.ticker,
                "cycle": cycle.cycle,
                "n_returns": n,
                "missing_returns": int((~valid).sum()),
                "sum_squared_log_returns": float(np.nansum(logs**2)),
                "sum_simple_minus_log": float(np.nansum(simple[valid] - logs[valid])),
                "rv": float(TRADING_DAYS_PER_YEAR / n * np.nansum(logs**2))
                if n and valid.all()
                else np.nan,
                "rv21": float(
                    TRADING_DAYS_PER_YEAR / RV21_RETURNS * np.sum(trailing_logs**2)
                )
                if len(trailing_logs) == RV21_RETURNS
                and np.isfinite(trailing_logs).all()
                else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_returns(
    entries: pd.DataFrame,
    legs: pd.DataFrame,
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    curve: ZeroCurve,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every computable arm-cycle's accounting: one row per arm-cycle and the daily
    equity paths in long form."""
    closes = prices.pivot(index="date", columns="ticker", values="close")
    rate_cache: dict[tuple[pd.Timestamp, int], float] = {}

    def rate(date: pd.Timestamp, days: int) -> float:
        if (date, days) not in rate_cache:
            rate_cache[(date, days)] = curve.rate(date, max(days, 1))
        return rate_cache[(date, days)]

    entry_index = entries.set_index(["ticker", "cycle"])
    panel_groups = dict(iter(panel.groupby(["ticker", "cycle", "arm"])))
    records, paths = [], []
    for (ticker, cycle, arm), arm_legs in legs.groupby(["ticker", "cycle", "arm"]):
        entry = entry_index.loc[(ticker, cycle)]
        arm_legs = arm_legs.copy()
        if arm == "strip":
            scale = 2.0 / (entry.years_to_expiration * entry.k_strip) / 100.0
            arm_legs["contracts"] = arm_legs.weight.astype(float) * scale
        else:
            arm_legs["contracts"] = 1.0
        rows = panel_groups[(ticker, cycle, arm)]
        day_rows = rows.drop_duplicates("cycle_day")
        day_rows = day_rows[day_rows.cycle_day >= 0].sort_values("cycle_day")
        rates = np.array(
            [
                rate(date, days)
                for date, days in zip(day_rows.date, day_rows.days_to_expiration)
            ]
        )
        path = simulate_arm(arm_legs, rows, closes[ticker], rates)
        close_entry = float(closes[ticker].loc[entry.entry])
        record = {"ticker": ticker, "cycle": cycle, "arm": arm, **path.record}
        if arm == "strip":
            record["var_points_gross"] = record["gain_gross"] * entry.k_strip
            record["var_points_primary"] = record["gain_primary"] * entry.k_strip
        else:
            record["spot_normalized_gross"] = record["gain_gross"] / 100.0 / close_entry
            record["spot_normalized_primary"] = (
                record["gain_primary"] / 100.0 / close_entry
            )
        records.append(record)
        paths.append((ticker, cycle, arm, path))
    return pd.DataFrame(records), equity_frame(paths)


def equity_frame(paths: list[tuple[str, int, str, ArmPath]]) -> pd.DataFrame:
    """Daily equity per unit of entry premium in long form, one row per arm-cycle,
    marking, cost cell and cycle day."""
    columns: dict[str, list[np.ndarray]] = {
        name: []
        for name in ("ticker", "cycle", "arm", "marking", "k", "c", "date", "equity")
    }
    columns["cycle_day"] = []
    for ticker, cycle, arm, path in paths:
        markings, cells, count = path.equity.shape
        size = markings * cells * count
        columns["ticker"].append(np.repeat(ticker, size))
        columns["cycle"].append(np.repeat(cycle, size))
        columns["arm"].append(np.repeat(arm, size))
        columns["marking"].append(np.repeat(np.array(MARKINGS), cells * count))
        columns["k"].append(
            np.tile(np.repeat([cell[0] for cell in CELLS], count), markings)
        )
        columns["c"].append(
            np.tile(np.repeat([cell[1] for cell in CELLS], count), markings)
        )
        columns["date"].append(np.tile(path.dates.to_numpy(), markings * cells))
        columns["cycle_day"].append(np.tile(np.arange(count), markings * cells))
        columns["equity"].append(path.equity.reshape(-1))
    return pd.DataFrame(
        {name: np.concatenate(parts) for name, parts in columns.items()}
    )
