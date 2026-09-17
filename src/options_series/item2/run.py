"""Reproduce every figure and table of item 2.

python -m options_series.item2.run              pull from WRDS, then build
python -m options_series.item2.run --skip-pull  build from data already on disk
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import wrds

from options_series.db import connect
from options_series.item2.config import (
    AVERAGE_FLOOR,
    CONSTRUCTION_RESTRICT_LIMIT_MINUTES,
    CONSTRUCTION_SERIAL_LIMIT_MINUTES,
    CONSTRUCTION_WORKERS,
    CORRELATION_FLOOR,
    DATA_DIR,
    FIGURES_DIR,
    H2_AFTER,
    H2_BEFORE,
    LINK_COVERAGE_FLOOR,
    NODES,
    OUTPUT_DIR,
    RESTRICTED_START,
    SAMPLE_END,
    SAMPLE_START,
    SPX_SECID,
    SYNTHETIC_TOLERANCE,
    VALIDATION_GAP_THRESHOLD,
    VALIDATION_MIN_CORRELATION,
)
from options_series.item2.correlation import (
    DAILY_PANEL_PATH,
    GRID_PANEL_PATH,
    NAME_PREMIUM_PATH,
    annual_cross_section,
    annual_means,
    correlations,
    daily_averages,
    decomposition,
    decomposition_by_period,
    floor_counts,
    load_returns,
    member_secids,
    non_overlapping_grid,
    premiums,
    pull_returns,
    realized_variances,
    surface_to_atm_ratio,
)
from options_series.item2.figures import (
    plot_correlations,
    plot_decile_band,
    plot_gap_and_zero_dte,
    plot_post_figure,
    plot_validation,
)
from options_series.item2.membership import (
    CONSTITUENTS_PATH,
    LINK_PATH,
    MARKET_CAP_PATH,
    MEMBERSHIP_PATH,
    SURFACE_PRESENCE_PATH,
    TRADE_DATES_PATH,
    build_constituents,
    coverage,
    link_candidates,
    link_coverage_check,
    link_table_columns,
    member_days,
    membership_span,
    previous_day_market_cap,
    pull_link,
    pull_membership,
    pull_stock_daily,
    pull_surface_presence,
    pull_trade_dates,
    resolve_links,
    shared_secids,
)
from options_series.item2.surface_variance import (
    NO_SURFACE_ROWS,
    ZERO_CURVE_PATH,
    atm_variance,
    check_flat_surface,
    check_skewed_surface,
    drop_counts,
    load_ladder_series,
    load_surface_year,
    pull_surfaces,
    pull_zero_curve,
    surface_variance_for_year,
    validate_against_ladder,
)
from options_series.item2.tests import (
    break_date,
    h1_tests,
    h2_tests,
    h3_tests,
    period_cells,
    pull_zero_dte_share,
)

LOGGER = logging.getLogger(__name__)

PULL_STATE_PATH = DATA_DIR / "pull_state.json"
ZERO_DTE_PATH = DATA_DIR / "raw" / "zero_dte_share.parquet"
VARIANCE_DIR = DATA_DIR / "surface_variance"
MEASURE_LABELS = {"surface": "surface", "atm": "ATM"}
FIGURE_NAMES = ("post_fig1", "fig2_correlation", "fig3_deciles", "fig4_gap_zero_dte")


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
    return f"{pd.Timestamp(first).date()} .. {pd.Timestamp(last).date()}"


def _interval(
    low: float, high: float, formatter: Callable[[float], str] = _decimal
) -> str:
    """Bracketed interval text."""
    return f"[{formatter(low)}, {formatter(high)}]"


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


def membership_stage(
    connection: wrds.Connection | None,
) -> tuple[pd.DataFrame, pd.DatetimeIndex, dict[str, object]]:
    """Step 1: membership, the link, the daily constituents, their coverage and stop rules
    9.4 and 9.1."""
    if connection is not None:
        pull_membership(connection).to_parquet(MEMBERSHIP_PATH, index=False)
        link_table_columns(connection).to_csv(
            OUTPUT_DIR / "link_table_columns.csv", index=False
        )
        pull_link(connection).to_parquet(LINK_PATH, index=False)
        pull_trade_dates(connection).to_parquet(TRADE_DATES_PATH, index=False)
    membership = pd.read_parquet(MEMBERSHIP_PATH)
    link = pd.read_parquet(LINK_PATH)
    span = membership_span(membership)
    sample_start = SAMPLE_START
    if not span["covers_sample_start"]:
        sample_start = str(span["first_start"].date())
        LOGGER.info("stop rule 9.4: sample starts at %s", sample_start)
    trade_dates = pd.DatetimeIndex(pd.read_parquet(TRADE_DATES_PATH).date)
    trade_dates = trade_dates[
        (trade_dates >= sample_start) & (trade_dates <= SAMPLE_END)
    ]

    members = member_days(membership, trade_dates)
    candidates = link_candidates(members, link)
    if connection is not None:
        pull_surface_presence(connection, candidates).to_parquet(
            SURFACE_PRESENCE_PATH, index=False
        )
    presence = pd.read_parquet(SURFACE_PRESENCE_PATH)
    resolved, link_summary = resolve_links(candidates, presence)
    constituents = build_constituents(members, resolved, presence)
    constituents.to_parquet(CONSTITUENTS_PATH, index=False)
    shared = shared_secids(constituents)
    daily_coverage, coverage_by_year = coverage(constituents)
    daily_coverage.to_csv(OUTPUT_DIR / "coverage_daily.csv", index=False)
    coverage_by_year.to_csv(OUTPUT_DIR / "coverage_by_year.csv", index=False)
    check = link_coverage_check(daily_coverage)
    report = {
        "membership": {key: str(value) for key, value in span.items()},
        "sample_start": sample_start,
        "trade_dates": len(trade_dates),
        "member_days": len(members),
        "link_rows": len(link),
        "link_resolution": link_summary,
        "shared_secid_member_days": len(shared),
        "shared_secid_dates": int(shared.date.nunique()),
        "shared_secids": int(shared.secid.nunique()),
        "stop_rule_9_1": {key: str(value) for key, value in check.items()},
    }
    (OUTPUT_DIR / "step1_membership.json").write_text(json.dumps(report, indent=2))
    if not check["passed"]:
        raise RuntimeError(
            "stop rule 9.1: median share of constituents with a 30-day surface "
            f"{check['median_share_with_surface']:.4f} is below {LINK_COVERAGE_FLOOR}"
        )
    return constituents, trade_dates, report


def secids_by_year(constituents: pd.DataFrame) -> dict[int, np.ndarray]:
    """Constituent secids per calendar year."""
    mapped = constituents.dropna(subset=["secid"])
    return {
        int(year): group.secid.astype("int64").unique()
        for year, group in mapped.groupby(mapped.date.dt.year)
    }


def pull_stage(
    connection: wrds.Connection, constituents: pd.DataFrame
) -> dict[str, float]:
    """Step 2: the surface under stop rule 9.3, the zero curve, returns, CRSP prices and
    the SPX zero-days-to-expiry volume, with wall clock per pull."""
    minutes = {}
    started = time.time()
    log, sample_start = pull_surfaces(connection, secids_by_year(constituents))
    minutes["surface"] = (time.time() - started) / 60.0
    log.to_csv(OUTPUT_DIR / "surface_pull_log.csv", index=False)
    PULL_STATE_PATH.write_text(
        json.dumps(
            {"sample_start": sample_start, "surface_pull_minutes": minutes["surface"]}
        )
    )
    for name, pull in (
        (
            "zero_curve",
            lambda: pull_zero_curve(connection).to_parquet(
                ZERO_CURVE_PATH, index=False
            ),
        ),
        (
            "returns",
            lambda: pull_returns(
                connection,
                np.unique(constituents.secid.dropna().astype("int64").values),
            ),
        ),
        (
            "stock_daily",
            lambda: pull_stock_daily(connection, constituents.permno.unique()),
        ),
        (
            "zero_dte",
            lambda: pull_zero_dte_share(connection).to_parquet(
                ZERO_DTE_PATH, index=False
            ),
        ),
    ):
        started = time.time()
        pull()
        minutes[name] = (time.time() - started) / 60.0
        LOGGER.info("%s pulled in %.1f min", name, minutes[name])
    (OUTPUT_DIR / "pull_minutes.json").write_text(json.dumps(minutes, indent=2))
    return minutes


def _keep_pairs(
    constituents: pd.DataFrame, trade_dates: pd.DatetimeIndex, year: int
) -> pd.DataFrame:
    """Constituent secid-dates of one year and SPX on every trade date of that year."""
    in_year = constituents[(constituents.date.dt.year == year)].dropna(subset=["secid"])
    spx_dates = trade_dates[trade_dates.year == year]
    return pd.concat(
        [
            in_year[["secid", "date"]].astype({"secid": "int64"}),
            pd.DataFrame({"secid": SPX_SECID, "date": spx_dates}),
        ],
        ignore_index=True,
    ).drop_duplicates()


def _construct_year(year: int) -> tuple[int, float, int]:
    """Surface-based and ATM variance at both maturities for one year's constituent
    secid-dates and SPX, a secid-date with no surface rows at a maturity kept with its own
    drop code; written to disk, returning the year, seconds and rows."""
    started = time.time()
    constituents = pd.read_parquet(CONSTITUENTS_PATH)
    trade_dates = pd.DatetimeIndex(pd.read_parquet(TRADE_DATES_PATH).date)
    keep = _keep_pairs(constituents, trade_dates, year)
    curve = pd.read_parquet(ZERO_CURVE_PATH)
    variance = surface_variance_for_year(year, curve, keep)
    atm = atm_variance(load_surface_year(year).merge(keep, on=["secid", "date"]))
    rows = (
        keep.merge(pd.DataFrame({"node": NODES}), how="cross")
        .merge(variance, on=["secid", "date", "node"], how="left")
        .merge(atm, on=["secid", "date", "node"], how="left")
    )
    rows["drop_code"] = rows.drop_code.fillna(NO_SURFACE_ROWS)
    VARIANCE_DIR.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(VARIANCE_DIR / f"variance_{year}.parquet", index=False)
    return year, time.time() - started, len(rows)


def construction_stage(
    constituents: pd.DataFrame, years: list[int], sample_start: str
) -> tuple[pd.DataFrame, str]:
    """Step 3 on the constituents: the newest year serially, the rest across cores when
    the projection from its rows passes the serial limit, and the sample restricted when
    the running time passes the restriction limit. Returns the per-year log and the
    sample start."""
    order = sorted(years, reverse=True)
    expected_rows = constituents.dropna(subset=["secid"]).groupby(
        constituents.date.dt.year
    ).size() * len(NODES)
    log, started = [], time.time()
    year, seconds, rows = _construct_year(order[0])
    log.append({"year": year, "seconds": seconds, "rows": rows, "mode": "serial"})
    projected = seconds / rows * float(expected_rows.loc[order].sum()) / 60.0
    LOGGER.info(
        "construction %d in %.1f s, projected %.1f min", year, seconds, projected
    )
    remaining = order[1:]
    if projected <= CONSTRUCTION_SERIAL_LIMIT_MINUTES:
        for year in remaining:
            if (time.time() - started) / 60.0 > CONSTRUCTION_RESTRICT_LIMIT_MINUTES:
                sample_start = max(sample_start, RESTRICTED_START)
                if year < int(RESTRICTED_START[:4]):
                    break
            year, seconds, rows = _construct_year(year)
            log.append(
                {"year": year, "seconds": seconds, "rows": rows, "mode": "serial"}
            )
            LOGGER.info("construction %d: %d rows in %.1f s", year, rows, seconds)
    else:
        with ProcessPoolExecutor(max_workers=CONSTRUCTION_WORKERS) as executor:
            futures = {
                executor.submit(_construct_year, year): year for year in remaining
            }
            for future in as_completed(futures):
                if future.cancelled():
                    continue
                year, seconds, rows = future.result()
                log.append(
                    {"year": year, "seconds": seconds, "rows": rows, "mode": "parallel"}
                )
                LOGGER.info("construction %d: %d rows in %.1f s", year, rows, seconds)
                if (time.time() - started) / 60.0 > CONSTRUCTION_RESTRICT_LIMIT_MINUTES:
                    sample_start = max(sample_start, RESTRICTED_START)
                    for pending, pending_year in futures.items():
                        if pending_year < int(RESTRICTED_START[:4]):
                            pending.cancel()
    return pd.DataFrame(log).sort_values("year"), sample_start


def load_variances(sample_start: str) -> pd.DataFrame:
    """Surface-based and ATM variance for every constructed year from the sample start,
    the drop code as a category."""
    frames = [
        pq.read_table(path).to_pandas(strings_to_categorical=True)
        for path in sorted(VARIANCE_DIR.glob("variance_*.parquet"))
    ]
    variance = pd.concat(frames, ignore_index=True)
    variance["drop_code"] = variance.drop_code.astype("category")
    variance = variance[(variance.date >= sample_start) & (variance.date <= SAMPLE_END)]
    return variance.reset_index(drop=True)


def results_markdown(
    report: dict[str, object],
    sample_start: str,
    primary: str,
    h1: pd.DataFrame,
    h2: pd.DataFrame,
    cells: pd.DataFrame,
    h3: pd.DataFrame,
    decomposition_table: pd.DataFrame,
    cross_section: pd.DataFrame,
    flat: pd.DataFrame,
    skewed: pd.DataFrame,
    validation: pd.DataFrame,
    drops: pd.DataFrame,
    retained: pd.DataFrame,
    ratio: pd.DataFrame,
    coverage_by_year: pd.DataFrame,
    floors: pd.DataFrame,
    breaks: pd.DataFrame,
    zero_dte: pd.DataFrame,
    pull_log: pd.DataFrame,
    construction_log: pd.DataFrame,
) -> str:
    """RESULTS.md: the headline, every test with all four inference rows, Holm levels and
    verdicts, the robustness rows, the decomposition, the deciles, the validation, the
    coverage by year, the floors and the break date."""
    headline = h1[h1.in_family & (h1.node == 30)].iloc[0]
    median_log_gap = validation.set_index("node").median_log_gap
    ladder_note = (
        "Surface measure against item 1's SPX strike ladder, median log gap: "
        + ", ".join(
            f"{node}-day {median_log_gap.get(node, np.nan):+.4f}" for node in NODES
        )
        + "."
    )

    def verdict_line(
        name: str, frame: pd.DataFrame, text: Callable[[pd.Series], str]
    ) -> str:
        return f"- **{name}**: " + "; ".join(
            f"{int(row.node)}-day {text(row)}, **{row.verdict}**"
            for _, row in frame[frame.in_family].sort_values("node").iterrows()
        )

    lines = ["# Item 2 — results", ""]
    lines += [
        "## Headline",
        "",
        (
            "**H1 gap at the 30-day node, the index log(IV²/RV) minus the equal-weighted "
            f"constituent average on the {MEASURE_LABELS[primary]} measure: "
            f"{_decimal(headline.estimate)}, Newey-West 95 percent interval "
            f"{_interval(headline.nw_ci_low, headline.nw_ci_high)}, block-bootstrap "
            f"interval {_interval(headline.boot_ci_low, headline.boot_ci_high)}, on "
            f"{_count(headline.n)} daily observations.**"
        ),
        "",
        f"- **Sample: {_span(pd.Timestamp(sample_start), pd.Timestamp(SAMPLE_END))}.**",
        verdict_line("H1", h1, lambda row: f"gap {row.estimate:+.4f}"),
        verdict_line("H2", h2, lambda row: f"later minus earlier {row.estimate:+.4f}"),
        verdict_line(
            "H3",
            h3,
            lambda row: f"implied minus realized correlation {row.estimate:+.4f}",
        ),
        "",
        (
            "A hypothesis is supported only when the Newey-West and the stationary "
            "block-bootstrap p-values both clear the Holm-corrected level within the block "
            "of two maturities. The surface measure is built as amended by A1 in section 13 "
            "of the spec."
        ),
        "",
    ]

    inference_headers = [
        "node",
        "measure",
        "weighting",
        "n",
        "estimate",
        "NW 95% interval",
        "p NW",
        "p HH",
        "boot 95% interval",
        "p boot",
        "grid n",
        "p grid",
    ]

    def inference_cells(row: object) -> list[str]:
        return [
            row.node,
            MEASURE_LABELS[row.measure],
            getattr(row, "weighting", "value"),
            _count(row.n),
            f"{row.estimate:+.4f}",
            _interval(row.nw_ci_low, row.nw_ci_high, lambda value: f"{value:+.4f}"),
            _p_value(row.p_newey_west),
            _p_value(row.p_hansen_hodrick),
            _interval(row.boot_ci_low, row.boot_ci_high, lambda value: f"{value:+.4f}"),
            _p_value(row.p_bootstrap),
            int(row.n_grid),
            _p_value(row.p_grid),
        ]

    def test_tables(frame: pd.DataFrame) -> list[str]:
        ordered = frame.sort_values(
            ["node", "measure", "in_family"], ascending=[True, False, False]
        )
        tables = ["#### Family", ""]
        tables += _markdown_table(
            [
                *inference_headers,
                "Holm level NW",
                "Holm level boot",
                "NW clears",
                "boot clears",
                "verdict",
            ],
            [
                [
                    *inference_cells(row),
                    _decimal(row.holm_level_newey_west),
                    _decimal(row.holm_level_bootstrap),
                    _yes_no(row.clears_newey_west),
                    _yes_no(row.clears_bootstrap),
                    f"**{row.verdict}**",
                ]
                for row in ordered[ordered.in_family].itertuples()
            ],
        )
        tables += ["#### Robustness rows, outside the family", ""]
        tables += _markdown_table(
            inference_headers,
            [inference_cells(row) for row in ordered[~ordered.in_family].itertuples()],
        )
        return tables + [ladder_note, ""]

    lines += [
        "## Tests",
        "",
        "### H1 — index premium above the equal-weighted constituent average",
        "",
        (
            f"Daily gap on dates with at least {AVERAGE_FLOOR} constituents carrying a valid "
            f"{MEASURE_LABELS[primary]} variance. One-sided."
        ),
        "",
    ]
    lines += test_tables(h1)

    lines += [
        "### H2 — the gap over the later calm period against the earlier one",
        "",
        (
            f"Mean gap over {H2_AFTER[0]} .. {H2_AFTER[1]} minus the mean over "
            f"{H2_BEFORE[0]} .. {H2_BEFORE[1]}, as the slope on a later-period indicator. "
            "Two-sided."
        ),
        "",
    ]
    lines += _markdown_table(
        [
            "node",
            "measure",
            "weighting",
            "n earlier",
            "mean earlier",
            "n later",
            "mean later",
        ],
        [
            [
                row.node,
                MEASURE_LABELS[row.measure],
                row.weighting,
                _count(row.n_before),
                _decimal(row.mean_before),
                _count(row.n_after),
                _decimal(row.mean_after),
            ]
            for row in h2.sort_values(
                ["node", "measure", "in_family"], ascending=[True, False, False]
            ).itertuples()
        ],
    )
    lines += test_tables(h2)
    lines += ["#### Mean gap by period, no test", ""]
    lines += _markdown_table(
        ["node", "measure", "weighting", "period", "dates", "mean gap"],
        [
            [
                row.node,
                MEASURE_LABELS[row.measure],
                row.weighting,
                row.period,
                _count(row.dates),
                _decimal(row.mean_gap),
            ]
            for row in cells.itertuples()
        ],
    )
    lines += [ladder_note, ""]

    lines += [
        "### H3 — implied correlation above realized correlation",
        "",
        (
            f"Daily difference on dates with at least {CORRELATION_FLOOR} constituents "
            f"carrying a valid {MEASURE_LABELS[primary]} variance, value weights. One-sided."
        ),
        "",
    ]
    lines += _markdown_table(
        ["node", "measure", "mean implied", "mean realized"],
        [
            [
                row.node,
                MEASURE_LABELS[row.measure],
                _decimal(row.mean_rho_implied),
                _decimal(row.mean_rho_realized),
            ]
            for row in h3.sort_values(
                ["node", "in_family"], ascending=[True, False]
            ).itertuples()
        ],
    )
    lines += test_tables(h3)

    lines += ["## Decomposition of the gap by period", ""]
    lines += _markdown_table(
        [
            "node",
            "measure",
            "period",
            "dates",
            "mean gap",
            "correlation component",
            "residual",
        ],
        [
            [
                row.node,
                MEASURE_LABELS[row.measure],
                row.period,
                _count(row.dates),
                _decimal(row.mean_gap),
                _decimal(row.mean_correlation_component),
                _decimal(row.mean_residual),
            ]
            for row in decomposition_table.itertuples()
        ],
    )
    lines += [ladder_note, ""]

    lines += ["## Cross-section of annual single-name premia, 30-day node", ""]
    decile_columns = [f"p{decile}" for decile in range(10, 100, 10)]
    lines += _markdown_table(
        ["year", "names", *decile_columns, "index", "share above index"],
        [
            [
                int(row["year"]),
                _count(row["names"]),
                *[_decimal(row[column], 3) for column in decile_columns],
                _decimal(row["index_premium"], 3),
                _decimal(row["share_above_index"], 3),
            ]
            for _, row in cross_section.iterrows()
        ],
    )
    lines += [ladder_note, ""]

    lines += ["## Validation", "", "### Synthetic surfaces", ""]
    lines += _markdown_table(
        ["check", "days", "result", "target", "tolerance", "passed"],
        [
            [
                f"flat at {row.volatility:.0%}",
                row.days,
                f"recovered fraction of σ² {row.recovered_fraction:.6f}",
                "1",
                f"{SYNTHETIC_TOLERANCE:.1%}",
                _yes_no(row.passed),
            ]
            for row in flat.itertuples()
        ]
        + [
            [
                (
                    f"linear in delta, {row.put_volatility:.0%} at the 10-delta put "
                    f"to {row.call_volatility:.0%} at the 10-delta call"
                ),
                row.days,
                f"gap to a {row.reference_points:,}-strike reference {row.relative_gap:+.4%}",
                "0",
                f"{SYNTHETIC_TOLERANCE:.1%}",
                _yes_no(row.passed),
            ]
            for row in skewed.itertuples()
        ],
    )
    lines += ["### SPX against item 1's strike-ladder series", ""]
    lines += _markdown_table(
        [
            "node",
            "dates",
            "span",
            "correlation",
            "mean gap",
            "median gap",
            "mean log gap",
            "median log gap",
            f"share beyond {VALIDATION_GAP_THRESHOLD:.0%}",
            f"clears {VALIDATION_MIN_CORRELATION}",
        ],
        [
            [
                row.node,
                _count(row.dates),
                _span(row.first_date, row.last_date),
                f"{row.correlation:.4f}",
                f"{row.mean_gap:+.5f}",
                f"{row.median_gap:+.5f}",
                f"{row.mean_log_gap:+.4f}",
                f"{row.median_log_gap:+.4f}",
                _decimal(row.share_beyond_threshold),
                _yes_no(row.passed),
            ]
            for row in validation.itertuples()
        ],
    )
    lines += [
        (
            f"Primary measure under stop rule 9.2: **{MEASURE_LABELS[primary]}**. Gaps are "
            "surface minus ladder in annualised variance and in log units."
        ),
        "",
    ]
    lines += ["### Drops by year and code, constituents", ""]
    wide_drops = drops.pivot_table(
        index=["year", "node"],
        columns="drop_code",
        values="rows",
        fill_value=0,
        observed=True,
    )
    lines += _markdown_table(
        ["year", "node", *wide_drops.columns],
        [
            [year, node, *[_count(value) for value in values]]
            for (year, node), values in wide_drops.iterrows()
        ],
    )
    lines += ["### Median retained secids per date", ""]
    lines += _markdown_table(
        ["year", *[f"{node}-day" for node in NODES]],
        [
            [year, *[_decimal(row.get(node, np.nan), 1) for node in NODES]]
            for year, row in retained.pivot_table(
                index="year", columns="node", values="retained"
            ).iterrows()
        ],
    )

    lines += [
        "### Surface against ATM variance by period, descriptive",
        "",
        (
            "Surface-based over ATM implied variance on rows where both are valid. Added "
            "after the tests ran to describe where the two measures part; no inference."
        ),
        "",
    ]
    lines += _markdown_table(
        ["node", "group", "period", "rows", "p10", "median", "p90", "mean log ratio"],
        [
            [
                row.node,
                row.group,
                row.period,
                _count(row.rows),
                _decimal(row.p10, 3),
                _decimal(row.median, 3),
                _decimal(row.p90, 3),
                f"{row.mean_log_ratio:+.3f}",
            ]
            for row in ratio.itertuples()
        ],
    )
    lines += [
        (
            "Returns at or below -100 percent, which have no log return and count as "
            f"missing: {report['returns_at_or_below_minus_one']}."
        ),
        "",
    ]
    lines += ["## Coverage by year", ""]
    link = report["link_resolution"]
    lines += [
        (
            f"Membership list {report['membership']['first_start'][:10]} .. "
            f"{report['membership']['last_end'][:10]}, {report['membership']['permnos']} "
            f"distinct permnos. {link['permno_dates_with_several_secids']:,} permno-dates "
            f"linked to more than one secid: {link['decided_by_score']:,} decided by score, "
            f"{link['decided_by_surface_history']:,} by surface history, "
            f"{link['decided_by_lower_secid']:,} by the lower secid. Stop rule 9.1: median "
            "share of members with a 30-day 50-delta call "
            f"{float(report['stop_rule_9_1']['median_share_with_surface']):.4f} against "
            f"{LINK_COVERAGE_FLOOR}."
        ),
        "",
    ]
    lines += _markdown_table(
        [
            "year",
            "dates",
            "mean members",
            "median members",
            "mean mapped",
            "median mapped",
            "mean with 30-day call",
            "median with 30-day call",
        ],
        [
            [
                row.year,
                row.dates,
                _decimal(row.mean_members, 1),
                _decimal(row.median_members, 1),
                _decimal(row.mean_mapped, 1),
                _decimal(row.median_mapped, 1),
                _decimal(row.mean_with_surface, 1),
                _decimal(row.median_with_surface, 1),
            ]
            for row in coverage_by_year.itertuples()
        ],
    )

    lines += [
        "## Floors",
        "",
        (
            f"Dates clearing and dropped by the {AVERAGE_FLOOR} floor (H1, H2) and the "
            f"{CORRELATION_FLOOR} floor (H3), counted on valid "
            f"{MEASURE_LABELS[primary]} variances."
        ),
        "",
    ]
    lines += _markdown_table(
        [
            "node",
            "year",
            "trade dates",
            "median valid surface",
            "median valid ATM",
            f"clear {AVERAGE_FLOOR}",
            f"dropped by {AVERAGE_FLOOR}",
            f"clear {CORRELATION_FLOOR}",
            f"dropped by {CORRELATION_FLOOR}",
        ],
        [
            [
                row.node,
                row.year,
                row.trade_dates,
                _decimal(row.median_valid_surface, 1),
                _decimal(row.median_valid_atm, 1),
                row.clear_300,
                row.dropped_by_300,
                row.clear_450,
                row.dropped_by_450,
            ]
            for row in floors.itertuples()
        ],
    )

    lines += ["## Break date in the annual gap, no test", ""]
    lines += _markdown_table(
        ["node", "years", "minimum regime", "break year", "mean before", "mean after"],
        [
            [
                row.node,
                f"{row.first_year} .. {row.last_year}",
                row.minimum_regime_years,
                f"**{row.break_year}**",
                _decimal(row.mean_before),
                _decimal(row.mean_after),
            ]
            for row in breaks.itertuples()
        ],
    )
    lines += ["### SPX option volume share at zero days to expiry", ""]
    lines += _markdown_table(
        ["year", "volume", "zero-DTE volume", "share"],
        [
            [
                row.year,
                _count(row.volume),
                _count(row.zero_dte_volume),
                _decimal(row.zero_dte_share),
            ]
            for row in zero_dte.itertuples()
        ],
    )

    lines += ["## Wall clock", ""]
    lines += _markdown_table(
        ["surface pull year", "secids", "rows", "seconds", "running minutes"],
        [
            [
                row.year,
                row.secids,
                _count(row.rows),
                _decimal(row.seconds, 1),
                _decimal(row.running_minutes, 1),
            ]
            for row in pull_log.itertuples()
        ],
    )
    lines += _markdown_table(
        ["construction year", "rows", "seconds", "mode"],
        [
            [row.year, _count(row.rows), _decimal(row.seconds, 1), row.mode]
            for row in construction_log.itertuples()
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
    for directory in (DATA_DIR / "raw", OUTPUT_DIR, FIGURES_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    minutes: dict[str, float] = {}

    connection = None if arguments.skip_pull else connect()
    started = time.time()
    constituents, trade_dates, report = membership_stage(connection)
    minutes["membership"] = (time.time() - started) / 60.0

    if connection is not None:
        minutes.update(pull_stage(connection, constituents))
        connection.close()
    sample_start = max(
        report["sample_start"], json.loads(PULL_STATE_PATH.read_text())["sample_start"]
    )
    market_cap = previous_day_market_cap()
    market_cap.to_parquet(MARKET_CAP_PATH, index=False)

    flat = check_flat_surface()
    skewed = check_skewed_surface()
    flat.to_csv(OUTPUT_DIR / "flat_surface_check.csv", index=False)
    skewed.to_csv(OUTPUT_DIR / "skewed_surface_check.csv", index=False)
    if not (flat.passed.all() and skewed.passed.all()):
        raise RuntimeError(
            "surface construction fails the synthetic checks: flat recovered fractions "
            + ", ".join(
                f"{row.days} days {row.recovered_fraction:.6f}"
                for row in flat.itertuples()
            )
            + "; skewed gaps "
            + ", ".join(
                f"{row.days} days {row.relative_gap:+.4%}"
                for row in skewed.itertuples()
            )
            + f"; tolerance {SYNTHETIC_TOLERANCE:.1%}"
        )

    started = time.time()
    curve = pd.read_parquet(ZERO_CURVE_PATH)
    ladder = load_ladder_series()
    spx = pd.concat(
        [
            surface_variance_for_year(
                year,
                curve,
                pd.DataFrame(
                    {"secid": SPX_SECID, "date": trade_dates[trade_dates.year == year]}
                ),
            )
            for year in sorted(ladder.date.dt.year.unique())
        ],
        ignore_index=True,
    )
    validation, compared = validate_against_ladder(spx, ladder)
    validation.to_csv(OUTPUT_DIR / "validation_summary.csv", index=False)
    compared.to_csv(OUTPUT_DIR / "validation_daily.csv", index=False)
    plot_validation(compared, validation, OUTPUT_DIR / "fig_validation")
    # Stop rule 9.2 judges the construction as a whole: a failure at either maturity makes
    # ATM the primary measure at both.
    primary = "surface" if validation.passed.all() else "atm"
    minutes["validation"] = (time.time() - started) / 60.0

    started = time.time()
    years = [
        year for year in secids_by_year(constituents) if year >= int(sample_start[:4])
    ]
    construction_log, sample_start = construction_stage(
        constituents, years, sample_start
    )
    construction_log.to_csv(OUTPUT_DIR / "construction_log.csv", index=False)
    minutes["construction"] = (time.time() - started) / 60.0
    variance = load_variances(sample_start)
    trade_dates = trade_dates[trade_dates >= sample_start]
    names_variance = variance[variance.secid != SPX_SECID]
    drops = drop_counts(names_variance)
    drops.to_csv(OUTPUT_DIR / "drop_counts.csv", index=False)
    retained = (
        names_variance[names_variance.drop_code == "OK"]
        .groupby(["date", "node"])
        .size()
        .rename("retained")
        .reset_index()
    )
    retained = (
        retained.groupby([retained.date.dt.year.rename("year"), "node"])
        .retained.median()
        .reset_index()
    )
    retained.to_csv(OUTPUT_DIR / "retained_by_year.csv", index=False)
    ratio = surface_to_atm_ratio(variance)
    ratio.to_csv(OUTPUT_DIR / "surface_to_atm_ratio.csv", index=False)

    started = time.time()
    constituents = constituents[constituents.date >= sample_start]
    returns = load_returns()
    report["returns_at_or_below_minus_one"] = int((returns["return"] <= -1).sum())
    realized = realized_variances(returns, trade_dates, variance[["secid", "date"]])
    premium = premiums(
        variance[["secid", "date", "node", "implied_var", "drop_code"]],
        variance[["secid", "date", "node", "implied_var_atm"]],
        realized,
    )
    names = premium[premium.secid != SPX_SECID].merge(
        member_secids(constituents, market_cap), on=["date", "secid"]
    )
    names.to_parquet(NAME_PREMIUM_PATH, index=False)
    index = premium[premium.secid == SPX_SECID]
    daily = daily_averages(names, index, primary)
    daily = decomposition(correlations(names, daily))
    daily.to_parquet(DAILY_PANEL_PATH, index=False)
    grid = non_overlapping_grid(daily, trade_dates, sample_start)
    grid.to_parquet(GRID_PANEL_PATH, index=False)
    annual = annual_means(daily)
    cross_section = annual_cross_section(names, daily, primary)
    decomposition_table = decomposition_by_period(daily)
    floors = floor_counts(daily, trade_dates)
    minutes["premiums"] = (time.time() - started) / 60.0

    started = time.time()
    h1 = h1_tests(daily, grid, primary)
    h2 = h2_tests(daily, grid, primary)
    cells = period_cells(daily)
    h3 = h3_tests(daily, grid, primary)
    breaks = break_date(annual, f"gap_{primary}_ew")
    zero_dte = pd.read_parquet(ZERO_DTE_PATH)
    minutes["tests"] = (time.time() - started) / 60.0

    plot_post_figure(annual, OUTPUT_DIR / FIGURE_NAMES[0], primary)
    plot_correlations(annual, OUTPUT_DIR / FIGURE_NAMES[1], primary)
    plot_decile_band(cross_section, OUTPUT_DIR / FIGURE_NAMES[2])
    plot_gap_and_zero_dte(
        annual, zero_dte, breaks, OUTPUT_DIR / FIGURE_NAMES[3], primary
    )
    for name in FIGURE_NAMES:
        shutil.copy2(OUTPUT_DIR / f"{name}.png", FIGURES_DIR / f"{name}.png")

    for name, table in {
        "h1_tests": h1,
        "h2_tests": h2,
        "h2_period_cells": cells,
        "h3_tests": h3,
        "decomposition_by_period": decomposition_table,
        "cross_section_deciles": cross_section,
        "annual_means": annual,
        "floor_counts": floors,
        "break_date": breaks,
        "zero_dte_share": zero_dte,
    }.items():
        table.to_csv(OUTPUT_DIR / f"{name}.csv", index=False)
    (OUTPUT_DIR / "RESULTS.md").write_text(
        results_markdown(
            report,
            sample_start,
            primary,
            h1,
            h2,
            cells,
            h3,
            decomposition_table,
            cross_section,
            flat,
            skewed,
            validation,
            drops,
            retained,
            ratio,
            pd.read_csv(OUTPUT_DIR / "coverage_by_year.csv"),
            floors,
            breaks,
            zero_dte,
            pd.read_csv(OUTPUT_DIR / "surface_pull_log.csv"),
            construction_log,
        )
    )
    (OUTPUT_DIR / "stage_minutes.json").write_text(json.dumps(minutes, indent=2))
    LOGGER.info("stage minutes: %s", minutes)


if __name__ == "__main__":
    main()
