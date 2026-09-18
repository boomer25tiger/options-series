"""Reproduce the session 1 diagnostics of item 3. The run computes no gain of any kind
and no realized variance over a cycle.

python -m options_series.item3.run              pull from WRDS, then build
python -m options_series.item3.run --skip-pull  build from data already on disk

Item 3 reads item 1's model-free series, so python -m options_series.item1.run runs
first. D11 reads item 1's quote cache and keeps its last measurement once that cache is
gone.
"""

from __future__ import annotations

import argparse
import logging
import time

import pandas as pd

from options_series.db import connect
from options_series.item3.accounting import (
    MARKINGS,
    adjusted_closes,
    build_returns,
    realized_variances,
)
from options_series.item3.config import (
    DATA_DIR,
    EXECUTION_FRACTIONS,
    FIGURES_DIR,
    ITEM1_MODEL_FREE_PATH,
    ITEM1_OPTION_QUOTES_DIR,
    OUTPUT_DIR,
)
from options_series.item3.construction import (
    ZeroCurve,
    build_entries,
    resolve_exdates,
)
from options_series.item3.cycles import cycle_calendar, trading_calendar
from options_series.item3.diagnostics import (
    adjustment_changes,
    chain_continuity,
    column_reuse,
    cycle_counts,
    cycle_inventory,
    data_reuse,
    delta_diagnostics,
    entry_spread_share,
    hedge_paths,
    implied_correlations,
    leg_day_panel,
    missing_returns,
    shortfall_and_rounding,
    ss_flag_runs,
    stop_rule_one,
    strip_coverage,
    zero_bid_marks,
)
from options_series.item3.figures import plot_equity
from options_series.item3.pull import (
    load_atm_surface,
    load_cycle_quotes,
    load_option_starts,
    load_prices,
    load_ss_flag_counts,
    load_zero_curve,
    pull_all_cycle_quotes,
    pull_calendar_inputs,
)
from options_series.item3.samples import (
    exclusion_table,
    exclusions,
    pooled_equity,
    rule_one,
)

LOGGER = logging.getLogger(__name__)
PRIMARY_K, PRIMARY_C = 0.5, 0.0002


def equity_members(sample: pd.DataFrame, arm: str) -> pd.DataFrame:
    """Fund-cycles drawn in the pooled equity path of an arm: those entering their block
    and truncated cycles that pass every earlier rule."""
    rows = sample[
        (sample.arm == arm)
        & (sample.primary | (sample.excluded_by == "rule 5 truncated"))
    ]
    return rows[["ticker", "cycle", "entry"]]


def arm_equity(
    equity: pd.DataFrame, arm: str, k: float, c: float, marking: str = MARKINGS[0]
) -> pd.DataFrame:
    """Daily paths of one arm at one cost cell and marking."""
    return equity[
        (equity.arm == arm)
        & (equity.marking == marking)
        & (equity.k == k)
        & (equity.c == c)
    ]


