"""Figures of spec section 18: pooled daily marked equity with the stress windows, its
fan over the execution fraction, and the mean cycle return over the cost grid."""

from __future__ import annotations

import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.axes import Axes

from options_series.item1.figures import _save
from options_series.item3.config import EXECUTION_FRACTIONS, FIGURES_DIR

INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
SHADE = "#efeeea"
ARM_COLORS = {"strip": "#2a78d6", "straddle": "#eb6834"}
ARM_RAMPS = {
    "strip": ("#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"),
    "straddle": ("#ef9166", "#e56f38", "#c9531f", "#9c3f16", "#6f2c0d"),
}
ARM_LABELS = {"strip": "variance strip", "straddle": "ATM straddle"}
ARM_TITLES = {"strip": "Variance strip", "straddle": "ATM straddle"}
STRESS_WINDOWS = (
    ("autumn 2008", "2008-09-01", "2008-11-30"),
    ("Mar to Apr 2020", "2020-03-01", "2020-04-30"),
    ("2022, UNG", "2022-01-01", "2022-12-31"),
)


def _style(axis: Axes) -> None:
    """Recessive grid and spines, ink-coloured ticks."""
    axis.grid(axis="y", color=GRID, lw=0.6, zorder=0)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axis.spines[side].set_color(MUTED)
    axis.tick_params(colors=MUTED, labelsize=8.5)
    axis.axhline(0, color=MUTED, lw=0.8, zorder=1)


def _shade(axis: Axes, label: bool) -> None:
    """Shade the named stress windows of section 11, labelled along the top."""
    for position, (name, start, end) in enumerate(STRESS_WINDOWS):
        axis.axvspan(
            pd.Timestamp(start), pd.Timestamp(end), color=SHADE, lw=0, zorder=0
        )
        if label:
            axis.annotate(
                name,
                (pd.Timestamp(start), 1.0),
                xycoords=("data", "axes fraction"),
                xytext=(2, -11 - 11 * (position % 2)),
                textcoords="offset points",
                fontsize=7.5,
                color=MUTED,
            )


def _end_label(axis: Axes, series: pd.DataFrame, text: str, color: str) -> None:
    """Label a line at its right end in ink, with a colour swatch carried by the line."""
    last = series.iloc[-1]
    axis.annotate(
        text,
        (last.date, last.equity),
        xytext=(4, 0),
        textcoords="offset points",
        va="center",
        fontsize=8,
        color=INK,
    )
    axis.plot([last.date], [last.equity], "o", ms=4, color=color, zorder=4)


def _panel_a(axis: Axes, primary: dict[str, pd.DataFrame], prefix: str) -> None:
    """Pooled daily marked equity at the primary cell for both arms, with the stress
    windows shaded."""
    _shade(axis, label=True)
    for arm, series in primary.items():
        axis.plot(
            series.date,
            series.equity,
            color=ARM_COLORS[arm],
            lw=1.4,
            zorder=3,
            label=ARM_LABELS[arm],
        )
        _end_label(axis, series, ARM_LABELS[arm], ARM_COLORS[arm])
    _style(axis)
    axis.set_title(
        f"{prefix}Pooled daily marked equity, k = 0.5 and c = 2 bps",
        loc="left",
        fontsize=11,
        color=INK,
    )
    axis.set_ylabel(
        "cumulative return per unit of entry premium", fontsize=9, color=MUTED
    )
    axis.legend(frameon=False, fontsize=8.5, loc="upper left", bbox_to_anchor=(0, 0.93))
    axis.margins(x=0.06)


