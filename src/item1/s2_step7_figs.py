"""Step 7: figures 2, 3 and 4."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, load_json, dpath, opath
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

log_to("s2_step7_figs.log")
ETFS = ["GLD", "SLV", "USO", "UNG"]
COLOR = {"GLD": "#b8860b", "SLV": "#7f7f7f", "USO": "#1f4e79", "UNG": "#c0392b",
         "POOLED": "#111111"}
CONT, BACK = "#2c7fb8", "#d95f02"

S = pd.read_csv(opath("s2_sign_split.csv"))
H2 = pd.read_pickle(opath("s2_h2_raw.pkl"))
Q3 = load_json("s2_step6_q3.json")

# ------------------------------------------------- figure 2, sign split ---
fig, axes = plt.subplots(2, 1, figsize=(11, 8.6), sharex=True)
for ax, node in zip(axes, (30, 91)):
    d = S[S.node == node]
    ax.margins(y=0.16)
    xs = np.arange(len(ETFS)); w = 0.34
    for k, (st, col) in enumerate((("contango", CONT), ("backwardation", BACK))):
        sub = d[d.state == st].set_index("ticker").reindex(ETFS)
        pos = xs + (k - 0.5) * w
        ax.bar(pos, sub["mean"].values, w, color=col, alpha=0.85, zorder=3,
               edgecolor="white", linewidth=0.8)
        ax.errorbar(pos, sub["mean"].values,
                    yerr=[sub["mean"].values - sub.ci_lo.values,
                          sub.ci_hi.values - sub["mean"].values],
                    fmt="none", ecolor="#222222", elinewidth=1.1, capsize=3, zorder=4)
        for x, m, n, p, hi in zip(pos, sub["mean"].values, sub.n_windows.values,
                                  sub.power.values, sub.ci_hi.values):
            if not np.isfinite(m):
                continue
            mark = "" if str(p).startswith("at or above") else (
                " !" if "underpowered" in str(p) else " !!")
            top = np.nanmax([m, hi, 0.0])
            ax.annotate("n=%d%s" % (n, mark), (x, top), textcoords="offset points",
                        xytext=(0, 6), ha="center", fontsize=7.5,
                        color="#444444" if not mark else "#c00000")
    ax.axhline(0, color="#555555", lw=0.9, zorder=2)
    ax.set_xticks(xs); ax.set_xticklabels(ETFS)
    ax.set_ylabel("mean log(IV$^2$/RV)")
    ax.set_title("%d-day node" % node, loc="left", fontsize=11)
    ax.grid(alpha=0.25, lw=0.5, axis="y", zorder=0)
axes[0].legend(handles=[Patch(facecolor=CONT, label="contango"),
                        Patch(facecolor=BACK, label="backwardation"),
                        Line2D([], [], color="#222222", lw=1.1, label="block-bootstrap 95% interval"),
                        Line2D([], [], color="#c00000", lw=0, marker="$!$",
                               label="! under 64 windows, !! under 30 (section 5 floor)")],
               frameon=False, fontsize=8.5, ncol=2, loc="upper center",
               bbox_to_anchor=(0.5, 1.30))
fig.suptitle("Figure 2. Mean log(IV$^2$/RV) by futures-curve state, headline series per A3(a)\n"
             "n is the count of non-overlapping windows; no test is run on the split",
             y=0.995, fontsize=11.5)
fig.tight_layout(rect=[0, 0, 1, 0.92])
fig.savefig(opath("fig2_sign_split.png"), dpi=150); fig.savefig(opath("fig2_sign_split.svg"))
plt.close(fig)
print("wrote fig2_sign_split.png/.svg")

# ------------------------------------------- figure 3, H2 coefficients ---
# The raw slope is not comparable across commodities: z_t for gold and silver is an
# order of magnitude smaller than for crude and natural gas, so the raw coefficients
# span three orders of magnitude. The figure plots the coefficient scaled to a
# one-standard-deviation move in that commodity's own z_t. This is a pure rescaling:
# every t statistic and p value in the tables is unchanged by it.
panel = pd.read_parquet(dpath("test_panel.parquet"))
cw = panel[panel.in_common]
COLMAP = {"GLD": "logratio_atm", "UNG": "logratio_atm", "USO": "logratio_atm",
          "SLV": "logratio_mf"}
SD = {}
for node in (30, 91):
    for tic in ETFS:
        d = cw[(cw.ticker == tic) & (cw.node == node)][[COLMAP[tic], "z_t"]].dropna()
        SD[(node, tic)] = float(d.z_t.std(ddof=1))
    parts = []
    for tic in ETFS:
        d = cw[(cw.ticker == tic) & (cw.node == node)][[COLMAP[tic], "z_t"]].dropna()
        parts.append(d.z_t - d.z_t.mean())
    SD[(node, "POOLED")] = float(pd.concat(parts).std(ddof=1))

fam = H2[H2.in_family].copy()
fam["sd_z"] = fam.apply(lambda r: SD[(r.node, r.unit)], axis=1)
fam["est_sd"] = fam.estimate * fam.sd_z
fam["nw_lo"] = fam.apply(lambda r: (r.estimate - 1.96 * r.NW["se"]) * r.sd_z, axis=1)
fam["nw_hi"] = fam.apply(lambda r: (r.estimate + 1.96 * r.NW["se"]) * r.sd_z, axis=1)
fam["bt_lo"] = fam.apply(lambda r: r.BOOT["ci_lo"] * r.sd_z, axis=1)
fam["bt_hi"] = fam.apply(lambda r: r.BOOT["ci_hi"] * r.sd_z, axis=1)
fam[["node", "unit", "series", "estimate", "sd_z", "est_sd", "nw_lo", "nw_hi",
     "bt_lo", "bt_hi", "p_NW", "p_BOOT", "verdict"]].to_csv(
    opath("fig3_table.csv"), index=False)

UNITS = ETFS + ["POOLED"]
fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.6), sharey=True)
for ax, node in zip(axes, (30, 91)):
    d = fam[fam.node == node].set_index("unit").reindex(UNITS)
    xs = np.arange(len(UNITS))
    for i, u in enumerate(UNITS):
        r = d.loc[u]; c = COLOR[u]
        ax.plot([i - 0.15, i - 0.15], [r.nw_lo, r.nw_hi], color=c, lw=3.0,
                solid_capstyle="round")
        ax.plot([i + 0.15, i + 0.15], [r.bt_lo, r.bt_hi], color=c, lw=3.0, alpha=0.42,
                solid_capstyle="round")
        ax.plot(i, r.est_sd, "o", color=c, ms=7.5, markeredgecolor="white", zorder=5)
        ax.annotate("%+.3f" % r.est_sd, (i, r.est_sd), textcoords="offset points",
                    xytext=(0, 12), ha="center", fontsize=8, color=c)
    ax.axhline(0, color="#555555", lw=1.0)
    ax.set_xticks(xs); ax.set_xticklabels(UNITS)
    ax.set_title("%d-day node" % node, loc="left", fontsize=11)
    ax.grid(alpha=0.25, lw=0.5, axis="y")
    ax.set_xlim(-0.6, len(UNITS) - 0.4)
axes[0].set_ylabel("change in log(IV$^2$/RV) per 1 sd of $z_t$")
axes[1].legend(handles=[Line2D([], [], color="#444444", lw=3.0, label="Newey-West 95%"),
                        Line2D([], [], color="#444444", lw=3.0, alpha=0.42,
                               label="block-bootstrap 95%")],
               frameon=False, fontsize=9, loc="upper right")
fig.suptitle("Figure 3. H2 slope coefficients, scaled to a one-standard-deviation move in "
             "each commodity's own $z_t$\nheadline series per A3(a); the rescaling leaves "
             "every t statistic and p value unchanged", y=0.99, fontsize=11.5)
fig.tight_layout(rect=[0, 0, 1, 0.90])
fig.savefig(opath("fig3_slope_coefficients.png"), dpi=150)
fig.savefig(opath("fig3_slope_coefficients.svg"))
plt.close(fig)
print("wrote fig3_slope_coefficients.png/.svg")

# --------------------------------------------- figure 4, commonality ---
fig, ax = plt.subplots(figsize=(9.2, 5.2))
labs, before, after = [], [], []
for node in (30, 91):
    for series in ("mf", "atm"):
        r = Q3["nodes"][str(node)][series]
        labs.append("%d-day\n%s" % (node, "model-free" if series == "mf" else "ATM"))
        before.append(r["share_before"]); after.append(r["share_after"])
xs = np.arange(len(labs)); w = 0.36
ax.bar(xs - w / 2, before, w, color="#1f4e79", label="before conditioning on $z_t$", zorder=3)
ax.bar(xs + w / 2, after, w, color="#7fb3d5", label="after residualising on own $z_t$", zorder=3)
for x, b, a in zip(xs, before, after):
    ax.annotate("%.4f" % b, (x - w / 2, b), textcoords="offset points", xytext=(0, 4),
                ha="center", fontsize=8)
    ax.annotate("%.4f" % a, (x + w / 2, a), textcoords="offset points", xytext=(0, 4),
                ha="center", fontsize=8)
    ax.annotate("%+.4f" % (a - b), (x, max(b, a)), textcoords="offset points", xytext=(0, 18),
                ha="center", fontsize=8.5, color="#c00000")
ax.axhline(0.25, color="#999999", ls="--", lw=1)
ax.annotate("0.25 = four uncorrelated series", (len(labs) - 0.5, 0.255), ha="right",
            fontsize=8, color="#777777")
ax.set_xticks(xs); ax.set_xticklabels(labs)
ax.set_ylabel("share of variance in the first principal component")
ax.set_ylim(0, 0.75)
ax.legend(frameon=False, fontsize=9)
ax.grid(alpha=0.25, lw=0.5, axis="y", zorder=0)
ax.set_title("Figure 4. Commonality across the four commodity variance premia (Q3)\n"
             "first-component share of the pairwise-complete correlation matrix, four series",
             loc="left", fontsize=11.5)
fig.tight_layout()
fig.savefig(opath("fig4_commonality.png"), dpi=150); fig.savefig(opath("fig4_commonality.svg"))
plt.close(fig)
print("wrote fig4_commonality.png/.svg")
