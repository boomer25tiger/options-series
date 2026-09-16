"""Step 4: H1, eight tests. Mean log(IV^2/RV) > 0, one-sided, per ETF per node."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath, COMMON_START, COMMON_END
from item1.s2_inference import (hac_mean, boot_mean, grid_mean, holm, verdict,
                                SEED, N_DRAWS_DEFAULT, ALPHA)
import numpy as np
import pandas as pd
pd.set_option("display.width", 330); pd.set_option("display.max_rows", 300)

log_to("s2_step4_h1.log")
H = {30: 21, 91: 63}
ETFS = ["GLD", "SLV", "USO", "UNG"]
# A3(a) verdicts from session 1b: labelled ETFs take the ATM secondary as headline.
HEADLINE = {"GLD": "atm", "UNG": "atm", "USO": "atm", "SLV": "mf"}

panel = pd.read_parquet(dpath("test_panel.parquet"))
grid = pd.read_parquet(dpath("test_grid.parquet"))
cw = panel[panel.in_common].copy()
cw["logratio_f2"] = np.log(cw.mfiv_floor2 / cw.rv)
grid["logratio_f2"] = np.log(grid.mfiv_floor2 / grid.rv)

print("seed %d, %d bootstrap draws, alpha %.2f" % (SEED, N_DRAWS_DEFAULT, ALPHA))
print("headline series per A3(a): %s" % HEADLINE)

def one(y_daily, y_grid, h, draws=N_DRAWS_DEFAULT):
    a = hac_mean(y_daily, h)
    b = boot_mean(y_daily, h, n_draws=draws)
    g = grid_mean(y_grid)
    return {"n": a["n"], "estimate": a["estimate"],
            "NW": a["NW"], "HH": a["HH"], "BOOT": b, "GRID": g}

t_all = time.time()
results = []
for node in (30, 91):
    h = H[node]
    for tic in ETFS + ["SPX"]:
        d = cw[(cw.ticker == tic) & (cw.node == node)]
        gd = grid[(grid.ticker == tic) & (grid.node == node)]
        for series, col in (("mf", "logratio_mf"), ("atm", "logratio_atm")):
            r = one(d[col].values, gd[col].values, h)
            r.update({"node": node, "ticker": tic, "series": series, "measure": "logratio",
                      "sample": "full", "in_family": tic != "SPX" and series == HEADLINE.get(tic)})
            results.append(r)
        # robustness: April 2020 exclusion
        dx = d[~d.apr2020]; gx = gd[~((gd.date >= "2020-03-01") & (gd.date <= "2020-04-30"))]
        for series, col in (("mf", "logratio_mf"), ("atm", "logratio_atm")):
            r = one(dx[col].values, gx[col].values, h)
            r.update({"node": node, "ticker": tic, "series": series, "measure": "logratio",
                      "sample": "ex-Apr2020", "in_family": False})
            results.append(r)
        # robustness: floor-of-2 model-free series
        r = one(d["logratio_f2"].values, gd["logratio_f2"].values, h)
        r.update({"node": node, "ticker": tic, "series": "mf_floor2", "measure": "logratio",
                  "sample": "full", "in_family": False})
        results.append(r)
        # secondary measure: IV^2 - RV in annualised variance points
        for series, col in (("mf", "diff_mf"), ("atm", "diff_atm")):
            r = one(d[col].values, gd[col].values, h)
            r.update({"node": node, "ticker": tic, "series": series, "measure": "diff",
                      "sample": "full", "in_family": False})
            results.append(r)
        print("  %s node %d done (%.0fs elapsed)" % (tic, node, time.time() - t_all))

R = pd.DataFrame(results)
R["p_NW"] = R.NW.apply(lambda d: d["p_one_sided"])
R["p_HH"] = R.HH.apply(lambda d: d["p_one_sided"])
R["p_BOOT"] = R.BOOT.apply(lambda d: d["p_one_sided"])
R["p_GRID"] = R.GRID.apply(lambda d: d["p_one_sided"])
R["n_grid"] = R.GRID.apply(lambda d: d["n"])

# ---- Holm within each block, on the family members only ----
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

print("\n===== H1: the eight family tests (headline series per A3(a)) =====")
fam = R[R.in_family].sort_values(["node", "ticker"])
print(fam[["node", "ticker", "series", "n", "estimate", "p_NW", "p_HH", "p_BOOT",
           "n_grid", "p_GRID", "holm_level_NW", "reject_NW", "reject_BOOT",
           "verdict"]].round(6).to_string(index=False))

print("\n===== both series side by side, full sample, log ratio =====")
both = R[(R.measure == "logratio") & (R["sample"] == "full") & (R.series.isin(["mf", "atm"]))]
print(both.sort_values(["node", "ticker", "series"])[
    ["node", "ticker", "series", "n", "estimate", "p_NW", "p_HH", "p_BOOT", "p_GRID"]
].round(6).to_string(index=False))

print("\n===== robustness rows =====")
rob = R[(R["sample"] == "ex-Apr2020") | (R.series == "mf_floor2") | (R.measure == "diff")]
print(rob.sort_values(["node", "ticker", "measure", "sample", "series"])[
    ["node", "ticker", "series", "measure", "sample", "n", "estimate", "p_NW", "p_BOOT"]
].round(6).to_string(index=False))

print("\nH1 wall clock: %.1f s (%.1f min)" % (time.time() - t_all, (time.time() - t_all) / 60))
R.to_pickle(opath("s2_h1_raw.pkl"))
dump_json("s2_step4_h1.json", {
    "seed": SEED, "draws": N_DRAWS_DEFAULT, "alpha": ALPHA, "headline": HEADLINE,
    "seconds": round(time.time() - t_all, 1),
    "rows": R.drop(columns=["NW", "HH", "BOOT", "GRID"]).to_dict("records"),
    "detail": [{k: v for k, v in r.items()} for r in results],
})
