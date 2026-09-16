"""Step 2f: retention and mean log ratio before and after A1, and the sub-30-day cells."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath, COMMON_START, COMMON_END
import numpy as np
import pandas as pd
pd.set_option("display.width", 300); pd.set_option("display.max_rows", 300)

log_to("s1b_step2f_compare.log")

rv = pd.read_parquet(dpath("premium_daily.parquet"))[["ticker", "date", "node", "rv"]]

def summarise(fn, label):
    m = pd.read_parquet(dpath(fn))
    m["year"] = m.date.dt.year
    ret = (m.assign(ok=(m.drop_code == "OK")).groupby(["ticker", "node"])
             .agg(dates=("date", "size"), ok=("ok", "sum")))
    ret["share_ok"] = ret.ok / ret.dates
    ok = m[m.drop_code == "OK"][["ticker", "date", "node", "mfiv"]]
    j = ok.merge(rv, on=["ticker", "date", "node"], how="left")
    j = j[(j.date >= COMMON_START) & (j.date <= COMMON_END)]
    j = j[(j.rv > 0) & j.mfiv.notna()]
    j["lr"] = np.log(j.mfiv / j.rv)
    mean = j.groupby(["ticker", "node"]).agg(n=("lr", "size"), mean_lr=("lr", "mean"),
                                             median_lr=("lr", "median"))
    out = ret.join(mean, how="outer")
    out.columns = ["%s_%s" % (label, c) for c in out.columns]
    return out, m

a, m_after = summarise("mfiv.parquet", "after")
b, m_before = summarise("mfiv_nofilter.parquet", "before")
cmp = b.join(a)
cmp["delta_share_ok"] = cmp.after_share_ok - cmp.before_share_ok
cmp["delta_mean_lr"] = cmp.after_mean_lr - cmp.before_mean_lr

print("===== retention and mean log(IV2/RV) before and after A1 =====")
print(cmp[["before_dates", "before_ok", "before_share_ok", "after_ok", "after_share_ok",
           "delta_share_ok", "before_n", "before_mean_lr", "after_n", "after_mean_lr",
           "delta_mean_lr"]].round(4).to_string())

print("\n===== implied vol extremes before and after A1 (surviving rows) =====")
rows = []
for lab, m in (("before", m_before), ("after", m_after)):
    ok = m[m.drop_code == "OK"].copy()
    ok["ivol"] = np.sqrt(ok.mfiv) * 100
    g = ok.groupby(["ticker", "node"]).agg(
        n=("ivol", "size"), median=("ivol", "median"),
        p95=("ivol", lambda s: s.quantile(0.95)), max=("ivol", "max"),
        share_over_100=("ivol", lambda s: float((s > 100).mean())))
    g["which"] = lab
    rows.append(g.reset_index())
ext = pd.concat(rows).pivot_table(index=["ticker", "node"], columns="which",
                                  values=["median", "p95", "max", "share_over_100"])
print(ext.round(3).to_string())

print("\n===== figure-1 cells resting on fewer than 30 days, AFTER A1 =====")
ok = m_after[m_after.drop_code == "OK"][["ticker", "date", "node", "mfiv"]]
j = ok.merge(rv, on=["ticker", "date", "node"], how="left")
j = j[(j.rv > 0) & j.mfiv.notna()]
j["lr"] = np.log(j.mfiv / j.rv); j["year"] = j.date.dt.year
cell = j.groupby(["ticker", "node", "year"]).agg(n=("lr", "size"), mean_lr=("lr", "mean"))
thin = cell[cell.n < 30]
print(thin.round(4).to_string() if len(thin) else "(none)")

print("\n===== the UNG 2011 cell specifically, before and after =====")
okb = m_before[m_before.drop_code == "OK"][["ticker", "date", "node", "mfiv"]]
jb = okb.merge(rv, on=["ticker", "date", "node"], how="left")
jb = jb[(jb.rv > 0) & jb.mfiv.notna()]
jb["lr"] = np.log(jb.mfiv / jb.rv); jb["year"] = jb.date.dt.year
for lab, d in (("before", jb), ("after", j)):
    u = d[(d.ticker == "UNG") & (d.year == 2011)]
    g = u.groupby("node").agg(n=("lr", "size"), mean_lr=("lr", "mean"),
                              max_ivol=("mfiv", lambda s: float(np.sqrt(s.max()) * 100)))
    print("%s:" % lab); print(g.round(4).to_string())

cmp.reset_index().to_csv(opath("s1b_retention_before_after.csv"), index=False)
dump_json("s1b_step2f_compare.json", {
    "comparison": cmp.reset_index().replace({np.nan: None}).to_dict("records"),
    "thin_cells_after": thin.reset_index().to_dict("records"),
})
