"""Step 4b: the pooled H1 number section 11 needs for the post opening.

Definition fixed in session 2 BEFORE the number was computed:

  Pooled = the equal-weighted average across GLD, SLV, USO and UNG of the daily
  log(IV^2/RV), computed on the ATM series for all four so that one measure covers
  every ETF at full retention. Averaging across ETFs per date first, then running the
  section 7 inference on that single series, carries the cross-sectional dependence
  among the four premia into the standard errors without further assumption.

  The model-free pooled number is reported alongside on the dates where all four
  model-free series exist, with that date count stated.

Outside the eighteen-test family. Labelled as such everywhere it appears.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath
from item1.s2_inference import (hac_mean, boot_mean, grid_mean, SEED, N_DRAWS_DEFAULT)
import numpy as np
import pandas as pd
pd.set_option("display.width", 320); pd.set_option("display.max_rows", 200)

log_to("s2_step4b_pooled.log")
H = {30: 21, 91: 63}
ETFS = ["GLD", "SLV", "USO", "UNG"]

panel = pd.read_parquet(dpath("test_panel.parquet"))
grid = pd.read_parquet(dpath("test_grid.parquet"))
cw = panel[panel.in_common]

print("definition fixed in session 2 before computation: equal-weighted average across")
print("%s of the daily log(IV^2/RV); ATM for all four as the primary pooled measure." % ETFS)
print("seed %d, %d bootstrap draws, same as the family tests" % (SEED, N_DRAWS_DEFAULT))

t_all = time.time()
rows = []
for node in (30, 91):
    h = H[node]
    for series, col in (("atm", "logratio_atm"), ("mf", "logratio_mf")):
        w = (cw[cw.ticker.isin(ETFS) & (cw.node == node)]
             .pivot_table(index="date", columns="ticker", values=col))
        w = w.reindex(columns=ETFS)
        complete = w.dropna(how="any")
        pooled = complete.mean(axis=1)
        gw = (grid[grid.ticker.isin(ETFS) & (grid.node == node)]
              .pivot_table(index="date", columns="ticker", values=col)).reindex(columns=ETFS)
        gpooled = gw.dropna(how="any").mean(axis=1)

        t0 = time.time()
        a = hac_mean(pooled.values, h)
        b = boot_mean(pooled.values, h)
        g = grid_mean(gpooled.values)
        el = time.time() - t0
        rec = {"node": node, "series": series, "in_family": False,
               "n_dates_all_four": int(len(complete)),
               "first_date": str(complete.index.min().date()),
               "last_date": str(complete.index.max().date()),
               "estimate": a["estimate"],
               "NW_se": a["NW"]["se"], "NW_t": a["NW"]["t"], "p_NW": a["NW"]["p_one_sided"],
               "HH_se": a["HH"]["se"], "HH_t": a["HH"]["t"], "p_HH": a["HH"]["p_one_sided"],
               "boot_ci_lo": b["ci_lo"], "boot_ci_hi": b["ci_hi"], "p_BOOT": b["p_one_sided"],
               "n_grid": g["n"], "grid_estimate": g["estimate"], "grid_t": g["t"],
               "p_GRID": g["p_one_sided"],
               "nw_ci_lo": a["estimate"] - 1.96 * a["NW"]["se"],
               "nw_ci_hi": a["estimate"] + 1.96 * a["NW"]["se"],
               "seconds": round(el, 1)}
        rows.append(rec)
        print("\nnode %d, %s series: dates with all four = %d (%s .. %s)"
              % (node, series, rec["n_dates_all_four"], rec["first_date"], rec["last_date"]))
        print("  pooled mean log(IV^2/RV) = %.6f" % rec["estimate"])
        print("  Newey-West   se=%.6f t=%.3f p=%.6g  95%% CI [%.4f, %.4f]"
              % (rec["NW_se"], rec["NW_t"], rec["p_NW"], rec["nw_ci_lo"], rec["nw_ci_hi"]))
        print("  Hansen-Hodrick se=%.6f t=%.3f p=%.6g" % (rec["HH_se"], rec["HH_t"], rec["p_HH"]))
        print("  block bootstrap p=%.4f  95%% CI [%.4f, %.4f]  (%.1fs)"
              % (rec["p_BOOT"], rec["boot_ci_lo"], rec["boot_ci_hi"], el))
        print("  non-overlapping grid n=%d mean=%.6f t=%.3f p=%.6g"
              % (rec["n_grid"], rec["grid_estimate"], rec["grid_t"], rec["p_GRID"]))

R = pd.DataFrame(rows)
total = time.time() - t_all
print("\n===== pooled H1 summary (outside the eighteen-test family) =====")
print(R[["node", "series", "n_dates_all_four", "estimate", "nw_ci_lo", "nw_ci_hi",
         "p_NW", "p_HH", "p_BOOT", "n_grid", "p_GRID"]].round(6).to_string(index=False))
print("\npooled bootstrap wall clock (all four pooled series): %.1f s" % total)

R.to_csv(opath("s2_pooled_h1.csv"), index=False)
dump_json("s2_step4b_pooled.json", {
    "definition": ("equal-weighted average across GLD, SLV, USO, UNG of the daily "
                   "log(IV^2/RV); ATM series for all four as primary; model-free "
                   "alongside on dates where all four model-free series exist"),
    "definition_fixed_before_computation": True,
    "in_family": False, "seed": SEED, "draws": N_DRAWS_DEFAULT,
    "pooled_bootstrap_seconds": round(total, 1),
    "rows": R.to_dict("records")})
