"""Step 5a: pull the ATM surface node (6.2) and the underlying returns (6.3)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import connect, log_to, dump_json, dpath, opath, SECIDS, PULL_SPAN
import numpy as np
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)

log_to("s1_step5a_pull_vsurf_secpr.log")
db = connect()

vs_frames, sp_frames, timing = [], [], []
t_all = time.time()
for tic in ["SPX", "GLD", "SLV", "USO", "UNG"]:
    sid = SECIDS[tic]
    a, b = PULL_SPAN[tic]
    for yr in range(int(a[:4]), int(b[:4]) + 1):
        t0 = time.time()
        v = db.raw_sql("""select date, days, delta, cp_flag, impl_volatility
                          from optionm.vsurfd%d
                          where secid = %%(s)s and date between %%(a)s and %%(b)s
                            and days in (30, 91) and delta in (50, -50)""" % yr,
                       params={"s": float(sid), "a": a, "b": b})
        t1 = time.time()
        s = db.raw_sql("""select date, return from optionm.secprd%d
                          where secid = %%(s)s and date between %%(a)s and %%(b)s""" % yr,
                       params={"s": float(sid), "a": a, "b": b})
        t2 = time.time()
        v["ticker"] = tic; v["secid"] = sid
        s["ticker"] = tic; s["secid"] = sid
        vs_frames.append(v); sp_frames.append(s)
        timing.append({"ticker": tic, "year": yr, "vsurfd_rows": len(v),
                       "vsurfd_seconds": round(t1 - t0, 2),
                       "secprd_rows": len(s), "secprd_seconds": round(t2 - t1, 2)})
        print("%-4s %d  vsurfd rows=%5d (%4.1fs)  secprd rows=%4d (%4.1fs)"
              % (tic, yr, len(v), t1 - t0, len(s), t2 - t1))

vs = pd.concat(vs_frames, ignore_index=True)
sp = pd.concat(sp_frames, ignore_index=True)
vs["date"] = pd.to_datetime(vs["date"]); sp["date"] = pd.to_datetime(sp["date"])
for c in ["days", "delta", "impl_volatility"]:
    vs[c] = pd.to_numeric(vs[c], errors="coerce")
sp["return"] = pd.to_numeric(sp["return"], errors="coerce")
print("\nTOTAL pull wall clock: %.1f s over %d partition pairs" % (time.time() - t_all, len(timing)))

# ---- 6.2: ATM variance = (mean of the delta=+50 call IV and the delta=-50 put IV)^2 ----
leg = vs[((vs.delta == 50) & (vs.cp_flag == "C")) | ((vs.delta == -50) & (vs.cp_flag == "P"))]
print("\nvsurfd rows pulled: %d ; rows on the two spec legs: %d" % (len(vs), len(leg)))
print("leg composition:")
print(leg.groupby(["days", "delta", "cp_flag"]).size().to_string())

w = leg.pivot_table(index=["ticker", "secid", "date", "days"], columns="cp_flag",
                    values="impl_volatility", aggfunc="first").reset_index()
w = w.rename(columns={"days": "node", "C": "iv_call50", "P": "iv_put50"})
w["atm_vol"] = w[["iv_call50", "iv_put50"]].mean(axis=1, skipna=False)
w["atmiv"] = w.atm_vol ** 2
w["year"] = w.date.dt.year
w.to_parquet(dpath("atmiv.parquet"), index=False)

print("\n===== ATM node: null counts per secid, node and year =====")
nn = w.groupby(["ticker", "node", "year"]).agg(
    dates=("date", "size"),
    null_call=("iv_call50", lambda s: int(s.isna().sum())),
    null_put=("iv_put50", lambda s: int(s.isna().sum())),
    null_atmiv=("atmiv", lambda s: int(s.isna().sum())))
nn["share_null_atmiv"] = (nn.null_atmiv / nn.dates).round(4)
print(nn.to_string())
nn.reset_index().to_csv(opath("s1_step5_atm_nulls_by_year.csv"), index=False)

print("\n===== ATM node: totals per secid and node =====")
tot = w.groupby(["ticker", "node"]).agg(dates=("date", "size"),
                                        null_atmiv=("atmiv", lambda s: int(s.isna().sum())))
tot["share_null"] = (tot.null_atmiv / tot.dates).round(4)
print(tot.to_string())

# ---- returns ----
sp = sp.sort_values(["ticker", "date"]).reset_index(drop=True)
sp["year"] = sp.date.dt.year
sp.to_parquet(dpath("secprd_returns.parquet"), index=False)
print("\n===== returns: missing-return counts per secid and year =====")
rn = sp.groupby(["ticker", "year"]).agg(
    dates=("date", "size"), missing=("return", lambda s: int(s.isna().sum())))
rn["share_missing"] = (rn.missing / rn.dates).round(4)
print(rn.to_string())
rn.reset_index().to_csv(opath("s1_step5_return_missing_by_year.csv"), index=False)
print("\ntotals per secid:")
rt = sp.groupby("ticker").agg(dates=("date", "size"),
                              missing=("return", lambda s: int(s.isna().sum())))
rt["share_missing"] = (rt.missing / rt.dates).round(6)
print(rt.to_string())

dump_json("s1_step5a_pull.json", {
    "timing": timing,
    "vsurfd_rows": len(vs), "vsurfd_leg_rows": len(leg),
    "atm_rows": len(w), "atm_null_total": int(w.atmiv.isna().sum()),
    "secprd_rows": len(sp), "return_missing_total": int(sp["return"].isna().sum()),
    "atm_nulls_by_year": nn.reset_index().to_dict("records"),
    "return_missing_by_year": rn.reset_index().to_dict("records"),
})
db.close()
