"""Figures: the annual index and constituent premia, implied against realized
correlation, the yearly decile band of single-name premia, the gap with the
zero-days-to-expiry volume share and the break date, and the surface validation."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from options_series.item1.figures import _save
from options_series.item2.config import NODES, PERIODS, SAMPLE_END

INDEX_COLOR = "#111111"
AVERAGE_COLOR = "#1f4e79"
IMPLIED_COLOR = "#c0392b"
REALIZED_COLOR = "#1f4e79"
ZERO_DTE_COLOR = "#b8860b"
PERIOD_SHADES = {
    "1996-2007": "#f2f2f2",
    "2008-2009": "#f6dcd8",
    "2010-2019": "#e8eef5",
    "2020": "#f6dcd8",
    "2021-2025": "#e6f0e3",
}
PARTIAL_YEAR = int(SAMPLE_END[:4]) if SAMPLE_END[5:] != "12-31" else None
THIN_CELL_DAYS = 30


def _shade_periods(axis: Axes, first_year: int, last_year: int) -> None:
    """Shade the five reporting periods and label each along the top of the axis."""
    for label, (start, end) in PERIODS.items():
        low, high = max(int(start[:4]), first_year), min(int(end[:4]), last_year)
        if low > high:
            continue
        axis.axvspan(low - 0.5, high + 0.5, color=PERIOD_SHADES[label], zorder=0, lw=0)
        axis.annotate(
            label,
            ((low + high) / 2, 1.0),
            xycoords=("data", "axes fraction"),
            xytext=(0, -12),
            textcoords="offset points",
            ha="center",
            fontsize=8.5,
            color="#555555",
        )


def _year_axis(axis: Axes, first_year: int, last_year: int) -> None:
    """Calendar-year ticks every other year with a light grid."""
    axis.set_xlim(first_year - 0.6, last_year + 0.6)
    axis.set_xticks(range(first_year, last_year + 1, 2))
    axis.grid(alpha=0.25, lw=0.5, zorder=0)
    axis.set_xlabel("calendar year")


def _series(
    axis: Axes, years: np.ndarray, values: np.ndarray, color: str, marker: str
) -> None:
    """A line with filled markers, the partial final year drawn as an open marker."""
    axis.plot(years, values, color=color, lw=1.7, zorder=3)
    partial = years == PARTIAL_YEAR
    axis.scatter(
        years[~partial],
        values[~partial],
        s=40,
        color=color,
        marker=marker,
        edgecolors="white",
        linewidths=0.8,
        zorder=4,
    )
    axis.scatter(
        years[partial],
        values[partial],
        s=40,
        facecolors="white",
        edgecolors=color,
        marker=marker,
        linewidths=1.6,
        zorder=4,
    )


def plot_post_figure(
    annual: pd.DataFrame, path: Path, primary: str = "surface"
) -> None:
    """Annual mean log(IV²/RV) at 30 days: the S&P 500 index against the equal-weighted
    average of its constituents, the five periods shaded."""
    index_column, average_column = f"index_premium_{primary}", f"ew_premium_{primary}"
    rows = annual[annual.node == 30].dropna(subset=[index_column]).sort_values("year")
    years = rows.year.values
    first_year, last_year = int(years.min()), int(years.max())
    figure, axis = plt.subplots(figsize=(11.5, 6.0))
    figure.subplots_adjust(left=0.07, right=0.98, bottom=0.10, top=0.82)
    _shade_periods(axis, first_year, last_year)
    axis.axhline(0, color="#555555", lw=0.9, zorder=1)
    _series(axis, years, rows[index_column].values, INDEX_COLOR, "o")
    _series(axis, years, rows[average_column].values, AVERAGE_COLOR, "s")
    thin = rows[rows.average_floor_dates < THIN_CELL_DAYS]
    for _, cell in thin.iterrows():
        axis.annotate(
            f"n={int(cell.average_floor_dates)}",
            (cell.year, cell[index_column]),
            textcoords="offset points",
            xytext=(8, 8),
            fontsize=7.5,
            color="#d62728",
        )
    _year_axis(axis, first_year, last_year)
    axis.set_ylabel("annual mean log(IV$^2$/RV)")
    figure.suptitle(
        "Annual mean log(IV$^2$/RV), 30-day maturity: the S&P 500 index against its constituents",
        y=0.975,
        fontsize=12,
    )
    handles = [
        Line2D(
            [],
            [],
            color=INDEX_COLOR,
            marker="o",
            lw=1.7,
            markeredgecolor="white",
            label="S&P 500 index",
        ),
        Line2D(
            [],
            [],
            color=AVERAGE_COLOR,
            marker="s",
            lw=1.7,
            markeredgecolor="white",
            label="equal-weighted average across constituents",
        ),
        Line2D(
            [],
            [],
            color="#555555",
            marker="o",
            lw=0,
            markerfacecolor="white",
            markeredgewidth=1.6,
            label=f"partial year ({PARTIAL_YEAR}): open marker",
        ),
    ]
    figure.legend(
        handles=handles,
        frameon=False,
        fontsize=9,
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.935),
    )
    _save(figure, path)


def plot_correlations(
    annual: pd.DataFrame, path: Path, primary: str = "surface"
) -> None:
    """Figure 2: annual mean implied and realized correlation, one panel per maturity."""
    figure, axes = plt.subplots(2, 1, figsize=(11.5, 8.6), sharex=True)
    for axis, node in zip(axes, NODES):
        rows = (
            annual[annual.node == node]
            .dropna(subset=[f"rho_implied_{primary}"])
            .sort_values("year")
        )
        years = rows.year.values
        first_year, last_year = int(years.min()), int(years.max())
        _shade_periods(axis, first_year, last_year)
        _series(axis, years, rows[f"rho_implied_{primary}"].values, IMPLIED_COLOR, "o")
        _series(
            axis, years, rows[f"rho_realized_{primary}"].values, REALIZED_COLOR, "s"
        )
        axis.set_ylabel("annual mean correlation")
        axis.set_title(f"{node}-day maturity", loc="left", fontsize=11)
        _year_axis(axis, first_year, last_year)
    axes[0].set_xlabel("")
    figure.subplots_adjust(left=0.07, right=0.98, bottom=0.07, top=0.86, hspace=0.22)
    figure.suptitle(
        "Figure 2. Implied against realized correlation of the S&P 500 constituents, "
        "value weights",
        y=0.975,
        fontsize=12,
    )
    figure.legend(
        handles=[
            Line2D(
                [],
                [],
                color=IMPLIED_COLOR,
                marker="o",
                lw=1.7,
                label="implied correlation",
            ),
            Line2D(
                [],
                [],
                color=REALIZED_COLOR,
                marker="s",
                lw=1.7,
                label="realized correlation over the following window",
            ),
        ],
        frameon=False,
        fontsize=9,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.945),
    )
    _save(figure, path)


def plot_decile_band(cross_section: pd.DataFrame, path: Path) -> None:
    """Figure 3: the yearly decile band of annual single-name premia at 30 days with the
    index premium overlaid."""
    rows = cross_section.sort_values("year")
    years = rows.year.values
    first_year, last_year = int(years.min()), int(years.max())
    figure, axis = plt.subplots(figsize=(11.5, 6.2))
    _shade_periods(axis, first_year, last_year)
    axis.axhline(0, color="#555555", lw=0.9, zorder=1)
    for low, high, alpha in (
        ("p10", "p90", 0.18),
        ("p20", "p80", 0.26),
        ("p30", "p70", 0.34),
        ("p40", "p60", 0.42),
    ):
        axis.fill_between(
            years,
            rows[low],
            rows[high],
            color=AVERAGE_COLOR,
            alpha=alpha,
            lw=0,
            zorder=2,
        )
    axis.plot(years, rows.p50, color=AVERAGE_COLOR, lw=1.4, zorder=3)
    _series(axis, years, rows.index_premium.values, INDEX_COLOR, "o")
    _year_axis(axis, first_year, last_year)
    axis.set_ylabel("annual mean log(IV$^2$/RV)")
    figure.subplots_adjust(left=0.07, right=0.98, bottom=0.10, top=0.82)
    figure.suptitle(
        "Figure 3. Cross-section of annual single-name premia, 30-day maturity",
        y=0.975,
        fontsize=12,
    )
    figure.legend(
        handles=[
            Patch(
                facecolor=AVERAGE_COLOR,
                alpha=0.3,
                label="single names, 10th to 90th percentile in decile bands",
            ),
            Line2D([], [], color=AVERAGE_COLOR, lw=1.4, label="single-name median"),
            Line2D(
                [], [], color=INDEX_COLOR, marker="o", lw=1.7, label="S&P 500 index"
            ),
        ],
        frameon=False,
        fontsize=9,
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.935),
    )
    _save(figure, path)


def plot_gap_and_zero_dte(
    annual: pd.DataFrame,
    zero_dte: pd.DataFrame,
    breaks: pd.DataFrame,
    path: Path,
    primary: str = "surface",
) -> None:
    """Figure 4: the annual index-minus-average gap at both maturities, the share of SPX
    option volume at zero days to expiry, and the estimated break year."""
    column = f"gap_{primary}_ew"
    rows = annual.dropna(subset=[column])
    first_year, last_year = int(rows.year.min()), int(rows.year.max())
    figure, axis = plt.subplots(figsize=(11.5, 6.2))
    figure.subplots_adjust(left=0.07, right=0.92, bottom=0.10, top=0.80)
    share = axis.twinx()
    _shade_periods(share, first_year, last_year)
    volume = zero_dte[(zero_dte.year >= first_year) & (zero_dte.year <= last_year)]
    share.bar(
        volume.year,
        volume.zero_dte_share,
        width=0.6,
        color=ZERO_DTE_COLOR,
        alpha=0.45,
        zorder=1,
    )
    share.set_ylim(0, max(0.05, float(volume.zero_dte_share.max()) * 1.15))
    share.set_ylabel("share of SPX option volume at zero days to expiry")
    axis.set_zorder(share.get_zorder() + 1)
    axis.patch.set_visible(False)
    axis.axhline(0, color="#555555", lw=0.9, zorder=1)
    for node, color, marker in ((30, INDEX_COLOR, "o"), (91, AVERAGE_COLOR, "s")):
        at_node = rows[rows.node == node].sort_values("year")
        _series(axis, at_node.year.values, at_node[column].values, color, marker)
        found = breaks[breaks.node == node]
        if len(found):
            axis.axvline(
                found.break_year.iloc[0] - 0.5, color=color, ls="--", lw=1.2, zorder=2
            )
    axis.set_ylabel("annual mean gap, index minus equal-weighted average")
    _year_axis(axis, first_year, last_year)
    figure.suptitle(
        "Figure 4. The index-minus-average gap by year, the zero-days-to-expiry volume "
        "share and the estimated break",
        y=0.975,
        fontsize=12,
    )
    figure.legend(
        handles=[
            Line2D([], [], color=INDEX_COLOR, marker="o", lw=1.7, label="gap, 30-day"),
            Line2D(
                [], [], color=AVERAGE_COLOR, marker="s", lw=1.7, label="gap, 91-day"
            ),
            Line2D(
                [],
                [],
                color="#555555",
                ls="--",
                lw=1.2,
                label="estimated break, in the color of its maturity",
            ),
            Patch(
                facecolor=ZERO_DTE_COLOR,
                alpha=0.45,
                label="zero-days-to-expiry share (right axis)",
            ),
        ],
        frameon=False,
        fontsize=9,
        ncol=4,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.935),
    )
    _save(figure, path)


def plot_validation(merged: pd.DataFrame, summary: pd.DataFrame, path: Path) -> None:
    """SPX surface-based variance against item 1's strike-ladder variance, one panel per
    maturity."""
    figure, axes = plt.subplots(1, 2, figsize=(12.5, 5.6))
    for axis, node in zip(axes, NODES):
        rows = merged[merged.node == node]
        stats = summary[summary.node == node].iloc[0]
        axis.scatter(
            rows.ladder_var,
            rows.surface_var,
            s=3,
            alpha=0.3,
            color=AVERAGE_COLOR,
            edgecolors="none",
        )
        limit = [0, float(max(rows.ladder_var.max(), rows.surface_var.max())) * 1.05]
        axis.plot(limit, limit, color="#c00000", lw=1, ls="--", label="45 degrees")
        axis.set_xlim(limit)
        axis.set_ylim(limit)
        axis.set_xlabel("strike-ladder model-free variance")
        axis.set_ylabel("surface-based model-free variance")
        axis.set_title(
            f"{node}-day, n = {int(stats.dates)}, corr = {stats.correlation:.4f}, "
            f"median log gap = {stats.median_log_gap:+.4f}",
            loc="left",
            fontsize=10,
        )
        axis.legend(frameon=False, fontsize=9)
        axis.grid(alpha=0.25, lw=0.5)
    figure.suptitle(
        "SPX surface-based against strike-ladder model-free variance", y=0.99
    )
    figure.tight_layout()
    _save(figure, path)