def plot_equity(
    primary: dict[str, pd.DataFrame],
    fans: dict[str, dict[float, pd.DataFrame]],
    path: Path,
) -> None:
    """Figure 1. Panel A: pooled daily marked equity at k = 0.5 and c = 2 bps for both
    arms. Panel B: each arm's series over the five execution fractions at c = 2 bps."""
    figure = plt.figure(figsize=(11, 8.2))
    grid = figure.add_gridspec(
        2, 2, height_ratios=(1.15, 1), hspace=0.38, wspace=0.28, bottom=0.12, top=0.95
    )
    _panel_a(figure.add_subplot(grid[0, :]), primary, "A. ")
    for position, (arm, by_k) in enumerate(fans.items()):
        axis = figure.add_subplot(grid[1, position])
        _shade(axis, label=False)
        for k, color in zip(EXECUTION_FRACTIONS, ARM_RAMPS[arm]):
            series = by_k[k]
            axis.plot(
                series.date,
                series.equity,
                color=color,
                lw=1.1,
                zorder=3,
                label=f"k = {k:g}",
            )
            _end_label(axis, series, f"k = {k:g}", color)
        _style(axis)
        axis.set_title(
            f"B. {ARM_TITLES[arm]}, c = 2 bps, by execution fraction k",
            loc="left",
            fontsize=10,
            color=INK,
        )
        axis.legend(
            frameon=False,
            fontsize=7.5,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.1),
            ncol=5,
            handlelength=1.2,
            columnspacing=0.8,
        )
        axis.margins(x=0.1)
    figure.text(
        0.01,
        0.012,
        "Strip on rule-2-passing cycles, straddle on cycles within 5 percent of F; "
        "truncated split cycles enter to their last valid mark. Shading marks the "
        "section 11 stress windows.",
        fontsize=7.5,
        color=MUTED,
    )
    _save(figure, path)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(path.with_suffix(".png"), FIGURES_DIR / path.with_suffix(".png").name)


def plot_cost_grid(means: pd.DataFrame, path: Path) -> None:
    """Figure 2: pooled mean cycle return over the k by c grid, one panel per arm,
    one line per hedge cost across the execution fractions."""
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=False)
    costs = sorted(means.c.unique())
    for axis, arm in zip(axes, ("strip", "straddle")):
        rows = means[means.arm == arm]
        ramp = ARM_RAMPS[arm][1:]
        for c, color in zip(costs, ramp):
            line = rows[rows.c == c].sort_values("k")
            axis.plot(
                line.k,
                line["mean"],
                color=color,
                lw=1.6,
                marker="o",
                ms=5,
                zorder=3,
                label=f"c = {c * 1e4:g} bps",
            )
            axis.annotate(
                f"{c * 1e4:g} bps",
                (line.k.iloc[-1], line["mean"].iloc[-1]),
                xytext=(5, 0),
                textcoords="offset points",
                va="center",
                fontsize=8,
                color=INK,
            )
        _style(axis)
        axis.set_xticks(EXECUTION_FRACTIONS)
        axis.set_xlabel(
            "execution fraction k of the quoted half-spread", fontsize=9, color=MUTED
        )
        axis.set_title(ARM_TITLES[arm], loc="left", fontsize=11, color=INK)
        axis.legend(frameon=False, fontsize=8, loc="upper right")
        axis.margins(x=0.12)
    axes[0].set_ylabel(
        "mean cycle return per unit of entry premium", fontsize=9, color=MUTED
    )
    figure.suptitle(
        "Mean pooled cycle return over the cost grid, estimation window",
        x=0.01,
        ha="left",
        fontsize=11,
        color=INK,
    )
    figure.tight_layout()
    _save(figure, path)
    shutil.copy(path.with_suffix(".png"), FIGURES_DIR / path.with_suffix(".png").name)


