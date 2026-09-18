"""Reproduce the session 1 diagnostics of item 3. The run computes no gain of any kind
and no realized variance over a cycle.

python -m options_series.item3.run              pull from WRDS, then build
python -m options_series.item3.run --skip-pull  build from data already on disk

Item 3 reads item 1's cache and model-free series, so python -m options_series.item1.run
runs first.
"""

from __future__ import annotations

import argparse
import logging
import time

import pandas as pd

from options_series.db import connect
from options_series.item3.config import FIGURES_DIR, ITEM1_MODEL_FREE_PATH, OUTPUT_DIR
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

LOGGER = logging.getLogger(__name__)


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

    for name, table in {
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
        "d11_data_reuse": data_reuse(quotes, entries),
        "d11_columns": column_reuse(quotes),
    }.items():
        table.to_csv(OUTPUT_DIR / f"{name}.csv", index=False)
    LOGGER.info(
        "session 1 diagnostics written in %.1f min", (time.time() - started) / 60.0
    )


if __name__ == "__main__":
    main()
