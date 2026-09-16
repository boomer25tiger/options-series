"""Figures: annual log variance ratios, the VIX check, the curve-state split, the slope
coefficients and the commonality shares."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from options_series.item1.config import (
    COMMODITY_ETFS,
    COMMON_END,
    COMMON_START,
    NODES,
    STATE_POWER_FLOOR,
    STATE_REPORT_FLOOR,
)

matplotlib.use("Agg")

TICKERS = ("SPX", "GLD", "SLV", "USO", "UNG")
COLORS = {
    "SPX": "#111111",
    "GLD": "#b8860b",
    "SLV": "#7f7f7f",
    "USO": "#1f4e79",
    "UNG": "#c0392b",
    "POOLED": "#111111",
}
MARKERS = {"SPX": "o", "GLD": "s", "SLV": "^", "USO": "D", "UNG": "v"}
CONTANGO_COLOR, BACKWARDATION_COLOR = "#2c7fb8", "#d95f02"
# 2007 opens with the first ETF listings in May, 2008 is partial against a common
# window that opens in December, 2025 ends with the data in August.
PARTIAL_YEARS = {2007, 2008, 2025}
THIN_CELL_DAYS = 30
YEARS = list(range(2007, 2026))


def _save(figure: plt.Figure, path: Path) -> None:
    """Write a figure as PNG and SVG and close it."""
    figure.savefig(path.with_suffix(".png"), dpi=150)
    figure.savefig(path.with_suffix(".svg"))
    plt.close(figure)


def annual_log_ratio_table(premium: pd.DataFrame) -> pd.DataFrame:
    """Annual mean log(IV²/RV) and day counts per ticker, node and calendar year."""
    table = (
        premium.groupby(["ticker", "node", "year"])
        .agg(
            mean_log_ratio_model_free=("log_ratio_model_free", "mean"),
            days_model_free=("log_ratio_model_free", "count"),
            mean_log_ratio_atm=("log_ratio_atm", "mean"),
            days_atm=("log_ratio_atm", "count"),
            mean_var_difference_model_free=("var_difference_model_free", "mean"),
            first_date=("date", "min"),
            last_date=("date", "max"),
        )
        .reset_index()
    )
    table["partial_year"] = table.year.isin(PARTIAL_YEARS)
    return table[(table.days_model_free > 0) | (table.days_atm > 0)]


def _annual_panel(
    axis: Axes, table: pd.DataFrame, node: int, value: str, count: str, ylabel: str
) -> None:
    """Draw one node's annual mean log ratio per ticker, marking partial years and cells
    built from fewer than thirty days."""
    axis.axvspan(2008.5, 2024.5, color="#e8eef5", zorder=0)
    axis.axhline(0, color="#555555", lw=0.9, zorder=1)
    for ticker in TICKERS:
        cells = table[(table.ticker == ticker) & (table.node == node)].sort_values(
            "year"
        )
        cells = cells[cells[count] > 0]
        if not len(cells):
            continue
        axis.plot(
            cells.year, cells[value], lw=1.6, color=COLORS[ticker], zorder=3, alpha=0.9
        )
        full = cells[~cells.partial_year]
        partial = cells[cells.partial_year]
        axis.scatter(
            full.year,
            full[value],
            s=46,
            color=COLORS[ticker],
            marker=MARKERS[ticker],
            zorder=4,
            edgecolors="white",
            linewidths=0.8,
        )
        axis.scatter(
            partial.year,
            partial[value],
            s=46,
            facecolors="white",
            edgecolors=COLORS[ticker],
            marker=MARKERS[ticker],
            zorder=4,
            linewidths=1.6,
            hatch="////",
        )
        thin = cells[cells[count] < THIN_CELL_DAYS]
        axis.scatter(
            thin.year,
            thin[value],
            s=230,
            facecolors="none",
            edgecolors="#d62728",
            linewidths=1.5,
            zorder=5,
        )
        for _, cell in thin.iterrows():
            axis.annotate(
                f"n={int(cell[count])}",
                (cell.year, cell[value]),
                textcoords="offset points",
                xytext=(9, 9),
                fontsize=7.5,
                color="#d62728",
                zorder=6,
            )
    axis.set_ylabel(ylabel)
    axis.grid(alpha=0.25, lw=0.5, zorder=0)
    axis.set_xticks(YEARS)
    axis.set_xlim(2006.5, 2025.5)


def _annual_legend() -> list:
    """Legend entries shared by the annual figures."""
    handles = [
        Line2D(
            [],
            [],
            color=COLORS[ticker],
            marker=MARKERS[ticker],
            lw=1.6,
            markeredgecolor="white",
            label=ticker,
        )
        for ticker in TICKERS
    ]
    handles += [
        Line2D(
            [],
            [],
            color="#555555",
            marker="o",
            lw=0,
            markerfacecolor="white",
            markeredgecolor="#555555",
            markeredgewidth=1.6,
            label="partial year (2007, 2008, 2025): open hatched marker",
        ),
        Patch(
            facecolor="#e8eef5",
            edgecolor="none",
            label="years fully inside the common window (2009-2024)",
        ),
        Line2D(
            [],
            [],
            color="#d62728",
            marker="o",
            lw=0,
            markerfacecolor="none",
            markeredgecolor="#d62728",
            markeredgewidth=1.5,
            markersize=11,
            label=f"cell built from fewer than {THIN_CELL_DAYS} surviving days",
        ),
    ]
    return handles


def plot_annual_log_ratio(table: pd.DataFrame, series: str, path: Path) -> None:
    """Figure 1: annual mean log(IV²/RV) per ticker, one panel per node."""
    value = f"mean_log_ratio_{series}"
    count = f"days_{series}"
    label = "model-free" if series == "model_free" else "at-the-money"
    figure, axes = plt.subplots(2, 1, figsize=(11.5, 9.2), sharex=True)
    for axis, node in zip(axes, NODES):
        _annual_panel(axis, table, node, value, count, "annual mean log(IV$^2$/RV)")
        axis.set_title(f"{node}-day node", loc="left", fontsize=11)
    axes[1].set_xlabel("calendar year")
    axes[0].legend(
        handles=_annual_legend(),
        frameon=False,
        fontsize=9,
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.30),
    )
    figure.suptitle(
        f"Figure 1. Annual mean log(IV$^2$/RV), {label} implied variance\n"
        f"common window {COMMON_START} to {COMMON_END}; per-ETF full spans shown",
        y=0.995,
        fontsize=12,
    )
    figure.tight_layout(rect=[0, 0, 1, 0.94])
    _save(figure, path)


def plot_headline_annual_log_ratio(table: pd.DataFrame, path: Path) -> None:
    """The 30-day panel of figure 1 on the model-free series, as a single figure."""
    figure, axis = plt.subplots(figsize=(11.5, 6.0))
    figure.subplots_adjust(left=0.07, right=0.98, bottom=0.10, top=0.80)
    _annual_panel(
        axis,
        table,
        30,
        "mean_log_ratio_model_free",
        "days_model_free",
        "annual mean log(IV$^2$/RV)",
    )
    axis.set_xlabel("calendar year")
    figure.suptitle(
        "Annual mean log(IV$^2$/RV), 30-day maturity, model-free implied variance",
        y=0.975,
        fontsize=12,
    )
    figure.legend(
        handles=_annual_legend(),
        frameon=False,
        fontsize=9,
        ncol=4,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.935),
    )
    _save(figure, path)


def plot_vix_check(series: pd.DataFrame, correlation: float, path: Path) -> None:
    """SPX 30-day model-free volatility against the VIX close: scatter and overlay."""
    figure, (scatter, overlay) = plt.subplots(1, 2, figsize=(13, 5.2))
    scatter.scatter(
        series.vix,
        series.model_free_vol,
        s=3,
        alpha=0.25,
        color="#1f4e79",
        edgecolors="none",
    )
    limit = [0, max(series.vix.max(), series.model_free_vol.max()) * 1.05]
    scatter.plot(limit, limit, color="#c00000", lw=1, ls="--", label="45 degrees")
    scatter.set_xlim(limit)
    scatter.set_ylim(limit)
    scatter.set_xlabel("VIX close (vol points)")
    scatter.set_ylabel("SPX 30-day model-free volatility (vol points)")
    scatter.set_title(f"Levels, n = {len(series)}, corr = {correlation:.4f}")
    scatter.legend(frameon=False, fontsize=9)
    scatter.grid(alpha=0.25, lw=0.5)
    overlay.plot(series.date, series.vix, lw=0.7, color="#c00000", label="VIX close")
    overlay.plot(
        series.date,
        series.model_free_vol,
        lw=0.7,
        color="#1f4e79",
        alpha=0.8,
        label="model-free 30-day",
    )
    overlay.set_ylabel("vol points")
    overlay.set_title(
        f"Overlay, {series.date.min().date()} to {series.date.max().date()}"
    )
    overlay.legend(frameon=False, fontsize=9)
    overlay.grid(alpha=0.25, lw=0.5)
    figure.suptitle("SPX model-free 30-day volatility against VIX", y=0.99)
    figure.tight_layout()
    _save(figure, path)


def plot_curve_state_split(split: pd.DataFrame, path: Path) -> None:
    """Figure 2: mean log ratio by curve state per ETF, two panels by node."""
    figure, axes = plt.subplots(2, 1, figsize=(11, 8.6), sharex=True)
    positions = np.arange(len(COMMODITY_ETFS))
    width = 0.34
    for axis, node in zip(axes, NODES):
        axis.margins(y=0.16)
        at_node = split[split.node == node]
        for offset, (state, color) in enumerate(
            (("contango", CONTANGO_COLOR), ("backwardation", BACKWARDATION_COLOR))
        ):
            cells = (
                at_node[at_node.state == state]
                .set_index("ticker")
                .reindex(COMMODITY_ETFS)
            )
            bar_positions = positions + (offset - 0.5) * width
            means = cells.mean_log_ratio.values
            axis.bar(
                bar_positions,
                means,
                width,
                color=color,
                alpha=0.85,
                zorder=3,
                edgecolor="white",
                linewidth=0.8,
            )
            axis.errorbar(
                bar_positions,
                means,
                yerr=[means - cells.ci_low.values, cells.ci_high.values - means],
                fmt="none",
                ecolor="#222222",
                elinewidth=1.1,
                capsize=3,
                zorder=4,
            )
            for position, mean, windows, status, high in zip(
                bar_positions,
                means,
                cells.windows.values,
                cells.status.values,
                cells.ci_high.values,
            ):
                if status.startswith("at or above"):
                    mark = ""
                elif status.startswith("underpowered"):
                    mark = " !"
                else:
                    mark = " !!"
                axis.annotate(
                    f"n={windows}{mark}",
                    (position, np.nanmax([mean, high, 0.0])),
                    textcoords="offset points",
                    xytext=(0, 6),
                    ha="center",
                    fontsize=7.5,
                    color="#c00000" if mark else "#444444",
                )
        axis.axhline(0, color="#555555", lw=0.9, zorder=2)
        axis.set_xticks(positions)
        axis.set_xticklabels(COMMODITY_ETFS)
        axis.set_ylabel("mean log(IV$^2$/RV)")
        axis.set_title(f"{node}-day node", loc="left", fontsize=11)
        axis.grid(alpha=0.25, lw=0.5, axis="y", zorder=0)
    axes[0].legend(
        handles=[
            Patch(facecolor=CONTANGO_COLOR, label="contango"),
            Patch(facecolor=BACKWARDATION_COLOR, label="backwardation"),
            Line2D(
                [], [], color="#222222", lw=1.1, label="block-bootstrap 95% interval"
            ),
            Line2D(
                [],
                [],
                color="#c00000",
                lw=0,
                marker="$!$",
                label=f"! under {STATE_POWER_FLOOR} windows, !! under {STATE_REPORT_FLOOR}",
            ),
        ],
        frameon=False,
        fontsize=8.5,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.30),
    )
    figure.suptitle(
        "Figure 2. Mean log(IV$^2$/RV) by futures-curve state, headline series\n"
        "n is the count of non-overlapping windows; no test is run on the split",
        y=0.995,
        fontsize=11.5,
    )
    figure.tight_layout(rect=[0, 0, 1, 0.92])
    _save(figure, path)


def plot_slope_coefficients(scaled: pd.DataFrame, path: Path) -> None:
    """Figure 3: slope per standard deviation of the curve slope with Newey-West and
    bootstrap intervals, two panels by node."""
    units = [*COMMODITY_ETFS, "POOLED"]
    figure, axes = plt.subplots(1, 2, figsize=(12.5, 5.6), sharey=True)
    for axis, node in zip(axes, NODES):
        at_node = scaled[scaled.node == node].set_index("unit").reindex(units)
        for index, unit in enumerate(units):
            row = at_node.loc[unit]
            color = COLORS[unit]
            axis.plot(
                [index - 0.15, index - 0.15],
                [row.nw_low_per_sd, row.nw_high_per_sd],
                color=color,
                lw=3.0,
                solid_capstyle="round",
            )
            axis.plot(
                [index + 0.15, index + 0.15],
                [row.boot_low_per_sd, row.boot_high_per_sd],
                color=color,
                lw=3.0,
                alpha=0.42,
                solid_capstyle="round",
            )
            axis.plot(
                index,
                row.estimate_per_sd,
                "o",
                color=color,
                ms=7.5,
                markeredgecolor="white",
                zorder=5,
            )
            axis.annotate(
                f"{row.estimate_per_sd:+.3f}",
                (index, row.estimate_per_sd),
                textcoords="offset points",
                xytext=(0, 12),
                ha="center",
                fontsize=8,
                color=color,
            )
        axis.axhline(0, color="#555555", lw=1.0)
        axis.set_xticks(np.arange(len(units)))
        axis.set_xticklabels(units)
        axis.set_title(f"{node}-day node", loc="left", fontsize=11)
        axis.grid(alpha=0.25, lw=0.5, axis="y")
        axis.set_xlim(-0.6, len(units) - 0.4)
    axes[0].set_ylabel("change in log(IV$^2$/RV) per 1 sd of $z_t$")
    axes[1].legend(
        handles=[
            Line2D([], [], color="#444444", lw=3.0, label="Newey-West 95%"),
            Line2D(
                [], [], color="#444444", lw=3.0, alpha=0.42, label="block-bootstrap 95%"
            ),
        ],
        frameon=False,
        fontsize=9,
        loc="upper right",
    )
    figure.suptitle(
        "Figure 3. Slope of log(IV$^2$/RV) on the curve slope, per standard deviation of "
        "each commodity's own $z_t$\nheadline series; the rescaling leaves every t "
        "statistic and p value unchanged",
        y=0.99,
        fontsize=11.5,
    )
    figure.tight_layout(rect=[0, 0, 1, 0.90])
    _save(figure, path)


def plot_commonality(
    shares: dict[tuple[int, str], dict[str, object]], path: Path
) -> None:
    """Figure 4: first-component share before and after conditioning on own curve slope."""
    labels, before, after = [], [], []
    for node in NODES:
        for series in ("model_free", "atm"):
            result = shares[(node, series)]
            labels.append(
                f"{node}-day\n{'model-free' if series == 'model_free' else 'ATM'}"
            )
            before.append(result["share_before"])
            after.append(result["share_after"])
    positions = np.arange(len(labels))
    width = 0.36
    figure, axis = plt.subplots(figsize=(9.2, 5.2))
    axis.bar(
        positions - width / 2,
        before,
        width,
        color="#1f4e79",
        label="before conditioning on $z_t$",
        zorder=3,
    )
    axis.bar(
        positions + width / 2,
        after,
        width,
        color="#7fb3d5",
        label="after residualising on own $z_t$",
        zorder=3,
    )
    for position, share_before, share_after in zip(positions, before, after):
        axis.annotate(
            f"{share_before:.4f}",
            (position - width / 2, share_before),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=8,
        )
        axis.annotate(
            f"{share_after:.4f}",
            (position + width / 2, share_after),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=8,
        )
        axis.annotate(
            f"{share_after - share_before:+.4f}",
            (position, max(share_before, share_after)),
            textcoords="offset points",
            xytext=(0, 18),
            ha="center",
            fontsize=8.5,
            color="#c00000",
        )
    axis.axhline(0.25, color="#999999", ls="--", lw=1)
    axis.annotate(
        "0.25 = four uncorrelated series",
        (len(labels) - 0.5, 0.255),
        ha="right",
        fontsize=8,
        color="#777777",
    )
    axis.set_xticks(positions)
    axis.set_xticklabels(labels)
    axis.set_ylabel("share of variance in the first principal component")
    axis.set_ylim(0, 0.75)
    axis.legend(frameon=False, fontsize=9)
    axis.grid(alpha=0.25, lw=0.5, axis="y", zorder=0)
    axis.set_title(
        "Figure 4. Commonality across the four commodity variance premia\n"
        "first-component share of the pairwise-complete correlation matrix, four series",
        loc="left",
        fontsize=11.5,
    )
    figure.tight_layout()
    _save(figure, path)
