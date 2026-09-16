"""Step 3d: diagnostic on multi-deliverable expiries (a construction defect).

Some ETF expiries carry TWO deliverable chains under the same exdate and the same
am_settlement: the standard chain and a split-adjusted chain. UNG on 2011-03-21 is the
clearest case - the close was 11.105 with cfadj 0.5, and the same exdate carries a call
struck at 5 quoted 6.05/6.15 (consistent with an underlying of 11.1) and another call
struck at 5 quoted 0.58/0.60 (consistent with an underlying of 5.55).

CHOICE 2 in mfiv.py resolves duplicate (exdate, am_settlement, cp_flag, strike) rows by
open interest. On these expiries that splices the two chains into one strike ladder and
the section 6.1 sum is then taken across two different securities.

This script MEASURES the extent of the problem. It does not change the construction:
per the session instruction nothing here changes the spec, and the pre-registered
step-4 stop rule passed. The fix is proposed as an amendment in the report.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath, PULL_SPAN
import numpy as np
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)

log_to("s1_step3d_multichain_diag.log")

rows = []
for tic in ["SPX", "GLD", "SLV", "USO", "UNG"]:
    a, b = PULL_SPAN[tic]
    for yr in range(int(a[:4]), int(b[:4]) + 1):
        fn = dpath("opprcd_%s_%d.parquet" % (tic, yr))
        if not os.path.exists(fn):
            continue
        q = pd.read_parquet(fn)
        q["dup"] = q.duplicated(["date", "exdate", "am_settlement", "cp_flag",
                                 "strike_price"], keep=False)
        per = q.groupby("date")["dup"].any()
        rows.append(pd.DataFrame({"ticker": tic, "year": yr,
                                  "date": per.index, "multi_chain": per.values}))
mc = pd.concat(rows, ignore_index=True)
mc.to_parquet(dpath("multichain_flag.parquet"), index=False)

print("===== secid-dates whose quote set contains a duplicated "
      "(exdate, am_settlement, cp_flag, strike) =====")
t = mc.groupby("ticker").agg(dates=("multi_chain", "size"), affected=("multi_chain", "sum"))
t["share"] = (t.affected / t.dates).round(4)
print(t.to_string())

print("\n===== affected dates by ticker and year =====")
ty = mc[mc.multi_chain].groupby(["ticker", "year"]).size().rename("affected_dates")
print(ty.to_string())
ty.reset_index().to_csv(opath("s1_step3_multichain_by_year.csv"), index=False)

p = pd.read_parquet(dpath("premium_daily.parquet"))
m = p.merge(mc[["ticker", "date", "multi_chain"]], on=["ticker", "date"], how="left")
m["ivol"] = np.sqrt(m.mfiv) * 100.0
ok = m[m.drop_code == "OK"]

print("\n===== implied vol of surviving rows, split by the flag =====")
g = ok.groupby(["ticker", "node", "multi_chain"]).agg(
    n=("ivol", "size"), median=("ivol", "median"),
    p95=("ivol", lambda s: s.quantile(0.95)), max=("ivol", "max"),
    share_over_100=("ivol", lambda s: float((s > 100).mean())))
print(g.round(3).to_string())
g.reset_index().to_csv(opath("s1_step3_multichain_ivol.csv"), index=False)

print("\n===== surviving rows above 100 vol points =====")
hi = ok[ok.ivol > 100]
h = hi.groupby(["ticker", "node"]).agg(n=("ivol", "size"),
                                       multi_chain_share=("multi_chain", "mean"))
print(h.round(3).to_string() if len(h) else "(none)")

print("\n===== how much of each annual figure-1 cell rests on flagged dates =====")
cell = ok.groupby(["ticker", "node", "year"]).agg(
    n=("logratio_mf", "count"), mean_mf=("logratio_mf", "mean"),
    flagged_share=("multi_chain", "mean"))
worst = cell[(cell.flagged_share > 0) & (cell.n > 0)].sort_values("flagged_share",
                                                                 ascending=False)
print(worst.round(4).head(30).to_string())
cell.reset_index().to_csv(opath("s1_step3_cell_flagged_share.csv"), index=False)

print("\n===== figure-1 cells resting on fewer than 30 days =====")
thin = cell[cell.n < 30]
print(thin.round(4).to_string() if len(thin) else "(none)")

dump_json("s1_step3d_multichain_diag.json", {
    "by_ticker": t.reset_index().to_dict("records"),
    "by_ticker_year": ty.reset_index().to_dict("records"),
    "ivol_split": g.reset_index().to_dict("records"),
    "thin_cells": thin.reset_index().to_dict("records"),
})
