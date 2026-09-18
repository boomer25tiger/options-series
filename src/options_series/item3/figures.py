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
    top = figure.add_subplot(grid[0, :])
    _shade(top, label=True)
    for arm, series in primary.items():
        top.plot(
            series.date,
            series.equity,
            color=ARM_COLORS[arm],
            lw=1.4,
            zorder=3,
            label=ARM_LABELS[arm],
        )
        _end_label(top, series, ARM_LABELS[arm], ARM_COLORS[arm])
    _style(top)
    top.set_title(
        "A. Pooled daily marked equity, k = 0.5 and c = 2 bps",
        loc="left",
        fontsize=11,
        color=INK,
    )
    top.set_ylabel(
        "cumulative return per unit of entry premium", fontsize=9, color=MUTED
    )
    top.legend(frameon=False, fontsize=8.5, loc="upper left", bbox_to_anchor=(0, 0.93))
    top.margins(x=0.06)
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