def returns_stage(
    entries: pd.DataFrame,
    legs: pd.DataFrame,
    panel: pd.DataFrame,
    prices: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    curve: ZeroCurve,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Cycle returns, their samples and Figure 1, written as they are built."""
    variances = realized_variances(entries, adjusted_closes(prices), calendar)
    returns, equity = build_returns(entries, legs, panel, prices, curve)
    equity.to_parquet(DATA_DIR / "equity_paths.parquet", index=False)
    sample = exclusions(entries, returns)
    keep = [
        "ticker",
        "cycle",
        "entry",
        "expiration",
        "window",
        "entry_year",
        "years_to_expiration",
        "k_strip",
        "k_flat_tail",
        "shortfall_ratio",
        "sigma_atm",
        "strip_puts",
        "strip_calls",
        "floor_pass",
    ]
    cycle_returns = (
        returns.merge(entries[keep], on=["ticker", "cycle"])
        .merge(variances, on=["ticker", "cycle"])
        .merge(
            sample[["ticker", "cycle", "arm", "excluded_by", "primary", "robustness"]],
            on=["ticker", "cycle", "arm"],
        )
    )
    cycle_returns.to_csv(OUTPUT_DIR / "cycle_returns.csv", index=False)
    sample.to_csv(OUTPUT_DIR / "sample_membership.csv", index=False)
    exclusion_table(sample).to_csv(OUTPUT_DIR / "sample_exclusions.csv", index=False)
    rule_one(sample).to_csv(OUTPUT_DIR / "sample_rule_1.csv", index=False)

    primary, fans, pooled = {}, {}, []
    for arm in ("strip", "straddle"):
        members = equity_members(sample, arm)
        primary[arm] = pooled_equity(
            arm_equity(equity, arm, PRIMARY_K, PRIMARY_C), members
        )
        fans[arm] = {
            k: pooled_equity(arm_equity(equity, arm, k, PRIMARY_C), members)
            for k in EXECUTION_FRACTIONS
        }
        for k, series in fans[arm].items():
            pooled.append(series.assign(arm=arm, k=k, c=PRIMARY_C))
    pd.concat(pooled, ignore_index=True).to_csv(
        OUTPUT_DIR / "fig1_pooled_equity.csv", index=False
    )
    plot_equity(primary, fans, OUTPUT_DIR / "fig1_equity")
    LOGGER.info("returns built for %d arm-cycles; Figure 1 written", len(returns))
    return cycle_returns, sample, equity


def main(argv: list[str] | None = None) -> None:
    """Pull or load the inputs, build every cycle's entry, run the diagnostics and write
    every table under the output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-pull", action="store_true", help="build from data on disk"
    )
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    for directory in (OUTPUT_DIR, FIGURES_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    if not arguments.skip_pull:
        connection = connect()
        pull_calendar_inputs(connection)
        calendar = trading_calendar(load_prices())
        pull_all_cycle_quotes(
            connection, cycle_calendar(calendar, load_option_starts())
        )
        connection.close()

    started = time.time()
    prices = load_prices()
    calendar = trading_calendar(prices)
    quotes = load_cycle_quotes()
    cycles = resolve_exdates(cycle_calendar(calendar, load_option_starts()), quotes)
    counts = cycle_counts(cycles)
    if not counts.agrees.all():
        LOGGER.warning(
            "cycle calendar disagrees with spec section 10: %s",
            counts[~counts.agrees].to_dict("records"),
        )

    curve = ZeroCurve(load_zero_curve())
    entries, legs = build_entries(cycles, quotes, curve)
    entries["missing_returns"] = missing_returns(entries, prices, calendar).values
    LOGGER.info("entries built in %.1f min", (time.time() - started) / 60.0)

    changes = adjustment_changes(prices)
    panel = leg_day_panel(legs, entries, quotes, calendar)
    paths = hedge_paths(panel, prices, curve)
    null_rates, null_runs, fallback, cycle_hedge = delta_diagnostics(paths, entries)
    zero_bid, cycle_zero_bid = zero_bid_marks(panel)
    chain_daily, leg_trace = chain_continuity(quotes, entries, panel, changes)
    shortfall, rounding = shortfall_and_rounding(entries)
    LOGGER.info("diagnostics built in %.1f min", (time.time() - started) / 60.0)

    hedge_wide = cycle_hedge.pivot(
        index=["ticker", "cycle"],
        columns="arm",
        values=["fallback_leg_days", "carried_hedge_days", "carried_hedge_share"],
    )
    hedge_wide.columns = [f"{arm}_{name}" for name, arm in hedge_wide.columns]
    cycle_table = (
        entries.drop(columns=["exdate_candidates"])
        .merge(hedge_wide.reset_index(), on=["ticker", "cycle"], how="left")
        .merge(cycle_zero_bid, on=["ticker", "cycle"], how="left")
    )

    tables = {
        "cycle_entries": cycle_table,
        "d1_adjustment_changes": changes,
        "d1_ss_flag_runs": ss_flag_runs(load_ss_flag_counts(), changes),
        "d2_cycle_inventory": cycle_inventory(entries),
        "d2_stop_rule_1": stop_rule_one(entries),
        "d3_entry_spread_share": entry_spread_share(entries),
        "d4_delta_null_rates": null_rates,
        "d4_null_run_lengths": null_runs,
        "d4_fallback_paths": fallback,
        "d4_cycle_hedge": cycle_hedge,
        "d5_strip_coverage": strip_coverage(entries),
        "d6_zero_bid_marks": zero_bid,
        "d7_chain_daily": chain_daily,
        "d7_leg_trace": leg_trace,
        "d8_cycle_counts": counts,
        "d9_correlations": implied_correlations(
            entries, pd.read_parquet(ITEM1_MODEL_FREE_PATH), load_atm_surface()
        ),
        "d10_replication_shortfall": shortfall,
        "d10_rounding_size": rounding,
        "d11_columns": column_reuse(quotes),
    }
    if any(ITEM1_OPTION_QUOTES_DIR.glob("*.parquet")):
        tables["d11_data_reuse"] = data_reuse(quotes, entries)
    else:
        LOGGER.info(
            "item 1's quote cache is absent; d11_data_reuse.csv stays as it was"
        )
    for name, table in tables.items():
        table.to_csv(OUTPUT_DIR / f"{name}.csv", index=False)
    LOGGER.info(
        "session 1 diagnostics written in %.1f min", (time.time() - started) / 60.0
    )
    returns_stage(entries, legs, panel, prices, calendar, curve)
    LOGGER.info("returns stage done in %.1f min", (time.time() - started) / 60.0)


if __name__ == "__main__":
    main()
