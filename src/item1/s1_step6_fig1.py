"""Step 6: figure 1, annual mean log(IV2/RV) by calendar year, both nodes.

Primary version uses the model-free implied variance (6.1); the second version uses the
ATM implied variance (6.2) so the skew contribution is visible side by side.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath, COMMON_START, COMMON_END
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)

log_to("s1_step6_fig1.log")

TICKERS = ["SPX", "GLD", "SLV", "USO", "UNG"]
COLOR = {"SPX": "#111111", "GLD": "#b8860b", "SLV": "#7f7f7f",
         "USO": "#1f4e79", "UNG": "#c0392b"}
MARKER = {"SPX": "o", "GLD": "s", "SLV": "^", "USO": "D", "UNG": "v"}
# Partial years: 2007 is the first ETF listing year and starts in May; 2008 is partial
# with respect to the common window, which opens 2008-12-08; 2025 ends with the feed on
# 2025-08-29.
PARTIAL = {2007, 2008, 2025}
# A cell resting on fewer than this many surviving days is ringed on the figure.
THIN_N = 30
YEARS = list(range(2007, 2026))

p = pd.read_parquet(dpath("premium_daily.parquet"))
p["year"] = p.date.dt.year

tab = (p.groupby(["ticker", "node", "year"])
         .agg(mean_logratio_mf=("logratio_mf", "mean"),
              n_days_mf=("logratio_mf", "count"),
              mean_logratio_atm=("logratio_atm", "mean"),
              n_days_atm=("logratio_atm", "count"),
              mean_diff_mf=("diff_mf", "mean"),
              first_date=("date", "min"), last_date=("date", "max"))
         .reset_index())
tab["partial_year"] = tab.year.isin(PARTIAL)
tab = tab[tab.n_days_mf.gt(0) | tab.n_days_atm.gt(0)]
tab.to_csv(opath("fig1_table.csv"), index=False)
print("wrote %s : %d rows" % (opath("fig1_table.csv"), len(tab)))

print("\n===== figure 1 underlying table: annual mean log(IV2/RV), model-free =====")
piv = tab.pivot_table(index=["node", "year"], columns="ticker", values="mean_logratio_mf")
cnt = tab.pivot_table(index=["node", "year"], columns="ticker", values="n_days_mf")
print(piv.round(4).to_string())
print("\n===== days per cell =====")
print(cnt.fillna(0).astype(int).to_string())


def draw(value_col, count_col, fname_png, fname_svg, title, ylab):
    fig, axes = plt.subplots(2, 1, figsize=(11.5, 9.2), sharex=True)
    for ax, node in zip(axes, [30, 91]):
        ax.axvspan(2008.5, 2024.5, color="#e8eef5", zorder=0,
                   label="_common window years")
        ax.axhline(0, color="#555555", lw=0.9, ls="-", zorder=1)
        for tic in TICKERS:
            s = tab[(tab.ticker == tic) & (tab.node == node)].sort_values("year")
            s = s[s[count_col] > 0]
            if not len(s):
                continue
            ax.plot(s.year, s[value_col], lw=1.6, color=COLOR[tic], zorder=3, alpha=0.9)
            full = s[~s.partial_year]
            part = s[s.partial_year]
            ax.scatter(full.year, full[value_col], s=46, color=COLOR[tic],
                       marker=MARKER[tic], zorder=4, edgecolors="white", linewidths=0.8)
            ax.scatter(part.year, part[value_col], s=46, facecolors="white",
                       edgecolors=COLOR[tic], marker=MARKER[tic], zorder=4, linewidths=1.6,
                       hatch="////")
            # A cell built from very few surviving days is not comparable with a cell
            # built from a full year. Ring it and print the count.
            thin = s[s[count_col] < THIN_N]
            if len(thin):
                ax.scatter(thin.year, thin[value_col], s=230, facecolors="none",
                           edgecolors="#d62728", linewidths=1.5, zorder=5)
                for _, rw in thin.iterrows():
                    ax.annotate("n=%d" % int(rw[count_col]),
                                (rw.year, rw[value_col]),
                                textcoords="offset points", xytext=(9, 9),
                                fontsize=7.5, color="#d62728", zorder=6)
        ax.set_ylabel(ylab)
        ax.set_title("%d-day node" % node, loc="left", fontsize=11)
        ax.grid(alpha=0.25, lw=0.5, zorder=0)
        ax.set_xticks(YEARS)
        ax.set_xlim(2006.5, 2025.5)
    axes[1].set_xlabel("calendar year")
    handles = [Line2D([], [], color=COLOR[t], marker=MARKER[t], lw=1.6,
                      markeredgecolor="white", label=t) for t in TICKERS]
    handles += [
        Line2D([], [], color="#555555", marker="o", lw=0, markerfacecolor="white",
               markeredgecolor="#555555", markeredgewidth=1.6,
               label="partial year (2007, 2008, 2025): open hatched marker"),
        Patch(facecolor="#e8eef5", edgecolor="none",
              label="years fully inside the common window (2009-2024)"),
        Line2D([], [], color="#d62728", marker="o", lw=0, markerfacecolor="none",
               markeredgecolor="#d62728", markeredgewidth=1.5, markersize=11,
               label="cell built from fewer than %d surviving days" % THIN_N),
    ]
    axes[0].legend(handles=handles, frameon=False, fontsize=9, ncol=3,
                   loc="upper center", bbox_to_anchor=(0.5, 1.30))
    fig.suptitle(title, y=0.995, fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(opath(fname_png), dpi=150)
    fig.savefig(opath(fname_svg))
    print("wrote %s and %s" % (opath(fname_png), opath(fname_svg)))
    plt.close(fig)


draw("mean_logratio_mf", "n_days_mf",
     "fig1_annual_logratio.png", "fig1_annual_logratio.svg",
     "Figure 1. Annual mean log(IV$^2$/RV), model-free implied variance (spec 6.1)\n"
     "common window %s to %s; per-ETF full spans shown" % (COMMON_START, COMMON_END),
     "annual mean log(IV$^2$/RV)")

draw("mean_logratio_atm", "n_days_atm",
     "fig1_atm_annual_logratio.png", "fig1_atm_annual_logratio.svg",
     "Figure 1, ATM version. Annual mean log(IV$^2$/RV), ATM implied variance (spec 6.2)\n"
     "the gap against the model-free version is the skew contribution",
     "annual mean log(IV$^2$/RV), ATM")

print("\n===== model-free minus ATM annual mean, by ticker and node (skew contribution) =====")
tab["mf_minus_atm"] = tab.mean_logratio_mf - tab.mean_logratio_atm
sk = tab.groupby(["ticker", "node"]).agg(
    mean_gap=("mf_minus_atm", "mean"), min_gap=("mf_minus_atm", "min"),
    max_gap=("mf_minus_atm", "max"), years=("year", "size"))
print(sk.round(4).to_string())

dump_json("s1_step6_fig1.json", {
    "years_plotted": YEARS, "partial_years": sorted(PARTIAL),
    "table_rows": len(tab),
    "skew_gap": sk.reset_index().to_dict("records"),
    "table": tab.to_dict("records"),
})