def plot_pooled_equity(primary: dict[str, pd.DataFrame], path: Path) -> None:
    """Figure 1 panel A on its own, the section figure of the writeup."""
    figure, axis = plt.subplots(figsize=(11, 4.6))
    _panel_a(axis, primary, "")
    figure.text(
        0.01,
        0.015,
        "Strip on rule-2-passing cycles, straddle on cycles within 5 percent of F; "
        "truncated split cycles enter to their last valid mark. Shading marks the "
        "section 11 stress windows.",
        fontsize=7.5,
        color=MUTED,
    )
    figure.subplots_adjust(left=0.07, right=0.9, top=0.92, bottom=0.12)
    _save(figure, path)
    shutil.copy(path.with_suffix(".png"), FIGURES_DIR / path.with_suffix(".png").name)


def plot_cost_drift(by_year: pd.DataFrame, path: Path, c_bps: float = 2.0) -> None:
    """Breakeven k by entry year at one hedge cost, both arms, with the holdout years
    shaded and the grid's bounds at k = 0 and k = 1 marked."""
    column = f"breakeven_k_c{c_bps:g}"
    figure, axis = plt.subplots(figsize=(11, 4.6))
    holdout = by_year.loc[by_year.holdout, "entry_year"]
    axis.axvspan(holdout.min() - 0.5, holdout.max() + 0.5, color=SHADE, lw=0, zorder=0)
    axis.annotate(
        "holdout",
        (holdout.min() - 0.5, 1.0),
        xycoords=("data", "axes fraction"),
        xytext=(3, -11),
        textcoords="offset points",
        fontsize=7.5,
        color=MUTED,
    )
    axis.axhline(1.0, color=MUTED, lw=0.8, ls=(0, (4, 3)), zorder=1)
    for arm in ("strip", "straddle"):
        rows = by_year[by_year.arm == arm].sort_values("entry_year")
        axis.plot(
            rows.entry_year,
            rows[column],
            color=ARM_COLORS[arm],
            lw=1.6,
            marker="o",
            ms=5,
            zorder=3,
            label=ARM_LABELS[arm],
        )
        last = rows.iloc[-1]
        axis.annotate(
            ARM_LABELS[arm],
            (last.entry_year, last[column]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=INK,
        )
    _style(axis)
    axis.set_xticks(sorted(by_year.entry_year.unique()))
    axis.set_xlim(by_year.entry_year.min() - 0.6, by_year.entry_year.max() + 1.4)
    axis.set_xlabel("entry year", fontsize=9, color=MUTED)
    axis.set_ylabel(f"breakeven k at c = {c_bps:g} bps", fontsize=9, color=MUTED)
    axis.set_title(
        f"Breakeven execution fraction by entry year, c = {c_bps:g} bps",
        loc="left",
        fontsize=11,
        color=INK,
    )
    axis.legend(frameon=False, fontsize=8.5, loc="upper right")
    figure.text(
        0.01,
        0.015,
        "Pooled per entry date, then averaged over the year's entries. The dashed line "
        "marks k = 1, the full quoted half-spread; above it the arm survives the full "
        "half-spread, and below 0 it loses at mid.",
        fontsize=7.5,
        color=MUTED,
    )
    figure.subplots_adjust(left=0.07, right=0.93, top=0.9, bottom=0.17)
    _save(figure, path)
    shutil.copy(path.with_suffix(".png"), FIGURES_DIR / path.with_suffix(".png").name)


GATE_COLORS = {
    "unconditional": "#2a78d6",
    "O1 gate": "#1baf7a",
    "O2 gate": "#eda100",
}
GATE_LABELS = {
    "unconditional": "unconditional strip",
    "O1 gate": "O1 gate, median",
    "O2 gate": "O2 gate, 90th percentile",
}


def plot_gates(curves: pd.DataFrame, path: Path) -> None:
    """Section 7's implementation figure: pooled cumulative strip return at k = 0.5 and
    c = 2 bps, unconditional and under each gate, with the holdout shaded."""
    figure, axis = plt.subplots(figsize=(11, 4.6))
    axis.axvspan(
        pd.Timestamp("2022-01-01"), curves.entry.max(), color=SHADE, lw=0, zorder=0
    )
    axis.annotate(
        "holdout",
        (pd.Timestamp("2022-01-01"), 1.0),
        xycoords=("data", "axes fraction"),
        xytext=(3, -11),
        textcoords="offset points",
        fontsize=7.5,
        color=MUTED,
    )
    ends = []
    for label, color in GATE_COLORS.items():
        rows = curves[curves.series == label].sort_values("entry")
        axis.plot(
            rows.entry,
            rows.cumulative,
            color=color,
            lw=1.6,
            zorder=3,
            label=GATE_LABELS[label],
        )
        ends.append((rows.cumulative.iloc[-1], rows.entry.iloc[-1], label, color))
    ends.sort()
    for position, (value, date, label, color) in enumerate(ends):
        axis.annotate(
            GATE_LABELS[label],
            (date, value),
            xytext=(6, -10 + 10 * position),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=INK,
        )
        axis.plot([date], [value], "o", ms=4, color=color, zorder=4)
    _style(axis)
    axis.set_title(
        "O1 and O2 gates on the strip, pooled cycle returns at k = 0.5 and c = 2 bps",
        loc="left",
        fontsize=11,
        color=INK,
    )
    axis.set_ylabel(
        "cumulative return per unit of entry premium", fontsize=9, color=MUTED
    )
    axis.legend(frameon=False, fontsize=8.5, loc="upper left")
    axis.margins(x=0.02)
    figure.text(
        0.01,
        0.015,
        "Implementation view with no test. Skipped cycles enter as zero returns; each "
        "fund's first 36 cycles always trade.",
        fontsize=7.5,
        color=MUTED,
    )
    figure.subplots_adjust(left=0.07, right=0.83, top=0.9, bottom=0.12)
    _save(figure, path)
    shutil.copy(path.with_suffix(".png"), FIGURES_DIR / path.with_suffix(".png").name)


def plot_o2(table: pd.DataFrame, path: Path) -> None:
    """Section 7's O2 exploratory series: mean and median cycle return at k = 0.5 and
    c = 2 bps by O2 quintile, one panel per arm, with no p-value."""
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    for axis, arm in zip(axes, ("strip", "straddle")):
        rows = table[(table.arm == arm) & (table.o2_quintile != "all")].copy()
        rows["o2_quintile"] = rows.o2_quintile.astype(int)
        rows = rows.sort_values("o2_quintile")
        color = ARM_COLORS[arm]
        axis.plot(
            rows.o2_quintile,
            rows.mean_return,
            color=color,
            lw=1.6,
            marker="o",
            ms=6,
            zorder=3,
            label="mean",
        )
        axis.plot(
            rows.o2_quintile,
            rows.median_return,
            color=color,
            lw=1.0,
            ls=(0, (4, 3)),
            marker="o",
            ms=6,
            markerfacecolor="white",
            zorder=3,
            label="median",
        )
        _style(axis)
        axis.set_xticks(
            rows.o2_quintile,
            [
                f"{low:.2f} to {high:.2f}"
                for low, high in zip(rows.o2_low, rows.o2_high)
            ],
            fontsize=7.5,
        )
        axis.set_xlabel(
            "O2 = IV30 / IV91 at entry, by quintile", fontsize=9, color=MUTED
        )
        axis.set_title(ARM_TITLES[arm], loc="left", fontsize=11, color=INK)
        axis.legend(frameon=False, fontsize=8, loc="lower right")
        axis.margins(x=0.08)
    axes[0].set_ylabel(
        "cycle return per unit of entry premium", fontsize=9, color=MUTED
    )
    figure.suptitle(
        "O2 against cycle returns at k = 0.5 and c = 2 bps, exploratory with no p-value",
        x=0.01,
        ha="left",
        fontsize=11,
        color=INK,
    )
    figure.tight_layout()
    _save(figure, path)
    shutil.copy(path.with_suffix(".png"), FIGURES_DIR / path.with_suffix(".png").name)
