"""Reproduce item 3: the pre-return diagnostics, the cycle returns and Figure 1, the
test family with breakeven k and Figure 2, the replication analysis, and the stress and
exploratory tables.

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

import numpy as np
import pandas as pd

from options_series.db import connect
from options_series.item3.accounting import (
    CELLS,
    HEDGE_COSTS,
    MARKINGS,
    adjusted_closes,
    build_returns,
    cell_label,
    realized_variances,
)
from options_series.item3.analysis import (
    add_eta,
    by_strike_count,
    convexity,
    cost_drift,
    daily_sharpe,
    drawdown,
    eta_comparison,
    eta_table,
    named_windows,
    replication_populations,
    split_cycles,
    worst_windows,
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
from options_series.item3.figures import plot_cost_grid, plot_equity
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
    pooled_returns,
    rule_one,
)
from options_series.item3.tests import (
    ESTIMATION_LAG,
    HOLDOUT_LAG,
    UNITS,
    block_tests,
    breakeven_row,
    diagnostic_regressions,
    mean_test,
    slope_test,
    unit_series,
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
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Cycle returns, their samples, the daily equity and hedge paths, and Figure 1,
    written as they are built."""
    variances = realized_variances(entries, adjusted_closes(prices), calendar)
    returns, equity, hedges = build_returns(entries, legs, panel, prices, curve)
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
    return cycle_returns, sample, equity, hedges


def column(k: float, c: float) -> str:
    """Return column of a cost cell."""
    return f"return_{cell_label(k, c)}"


def arm_series(rows: pd.DataFrame, arm: str, name: str) -> dict[str, np.ndarray]:
    """Each fund's and the pooled series of one arm and return column."""
    arm_rows = rows[rows.arm == arm]
    pooled = pooled_returns(arm_rows[["ticker", "entry", name]], name)
    return unit_series(arm_rows, name, pooled)


def verdict(first: bool, second: bool) -> str:
    """Decision rule on two inference outcomes."""
    if first and second:
        return "supported"
    if first != second:
        return "not robust to inference method"
    return "not supported"


def tests_stage(cycle_returns: pd.DataFrame) -> None:
    """The 22 tests, the O1 diagnostics, the robustness column, breakeven k and
    Figure 2."""
    estimation = cycle_returns[cycle_returns.window == "estimation"]
    primary = estimation[estimation.primary]
    blocks = []
    for block, (k, c) in (("A", (0.0, 0.0)), ("B", (PRIMARY_K, PRIMARY_C))):
        name = column(k, c)
        by_arm = {arm: arm_series(primary, arm, name) for arm in ("strip", "straddle")}
        blocks.append(block_tests(block, by_arm, ESTIMATION_LAG))
    holdout = cycle_returns[
        (cycle_returns.window == "holdout")
        & cycle_returns.primary
        & (cycle_returns.arm == "strip")
    ].copy()
    name = column(PRIMARY_K, PRIMARY_C)
    pooled_holdout = pooled_returns(holdout[["ticker", "entry", name]], name)
    block_c = mean_test(pooled_holdout[name].to_numpy(float), HOLDOUT_LAG)
    clears_nw = bool(block_c["p_newey_west"] <= 0.05)
    clears_boot = bool(block_c["p_bootstrap"] <= 0.05)
    block_c.update(
        block="C",
        arm="strip",
        unit="POOLED",
        holm_level_newey_west=0.05,
        holm_level_bootstrap=0.05,
        clears_newey_west=clears_nw,
        clears_bootstrap=clears_boot,
        verdict=verdict(clears_nw, clears_boot),
    )
    blocks.append(pd.DataFrame([block_c]))
    pd.concat(blocks, ignore_index=True).to_csv(
        OUTPUT_DIR / "tests_family.csv", index=False
    )

    holdout["log_k"] = np.log(holdout.k_strip)
    holdout["log_rv21"] = np.log(holdout.rv21)
    holdout["log_rv"] = np.log(holdout.rv)
    holdout["o1"] = holdout.log_k - holdout.log_rv21
    slope = slope_test(holdout, name, "o1")
    slope["verdict"] = verdict(slope["clustered_clears"], slope["bootstrap_clears"])
    pd.DataFrame([{"block": "C", "test": "O1 slope", **slope}]).to_csv(
        OUTPUT_DIR / "tests_o1_slope.csv", index=False
    )
    diagnostic_regressions(holdout, name).to_csv(
        OUTPUT_DIR / "tests_o1_diagnostics.csv", index=False
    )

    robust = estimation[estimation.robustness & (estimation.arm == "strip")]
    robustness = []
    for block, (k, c) in (("A", (0.0, 0.0)), ("B", (PRIMARY_K, PRIMARY_C))):
        name = column(k, c)
        robustness.append(
            block_tests(
                block,
                {"strip": arm_series(robust, "strip", name)},
                ESTIMATION_LAG,
                test=False,
            ).assign(sample="every computable strip cycle")
        )
    pd.concat(robustness, ignore_index=True).to_csv(
        OUTPUT_DIR / "tests_robustness_all_strip_cycles.csv", index=False
    )

    rows, grid = [], []
    samples = (("estimation", primary), ("full", cycle_returns[cycle_returns.primary]))
    for sample_name, frame in samples:
        for arm in ("strip", "straddle"):
            for c in HEDGE_COSTS:
                zero = arm_series(frame, arm, column(0.0, c))
                one = arm_series(frame, arm, column(1.0, c))
                for unit in UNITS:
                    if unit in zero and len(zero[unit]):
                        rows.append(
                            {
                                "sample": sample_name,
                                "arm": arm,
                                "unit": unit,
                                "c_bps": c * 1e4,
                                **breakeven_row(zero[unit], one[unit], ESTIMATION_LAG),
                            }
                        )
                if sample_name == "estimation":
                    for k in EXECUTION_FRACTIONS:
                        series = arm_series(frame, arm, column(k, c))["POOLED"]
                        grid.append(
                            {"arm": arm, "k": k, "c": c, "mean": float(series.mean())}
                        )
    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "breakeven_k.csv", index=False)
    grid = pd.DataFrame(grid)
    grid.to_csv(OUTPUT_DIR / "fig2_cost_grid.csv", index=False)
    plot_cost_grid(grid, OUTPUT_DIR / "fig2_cost_grid")
    LOGGER.info("tests, breakeven k and Figure 2 written")


