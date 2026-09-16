"""Step 3b: registered diagnostic A3(b), the floor-of-2 robustness series."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath, COMMON_START, COMMON_END
import numpy as np
import pandas as pd
pd.set_option("display.width", 300); pd.set_option("display.max_rows", 200)

log_to("s1b_step3b_floor2.log")
rv = pd.read_parquet(dpath("premium_daily.parquet"))[["ticker", "date", "node", "rv"]]

def summarise(fn, label):
    m = pd.read_parquet(dpath(fn))
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
    return out

f3 = summarise("mfiv.parquet", "floor3")
f2 = summarise("mfiv_floor2.parquet", "floor2")
t = f3.join(f2)
t["delta_share_ok"] = t.floor2_share_ok - t.floor3_share_ok
t["delta_mean_lr"] = t.floor2_mean_lr - t.floor3_mean_lr
print("===== A3(b) floor of 2 against the spec floor of 3, both with A1 in force =====")
print(t[["floor3_ok", "floor3_share_ok", "floor2_ok", "floor2_share_ok", "delta_share_ok",
         "floor3_n", "floor3_mean_lr", "floor2_n", "floor2_mean_lr",
         "delta_mean_lr"]].round(4).to_string())
print("\nThis is the robustness row that sits next to every primary H1 number in session 2.")
t.reset_index().to_csv(opath("s1b_a3b_floor2.csv"), index=False)
dump_json("s1b_step3b_floor2.json",
          {"rows": t.reset_index().replace({np.nan: None}).to_dict("records")})
