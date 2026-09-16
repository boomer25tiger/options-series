"""Step 5: H2, ten tests. Slope of log(IV^2/RV) on z_t, two-sided, per ETF and pooled."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath
from item1.s2_inference import (hac_slope, boot_slope, boot_slope_panel, grid_slope,
                                boot_mean, holm, verdict, SEED, N_DRAWS_DEFAULT, ALPHA)
import numpy as np
import pandas as pd
pd.set_option("display.width", 340); pd.set_option("display.max_rows", 300)

log_to("s2_step5_h2.log")
H = {30: 21, 91: 63}
ETFS = ["GLD", "SLV", "USO", "UNG"]
HEADLINE = {"GLD": "atm", "UNG": "atm", "USO": "atm", "SLV": "mf"}
COL = {"mf": "logratio_mf", "atm": "logratio_atm"}
POWER_FLOOR = 64      # section 5
REPORT_FLOOR = 30     # section 5

panel = pd.read_parquet(dpath("test_panel.parquet"))
grid = pd.read_parquet(dpath("test_grid.parquet"))
cw = panel[panel.in_common].copy()

t_all = time.time()
rows = []
for node in (30, 91):
    h = H[node]
    # ---- per ETF ----
    for tic in ETFS:
        col = COL[HEADLINE[tic]]
        d = cw[(cw.ticker == tic) & (cw.node == node)]
        gd = grid[(grid.ticker == tic) & (grid.node == node)]
        for smp, dd, gg in (("full", d, gd),
                            ("ex-Apr2020", d[~d.apr2020],
                             gd[~((gd.date >= "2020-03-01") & (gd.date <= "2020-04-30"))])):
            a = hac_slope(dd[col].values, dd.z_t.values, h)
            b = boot_slope(dd[col].values, dd.z_t.values, h)
            g = grid_slope(gg[col].values, gg.z_t.values)
            rows.append({"node": node, "unit": tic, "series": HEADLINE[tic], "sample": smp,
                         "n": a["n"], "estimate": a["estimate"],
                         "NW": a["NW"], "HH": a["HH"], "BOOT": b, "GRID": g,
                         "in_family": smp == "full",
                         "z_first": str(dd.loc[dd.z_t.notna(), "date"].min().date()),
                         "z_last": str(dd.loc[dd.z_t.notna(), "date"].max().date())})
        print("  %s node %d done (%.0fs)" % (tic, node, time.time() - t_all))
    # ---- pooled, within-ETF demeaned ----
    for smp in ("full", "ex-Apr2020"):
        parts, gparts = [], []
        for tic in ETFS:
            col = COL[HEADLINE[tic]]
            d = cw[(cw.ticker == tic) & (cw.node == node)][["date", col, "z_t", "apr2020"]]
            d = d.rename(columns={col: "y"}).dropna(subset=["y", "z_t"])
            g = grid[(grid.ticker == tic) & (grid.node == node)][["date", col, "z_t"]]
            g = g.rename(columns={col: "y"}).dropna(subset=["y", "z_t"])
            if smp == "ex-Apr2020":
                d = d[~d.apr2020]
                g = g[~((g.date >= "2020-03-01") & (g.date <= "2020-04-30"))]
            d = d.assign(y=d.y - d.y.mean(), z_t=d.z_t - d.z_t.mean(), ticker=tic)
            g = g.assign(y=g.y - g.y.mean(), z_t=g.z_t - g.z_t.mean(), ticker=tic)
            parts.append(d); gparts.append(g)
        P = pd.concat(parts, ignore_index=True).sort_values(["date", "ticker"])
        G = pd.concat(gparts, ignore_index=True)
        a = hac_slope(P.y.values, P.z_t.values, h)
        b = boot_slope_panel(P, h, "y", "z_t")
        g = grid_slope(G.y.values, G.z_t.values)
        rows.append({"node": node, "unit": "POOLED", "series": "headline mix",
                     "sample": smp, "n": a["n"], "estimate": a["estimate"],
                     "NW": a["NW"], "HH": a["HH"], "BOOT": b, "GRID": g,
                     "in_family": smp == "full", "z_first": "", "z_last": ""})
        print("  POOLED node %d %s done (%.0fs)" % (node, smp, time.time() - t_all))

R = pd.DataFrame(rows)
R["p_NW"] = R.NW.apply(lambda d: d["p_two_sided"])
R["p_HH"] = R.HH.apply(lambda d: d["p_two_sided"])
R["p_BOOT"] = R.BOOT.apply(lambda d: d["p_two_sided"])
R["p_GRID"] = R.GRID.apply(lambda d: d["p_two_sided"])
R["n_grid"] = R.GRID.apply(lambda d: d["n"])

R["holm_level_NW"] = np.nan; R["holm_level_BOOT"] = np.nan
R["reject_NW"] = False; R["reject_BOOT"] = False; R["verdict"] = ""
for node in (30, 91):
    m = (R.node == node) & R.in_family
    idx = R.index[m]
    lv_nw, rj_nw = holm(R.loc[idx, "p_NW"].values, ALPHA)
    lv_bt, rj_bt = holm(R.loc[idx, "p_BOOT"].values, ALPHA)
    R.loc[idx, "holm_level_NW"] = lv_nw; R.loc[idx, "reject_NW"] = rj_nw
    R.loc[idx, "holm_level_BOOT"] = lv_bt; R.loc[idx, "reject_BOOT"] = rj_bt
    R.loc[idx, "verdict"] = [verdict(a, b) for a, b in zip(rj_nw, rj_bt)]

print("\n===== H2: the ten family tests =====")
fam = R[R.in_family].sort_values(["node", "unit"])
print(fam[["node", "unit", "series", "n", "estimate", "p_NW", "p_HH", "p_BOOT", "n_grid",
           "p_GRID", "holm_level_NW", "reject_NW", "reject_BOOT", "verdict"]]
      .round(6).to_string(index=False))
print("\ngold and silver z_t sample span (A5 disclosure):")
print(fam[fam.unit.isin(["GLD", "SLV"])][["node", "unit", "z_first", "z_last"]].to_string(index=False))

print("\n===== H2 April 2020 exclusion rows =====")
ex = R[~R.in_family].sort_values(["node", "unit"])
print(ex[["node", "unit", "series", "n", "estimate", "p_NW", "p_HH", "p_BOOT", "p_GRID"]]
      .round(6).to_string(index=False))

# ---------------- sign split for figure 2 ----------------
print("\n===== sign split: mean log ratio by curve state (no test) =====")
split = []
for node in (30, 91):
    h = H[node]
    for tic in ETFS:
        col = COL[HEADLINE[tic]]
        d = cw[(cw.ticker == tic) & (cw.node == node)]
        gd = grid[(grid.ticker == tic) & (grid.node == node)]
        for st in ("contango", "backwardation"):
            y = d.loc[d.s_t == st, col].dropna().values
            ng = int(gd.loc[(gd.s_t == st) & gd[col].notna()].shape[0])
            if len(y) < 3:
                split.append({"node": node, "ticker": tic, "state": st, "n_daily": len(y),
                              "n_windows": ng, "mean": np.nan, "ci_lo": np.nan,
                              "ci_hi": np.nan, "power": "not reported"})
                continue
            b = boot_mean(y, h)
            if ng < REPORT_FLOOR:
                power = "reported, not tested (under %d windows)" % REPORT_FLOOR
            elif ng < POWER_FLOOR:
                power = "underpowered (%d to %d windows)" % (REPORT_FLOOR, POWER_FLOOR - 1)
            else:
                power = "at or above the %d-window power threshold" % POWER_FLOOR
            split.append({"node": node, "ticker": tic, "state": st, "n_daily": len(y),
                          "n_windows": ng, "mean": float(y.mean()),
                          "ci_lo": b["ci_lo"], "ci_hi": b["ci_hi"], "power": power})
S = pd.DataFrame(split)
print(S.round(4).to_string(index=False))
print("\nNo test is run on the split; it is nested in H2 per section 3.")
print("\nH2 wall clock: %.1f s (%.1f min)" % (time.time() - t_all, (time.time() - t_all) / 60))

R.to_pickle(opath("s2_h2_raw.pkl"))
S.to_csv(opath("s2_sign_split.csv"), index=False)
dump_json("s2_step5_h2.json", {
    "seed": SEED, "draws": N_DRAWS_DEFAULT, "alpha": ALPHA,
    "power_floor": POWER_FLOOR, "report_floor": REPORT_FLOOR,
    "seconds": round(time.time() - t_all, 1),
    "rows": R.drop(columns=["NW", "HH", "BOOT", "GRID"]).to_dict("records"),
    "detail": rows, "sign_split": S.to_dict("records")})