def replication_stage(cycle_returns: pd.DataFrame) -> None:
    """Part D: the two rule-2 populations, eta against both targets, both against
    strike count."""
    strip = cycle_returns[
        (cycle_returns.arm == "strip") & cycle_returns.robustness
    ].copy()
    strip["floor_pass"] = strip.floor_pass.astype(bool)
    strip["population"] = np.where(strip.floor_pass, "passes rule 2", "fails rule 2")
    straddle = cycle_returns[
        (cycle_returns.arm == "straddle") & cycle_returns.primary
    ].assign(population="primary")
    strip, straddle = add_eta(strip), add_eta(straddle)
    replication_populations(strip).to_csv(
        OUTPUT_DIR / "replication_populations.csv", index=False
    )
    eta_table(pd.concat([strip, straddle], ignore_index=True)).to_csv(
        OUTPUT_DIR / "replication_eta.csv", index=False
    )
    eta_comparison(strip).to_csv(
        OUTPUT_DIR / "replication_eta_comparison.csv", index=False
    )
    by_strike_count(strip).to_csv(
        OUTPUT_DIR / "replication_by_strike_count.csv", index=False
    )
    LOGGER.info("replication analysis written")


def stress_stage(
    cycle_returns: pd.DataFrame,
    sample: pd.DataFrame,
    equity: pd.DataFrame,
    hedges: pd.DataFrame,
    quotes: pd.DataFrame,
    legs: pd.DataFrame,
    prices: pd.DataFrame,
) -> None:
    """Part E: split cycles, stress windows, cost drift, the convexity series and the
    per-cycle counts."""
    primary_name = column(PRIMARY_K, PRIMARY_C)
    summary, daily = split_cycles(
        cycle_returns, equity, hedges, quotes, legs, prices, primary_name
    )
    summary.to_csv(OUTPUT_DIR / "stress_split_cycles.csv", index=False)
    daily.to_csv(OUTPUT_DIR / "stress_split_cycles_daily.csv", index=False)

    primary = cycle_returns[cycle_returns.primary]
    cells, markings = [], []
    for arm in ("strip", "straddle"):
        members = equity_members(sample, arm)
        for k, c in CELLS:
            pooled = pooled_returns(
                primary[primary.arm == arm][["ticker", "entry", column(k, c)]],
                column(k, c),
            )
            series = pooled_equity(arm_equity(equity, arm, k, c), members)
            cells.append(
                {
                    "arm": arm,
                    "k": k,
                    "c_bps": c * 1e4,
                    **worst_windows(pooled, column(k, c)),
                    **drawdown(series),
                }
            )
        for marking in MARKINGS:
            series = pooled_equity(
                arm_equity(equity, arm, PRIMARY_K, PRIMARY_C, marking), members
            )
            markings.append(
                {
                    "arm": arm,
                    "marking": marking,
                    **drawdown(series),
                    **daily_sharpe(series),
                }
            )
    pd.DataFrame(cells).to_csv(OUTPUT_DIR / "stress_cost_cells.csv", index=False)
    pd.DataFrame(markings).to_csv(OUTPUT_DIR / "stress_markings.csv", index=False)
    named_windows(cycle_returns, primary_name).to_csv(
        OUTPUT_DIR / "stress_named_windows.csv", index=False
    )
    by_year, by_fund = cost_drift(
        primary,
        {
            0.0: (column(0.0, 0.0), column(1.0, 0.0)),
            PRIMARY_C: (column(0.0, PRIMARY_C), column(1.0, PRIMARY_C)),
        },
    )
    by_year.to_csv(OUTPUT_DIR / "cost_drift_by_year.csv", index=False)
    by_fund.to_csv(OUTPUT_DIR / "cost_drift_half_spread_by_fund.csv", index=False)
    series, table = convexity(primary, column(0.0, 0.0))
    series.to_csv(OUTPUT_DIR / "convexity_series.csv", index=False)
    table.to_csv(OUTPUT_DIR / "convexity_by_u_and_g.csv", index=False)
    counts = cycle_returns[
        [
            "ticker",
            "cycle",
            "arm",
            "entry",
            "window",
            "excluded_by",
            "hedge_days",
            "carried_hedge_days",
            "carried_leg_days",
            "zero_bid_marks",
            "carried_marks",
        ]
    ]
    counts.to_csv(OUTPUT_DIR / "cycle_hedge_and_mark_counts.csv", index=False)
    LOGGER.info("stress and exploratory tables written")


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
    cycle_returns, sample, equity, hedges = returns_stage(
        entries, legs, panel, prices, calendar, curve
    )
    tests_stage(cycle_returns)
    replication_stage(cycle_returns)
    stress_stage(cycle_returns, sample, equity, hedges, quotes, legs, prices)
    LOGGER.info("item 3 run done in %.1f min", (time.time() - started) / 60.0)


if __name__ == "__main__":
    main()
