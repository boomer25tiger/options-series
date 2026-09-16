"""Reproduce every figure and table of item 1.

python -m options_series.item1.run              pull from WRDS, then build
python -m options_series.item1.run --skip-pull  build from data already on disk
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Iterable

import numpy as np
import pandas as pd

from options_series.db import connect
from options_series.item1.config import (
    BENCHMARK,
    COMMODITY_ETFS,
    CURVE_COVERAGE_FLOOR,
    DATA_DIR,
    NODES,
    OUTPUT_DIR,
    STATE_POWER_FLOOR,
    STATE_REPORT_FLOOR,
)
from options_series.item1.curve_state import (
    build_curve,
    choose_continuation,
    curve_slope_and_sign,
    load_continuation_candidates,
    pull_all_futures,
    test_continuation_candidates,
)
from options_series.item1.figures import (
    annual_log_ratio_table,
    plot_annual_log_ratio,
    plot_commonality,
    plot_curve_state_split,
    plot_headline_annual_log_ratio,
    plot_slope_coefficients,
    plot_vix_check,
)
from options_series.item1.model_free_variance import (
    atm_implied_variance,
    build_model_free_variance,
    check_estimator_on_black_scholes,
    validate_against_vix,
)
from options_series.item1.pull_options import (
    benchmark_trade_dates,
    load_atm_surface,
    load_security_returns,
    load_vix,
    load_zero_curve,
    pull_all_options,
)
from options_series.item1.realized_variance import (
    non_overlapping_grid,
    realized_variance,
    variance_premium,
)
from options_series.item1.tests import (
    assemble_panel,
    commonality,
    curve_state_split,
    headline_series,
    level_tests,
    pooled_level,
    selection_check,
    slope_per_standard_deviation,
    slope_tests,
)

LOGGER = logging.getLogger(__name__)
SERIES_LABELS = {
    "model_free": "model-free",
    "atm": "ATM",
    "headline mix": "headline mix",
}


def _decimal(value: float, places: int = 4) -> str:
    """Fixed-point text, empty for a missing value."""
    if value is None or not np.isfinite(value):
        return ""
    return f"{value:.{places}f}"


def _p_value(value: float) -> str:
    """P-value text: below the bootstrap resolution, scientific when tiny, else four
    decimals."""
    if value is None or not np.isfinite(value):
        return ""
    if value == 0:
        return "<0.0005"
    if value < 0.0001:
        return f"{value:.2e}"
    return f"{value:.4f}"


def _count(value: float) -> str:
    """Integer text with thousands separators."""
    return f"{int(value):,}"


def _span(first: pd.Timestamp, last: pd.Timestamp) -> str:
    """Date range text."""
    return f"{first.date()} .. {last.date()}"


def _interval(
    low: float, high: float, formatter: Callable[[float], str] = _decimal
) -> str:
    """Bracketed interval text."""
    return f"[{formatter(low)}, {formatter(high)}]"


def _signed(value: float) -> str:
    """Signed four-decimal text."""
    return f"{value:+.4f}"


def _yes_no(flag: bool) -> str:
    """yes or no."""
    return "yes" if flag else "no"


def _markdown_table(headers: list[str], rows: Iterable[list[str]]) -> list[str]:
    """Markdown table lines."""
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return lines + [""]


def results_tables(
    level: pd.DataFrame,
    pooled: pd.DataFrame,
    slope: pd.DataFrame,
    scaled: pd.DataFrame,
    split: pd.DataFrame,
    shares: dict[tuple[int, str], dict[str, object]],
    coverage: pd.DataFrame,
    continuation_tests: pd.DataFrame,
    curve_summary: pd.DataFrame,
    trade_date_count: int,
    vix_summary: dict[str, float | int | bool],
) -> str:
    """Every results table as markdown."""
    lines = ["# Item 1 results tables", ""]

    lines += ["## Pooled level, outside the test family", ""]
    lines += _markdown_table(
        [
            "node",
            "series",
            "dates with all four",
            "span",
            "pooled mean",
            "NW 95% interval",
            "p NW",
            "p HH",
            "boot 95% interval",
            "p boot",
            "grid n",
            "grid mean",
            "p grid",
        ],
        [
            [
                row.node,
                SERIES_LABELS[row.series],
                _count(row.n),
                _span(row.first_date, row.last_date),
                _decimal(row.estimate),
                _interval(row.nw_ci_low, row.nw_ci_high),
                _p_value(row.p_newey_west),
                _p_value(row.p_hansen_hodrick),
                _interval(row.boot_ci_low, row.boot_ci_high),
                _p_value(row.p_bootstrap),
                int(row.n_grid),
                _decimal(row.grid_estimate),
                _p_value(row.p_grid),
            ]
            for row in pooled.sort_values(
                ["node", "series"], ascending=[True, False]
            ).itertuples()
        ],
    )

    family = level[level.in_family].sort_values(["node", "ticker"])
    lines += ["## H1 family", ""]
    lines += _markdown_table(
        [
            "node",
            "ETF",
            "headline series",
            "n",
            "mean log(IV²/RV)",
            "p NW",
            "p HH",
            "p boot",
            "grid n",
            "p grid",
            "Holm level NW",
            "Holm level boot",
            "NW clears",
            "boot clears",
            "verdict",
        ],
        [
            [
                row.node,
                row.ticker,
                SERIES_LABELS[row.series],
                _count(row.n),
                _decimal(row.estimate),
                _p_value(row.p_newey_west),
                _p_value(row.p_hansen_hodrick),
                _p_value(row.p_bootstrap),
                int(row.n_grid),
                _p_value(row.p_grid),
                _decimal(row.holm_level_newey_west),
                _decimal(row.holm_level_bootstrap),
                _yes_no(row.clears_newey_west),
                _yes_no(row.clears_bootstrap),
                f"**{row.verdict}**",
            ]
            for row in family.itertuples()
        ],
    )

    full_log_ratio = level[
        (level.measure == "log_ratio")
        & (level["sample"] == "full")
        & level.series.isin(["model_free", "atm"])
    ]
    lines += ["## H1 both series", ""]
    lines += _markdown_table(
        [
            "node",
            "ETF",
            "series",
            "n",
            "mean",
            "p NW",
            "p HH",
            "p boot",
            "p grid",
            "headline?",
        ],
        [
            [
                row.node,
                row.ticker,
                SERIES_LABELS[row.series],
                _count(row.n),
                _decimal(row.estimate),
                _p_value(row.p_newey_west),
                _p_value(row.p_hansen_hodrick),
                _p_value(row.p_bootstrap),
                _p_value(row.p_grid),
                "yes" if row.in_family else "",
            ]
            for row in full_log_ratio[full_log_ratio.ticker != BENCHMARK]
            .sort_values(["node", "ticker", "series"])
            .itertuples()
        ],
    )
    lines += ["## SPX benchmark, outside the test family", ""]
    lines += _markdown_table(
        ["node", "series", "n", "mean", "p NW", "p HH", "p boot", "grid n", "p grid"],
        [
            [
                row.node,
                SERIES_LABELS[row.series],
                _count(row.n),
                _decimal(row.estimate),
                _p_value(row.p_newey_west),
                _p_value(row.p_hansen_hodrick),
                _p_value(row.p_bootstrap),
                int(row.n_grid),
                _p_value(row.p_grid),
            ]
            for row in full_log_ratio[full_log_ratio.ticker == BENCHMARK]
            .sort_values(["node", "series"])
            .itertuples()
        ],
    )

    excluding = level[
        (level["sample"] == "excluding April 2020")
        & level.series.isin(["model_free", "atm"])
    ]
    lines += ["## H1 excluding April 2020", ""]
    lines += _markdown_table(
        ["node", "ETF", "series", "n", "mean", "p NW", "p HH", "p boot", "p grid"],
        [
            [
                row.node,
                row.ticker,
                SERIES_LABELS[row.series],
                _count(row.n),
                _decimal(row.estimate),
                _p_value(row.p_newey_west),
                _p_value(row.p_hansen_hodrick),
                _p_value(row.p_bootstrap),
                _p_value(row.p_grid),
            ]
            for row in excluding.sort_values(["node", "ticker", "series"]).itertuples()
        ],
    )
    lines += ["## H1 floor-of-two model-free series", ""]
    lines += _markdown_table(
        ["node", "ETF", "n", "mean", "p NW", "p HH", "p boot", "p grid"],
        [
            [
                row.node,
                row.ticker,
                _count(row.n),
                _decimal(row.estimate),
                _p_value(row.p_newey_west),
                _p_value(row.p_hansen_hodrick),
                _p_value(row.p_bootstrap),
                _p_value(row.p_grid),
            ]
            for row in level[level.series == "model_free_floor2"]
            .sort_values(["node", "ticker"])
            .itertuples()
        ],
    )
    lines += ["## H1 IV² − RV in annualised variance points", ""]
    lines += _markdown_table(
        [
            "node",
            "ETF",
            "series",
            "n",
            "mean IV² − RV",
            "p NW",
            "p HH",
            "p boot",
            "p grid",
        ],
        [
            [
                row.node,
                row.ticker,
                SERIES_LABELS[row.series],
                _count(row.n),
                _decimal(row.estimate, 6),
                _p_value(row.p_newey_west),
                _p_value(row.p_hansen_hodrick),
                _p_value(row.p_bootstrap),
                _p_value(row.p_grid),
            ]
            for row in level[level.measure == "var_difference"]
            .sort_values(["node", "ticker", "series"])
            .itertuples()
        ],
    )

    slope_family = slope[slope.in_family].sort_values(["node", "unit"])
    lines += ["## H2 family", ""]
    lines += _markdown_table(
        [
            "node",
            "unit",
            "series",
            "n",
            "slope",
            "p NW",
            "p HH",
            "p boot",
            "grid n",
            "p grid",
            "Holm level NW",
            "Holm level boot",
            "NW clears",
            "boot clears",
            "verdict",
        ],
        [
            [
                row.node,
                row.unit,
                SERIES_LABELS[row.series],
                _count(row.n),
                _decimal(row.estimate, 3),
                _p_value(row.p_newey_west),
                _p_value(row.p_hansen_hodrick),
                _p_value(row.p_bootstrap),
                int(row.n_grid),
                _p_value(row.p_grid),
                _decimal(row.holm_level_newey_west),
                _decimal(row.holm_level_bootstrap),
                _yes_no(row.clears_newey_west),
                _yes_no(row.clears_bootstrap),
                f"**{row.verdict}**",
            ]
            for row in slope_family.itertuples()
        ],
    )
    lines += ["## H2 slope per standard deviation of z_t", ""]
    lines += _markdown_table(
        [
            "node",
            "unit",
            "sd of z_t",
            "slope per 1 sd",
            "NW 95% interval",
            "boot 95% interval",
            "verdict",
        ],
        [
            [
                row.node,
                row.unit,
                f"{row.slope_sd:.5f}",
                _signed(row.estimate_per_sd),
                _interval(row.nw_low_per_sd, row.nw_high_per_sd, _signed),
                _interval(row.boot_low_per_sd, row.boot_high_per_sd, _signed),
                row.verdict,
            ]
            for row in scaled.sort_values(["node", "unit"]).itertuples()
        ],
    )
    lines += [
        f"Largest absolute slope per standard deviation: {scaled.estimate_per_sd.abs().max():.4f}",
        "",
    ]
    lines += ["## H2 gold and silver slope span", ""]
    lines += _markdown_table(
        ["node", "unit", "z_t first date", "z_t last date"],
        [
            [
                row.node,
                row.unit,
                str(row.slope_first_date.date()),
                str(row.slope_last_date.date()),
            ]
            for row in slope_family[slope_family.unit.isin(["GLD", "SLV"])].itertuples()
        ],
    )
    lines += ["## H2 excluding April 2020", ""]
    lines += _markdown_table(
        ["node", "unit", "n", "slope", "p NW", "p HH", "p boot", "p grid"],
        [
            [
                row.node,
                row.unit,
                _count(row.n),
                _decimal(row.estimate, 3),
                _p_value(row.p_newey_west),
                _p_value(row.p_hansen_hodrick),
                _p_value(row.p_bootstrap),
                _p_value(row.p_grid),
            ]
            for row in slope[~slope.in_family]
            .sort_values(["node", "unit"])
            .itertuples()
        ],
    )

    lines += ["## Curve-state split, no test", ""]
    lines += _markdown_table(
        [
            "node",
            "ETF",
            "state",
            "daily obs",
            "n windows",
            "mean",
            "boot 95% interval",
            "section 5 status",
        ],
        [
            [
                row.node,
                row.ticker,
                row.state,
                _count(row.daily_observations),
                row.windows,
                _decimal(row.mean_log_ratio),
                _interval(row.ci_low, row.ci_high),
                row.status,
            ]
            for row in split.sort_values(["node", "ticker", "state"]).itertuples()
        ],
    )
    lines += [
        (
            f"State cells below the power floor: "
            f"{int((split.windows < STATE_POWER_FLOOR).sum())} of {len(split)}; "
            f"below the reporting floor: "
            f"{int((split.windows < STATE_REPORT_FLOOR).sum())}"
        ),
        "",
    ]

    lines += ["## Q3 commonality", ""]
    lines += _markdown_table(
        [
            "node",
            "series",
            "dates",
            "span",
            "share before",
            "share after",
            "change",
            "unconditioned share, full common window",
            "full-window dates",
            "mean absolute correlation before",
            "mean absolute correlation after",
        ],
        [
            [
                node,
                SERIES_LABELS[series],
                _count(result["dates"]),
                _span(result["first_date"], result["last_date"]),
                _decimal(result["share_before"]),
                _decimal(result["share_after"]),
                _signed(result["share_after"] - result["share_before"]),
                _decimal(result["share_full_window"]),
                _count(result["full_window_dates"]),
                _decimal(result["mean_abs_correlation_before"]),
                _decimal(result["mean_abs_correlation_after"]),
            ]
            for node in NODES
            for series in ("model_free", "atm")
            for result in [shares[(node, series)]]
        ],
    )
    for node in NODES:
        for moment in ("before", "after"):
            correlation = shares[(node, "model_free")][f"correlation_{moment}"]
            lines += [
                f"### Model-free correlations, {node}-day node, {moment} conditioning",
                "",
            ]
            lines += _markdown_table(
                ["", *COMMODITY_ETFS],
                [
                    [
                        ticker,
                        *[
                            _decimal(correlation.loc[ticker, other])
                            for other in COMMODITY_ETFS
                        ],
                    ]
                    for ticker in COMMODITY_ETFS
                ],
            )

    lines += ["## Curve-state coverage", ""]
    lines += _markdown_table(
        [
            "commodity",
            "underlying for",
            "incumbent class",
            "continuation class",
            "spliced at",
            "dates built",
            "dropped for null settlement",
            "span",
            "coverage share",
            "front-contract switches",
        ],
        [
            [
                row.commodity,
                row.underlying_for,
                row.incumbent_class,
                "none"
                if pd.isna(row.continuation_class)
                else int(row.continuation_class),
                row.spliced_at or "not spliced",
                _count(row.dates_built),
                row.dropped_null_settlement,
                _span(row.first_date, row.last_date),
                _decimal(row.coverage_share),
                row.front_switches,
            ]
            for row in coverage.itertuples()
        ],
    )
    lines += ["## Continuation candidates", ""]
    lines += _markdown_table(
        [
            "class",
            "id",
            "contract",
            "metal",
            "overlap dates",
            "F1 match",
            "F2 match",
            "dates after 2022-12-28",
            "accepted",
        ],
        [
            [
                row.class_code,
                row.class_id,
                row.contract,
                row.metal,
                _count(row.overlap_dates),
                _decimal(row.front_match),
                _decimal(row.second_match),
                row.dates_after_splice,
                "**yes**" if row.accepted else "no",
            ]
            for row in continuation_tests.sort_values(
                ["metal", "class_code"]
            ).itertuples()
        ],
    )
    lines += ["## Curve state", ""]
    lines += _markdown_table(
        [
            "commodity",
            "share contango",
            "share backwardation",
            "dates dropped for equality",
            "winsorization bounds on z_t",
            "z_t non-null",
        ],
        [
            [
                row.commodity,
                _decimal(row.share_contango),
                _decimal(row.share_backwardation),
                row.dropped_equal,
                f"[{row.winsor_lower:.6f}, {row.winsor_upper:.6f}]",
                _count(row.slope_nonnull),
            ]
            for row in curve_summary.itertuples()
        ],
    )
    lines += ["## Section 9 coverage check", ""]
    lines += [
        (
            f"Common window trade dates {_count(trade_date_count)}; the 80 percent "
            f"floor is {CURVE_COVERAGE_FLOOR * trade_date_count:.1f} dates."
        ),
        "",
    ]
    lines += _markdown_table(
        [
            "commodity",
            "underlying for",
            "coverage share",
            "clears 80 percent",
            "spliced at",
            "outcome",
        ],
        [
            [
                row.commodity,
                row.underlying_for,
                _decimal(row.coverage_share),
                _yes_no(row.clears_floor),
                row.spliced_at or "not spliced",
                "**RETAINED**" if row.clears_floor else "**DROPPED**",
            ]
            for row in coverage.itertuples()
        ],
    )
    lines += ["## VIX check", ""]
    lines += _markdown_table(
        [
            "dates",
            "correlation",
            "mean gap",
            "median gap",
            "median absolute gap",
            "dates over 2 points",
        ],
        [
            [
                _count(vix_summary["dates"]),
                f"{vix_summary['correlation']:.6f}",
                _signed(vix_summary["mean_gap"]),
                _signed(vix_summary["median_gap"]),
                _decimal(vix_summary["median_abs_gap"]),
                vix_summary["dates_over_two_points"],
            ]
        ],
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    """Pull or load the inputs, build every series, run the tests, write the outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-pull", action="store_true", help="build from data on disk"
    )
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    failed_checks = [
        name for name, passed in check_estimator_on_black_scholes() if not passed
    ]
    if failed_checks:
        raise RuntimeError(f"estimator checks failed: {failed_checks}")

    if not arguments.skip_pull:
        connection = connect()
        pull_all_options(connection)
        pull_all_futures(connection)
        connection.close()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    returns = load_security_returns()
    trade_dates = benchmark_trade_dates(returns)

    model_free = build_model_free_variance(load_zero_curve())
    model_free.to_parquet(DATA_DIR / "model_free_variance.parquet", index=False)
    vix_summary, vix_series = validate_against_vix(model_free, load_vix())
    if not vix_summary["passed"]:
        raise RuntimeError(
            f"model-free construction fails the VIX check: {vix_summary}"
        )
    plot_vix_check(vix_series, vix_summary["correlation"], OUTPUT_DIR / "fig_vix_check")

    atm = atm_implied_variance(load_atm_surface())
    premium = variance_premium(model_free, atm, realized_variance(returns))
    grid = non_overlapping_grid(returns, premium)
    premium.to_parquet(DATA_DIR / "premium_daily.parquet", index=False)
    grid.to_parquet(DATA_DIR / "premium_grid.parquet", index=False)

    continuation_tests = test_continuation_candidates(
        load_continuation_candidates(), trade_dates
    )
    curve, coverage = build_curve(trade_dates, choose_continuation(continuation_tests))
    below_floor = coverage.loc[~coverage.clears_floor, "commodity"].tolist()
    if below_floor:
        raise RuntimeError(f"curve state below the coverage floor for {below_floor}")
    curve_state, curve_summary = curve_slope_and_sign(curve)
    curve_state.to_parquet(DATA_DIR / "curve_state.parquet", index=False)

    daily, grid_panel = assemble_panel(premium, grid, curve_state, model_free)
    selection = selection_check(model_free, premium)
    headline = headline_series(selection)
    level = level_tests(daily, grid_panel, headline)
    pooled = pooled_level(daily, grid_panel)
    slope = slope_tests(daily, grid_panel, headline)
    scaled = slope_per_standard_deviation(daily, slope, headline)
    split = curve_state_split(daily, grid_panel, headline)
    shares = commonality(daily)

    annual = annual_log_ratio_table(premium)
    plot_annual_log_ratio(annual, "model_free", OUTPUT_DIR / "fig1_annual_logratio")
    plot_annual_log_ratio(annual, "atm", OUTPUT_DIR / "fig1_atm_annual_logratio")
    plot_headline_annual_log_ratio(annual, OUTPUT_DIR / "post_fig1")
    plot_curve_state_split(split, OUTPUT_DIR / "fig2_sign_split")
    plot_slope_coefficients(scaled, OUTPUT_DIR / "fig3_slope_coefficients")
    plot_commonality(shares, OUTPUT_DIR / "fig4_commonality")

    for name, table in {
        "annual_log_ratio": annual,
        "selection_check": selection,
        "h1_tests": level,
        "pooled_h1": pooled,
        "h2_tests": slope,
        "h2_slope_per_sd": scaled,
        "curve_state_split": split,
        "continuation_tests": continuation_tests,
        "curve_coverage": coverage,
        "curve_summary": curve_summary,
    }.items():
        table.to_csv(OUTPUT_DIR / f"{name}.csv", index=False)
    (OUTPUT_DIR / "results_tables.md").write_text(
        results_tables(
            level,
            pooled,
            slope,
            scaled,
            split,
            shares,
            coverage,
            continuation_tests,
            curve_summary,
            len(trade_dates),
            vix_summary,
        )
    )
    LOGGER.info("headline series by ETF: %s", headline)


if __name__ == "__main__":
    main()
