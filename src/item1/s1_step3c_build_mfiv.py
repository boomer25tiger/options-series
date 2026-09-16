"""Step 3c: run the section 6.1 estimator over every date in each secid's pull span."""
import os, sys, time, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import (log_to, dump_json, dpath, opath, SECIDS, PULL_SPAN, NODES)
from item1.mfiv import mfiv_one_date
import numpy as np
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)

log_to("s1_step3c_build_mfiv.log")

z = pd.read_parquet(dpath("zerocd.parquet"))
z["date"] = pd.to_datetime(z["date"])
zg = {d: (g.days.values.astype(float), g.rate.values.astype(float))
      for d, g in z.sort_values(["date", "days"]).groupby("date")}
zdates = np.array(sorted(zg))
print("zerocd: %d dates, %s .. %s" % (len(zdates), zdates[0].date(), zdates[-1].date()))

def rate_curve(d):
    """Exact zerocd date if present, else the nearest earlier date. Returns (curve, fellback)."""
    if d in zg:
        return zg[d], False
    i = np.searchsorted(zdates, d) - 1
    if i < 0:
        return (None, None), True
    return zg[zdates[i]], True

rows, timing = [], []
n_fallback = 0
n_dupe_dates = 0
t_all = time.time()

for tic in ["SPX", "GLD", "SLV", "USO", "UNG"]:
    sid = SECIDS[tic]
    a, b = PULL_SPAN[tic]
    for yr in range(int(a[:4]), int(b[:4]) + 1):
        fn = dpath("opprcd_%s_%d.parquet" % (tic, yr))
        if not os.path.exists(fn):
            print("%-4s %d  NOT PULLED, skipped" % (tic, yr)); continue
        t0 = time.time()
        df = pd.read_parquet(fn)
        ndates = 0
        for d, q in df.groupby("date", sort=True):
            ndates += 1
            if q.duplicated(["exdate", "am_settlement", "cp_flag", "strike_price"]).any():
                n_dupe_dates += 1
            (zd, zr), fell = rate_curve(d)
            n_fallback += fell
            res = mfiv_one_date(d, q, zd, zr, nodes=NODES)
            for node, rec in res.items():
                rows.append({"secid": sid, "ticker": tic, "date": d, "node": node,
                             "mfiv": rec["mfiv"],
                             "expiry_low": rec["expiry_low"], "expiry_high": rec["expiry_high"],
                             "n_strikes_low_put": rec["n_strikes_low_put"],
                             "n_strikes_low_call": rec["n_strikes_low_call"],
                             "n_strikes_high_put": rec["n_strikes_high_put"],
                             "n_strikes_high_call": rec["n_strikes_high_call"],
                             "drop_code": rec["drop_code"]})
        el = time.time() - t0
        timing.append({"ticker": tic, "year": yr, "dates": ndates, "rows_in": len(df),
                       "seconds": round(el, 2)})
        print("%-4s %d  dates=%4d  rows_in=%9d  %6.1f s" % (tic, yr, ndates, len(df), el))
        del df

mf = pd.DataFrame(rows)
total = time.time() - t_all
print("\nCONSTRUCTION wall clock: %.1f s (%.1f min) for %d secid-date-node records"
      % (total, total / 60.0, len(mf)))
print("dates whose zerocd curve came from an earlier date (fallback): %d" % n_fallback)
print("secid-dates carrying duplicate (exdate, am_settlement, cp_flag, strike) rows: %d"
      % n_dupe_dates)

mf["year"] = mf.date.dt.year
mf.to_parquet(dpath("mfiv.parquet"), index=False)
print("wrote %s (%.1f MB)" % (dpath("mfiv.parquet"),
                              os.path.getsize(dpath("mfiv.parquet")) / 1e6))

print("\n===== drop codes, overall =====")
print(mf.groupby(["ticker", "node", "drop_code"]).size().unstack(fill_value=0).to_string())

print("\n===== retention by ticker and node =====")
ret = (mf.assign(ok=(mf.drop_code == "OK"))
         .groupby(["ticker", "node"])
         .agg(dates=("date", "size"), ok=("ok", "sum")))
ret["share_ok"] = (ret.ok / ret.dates).round(4)
print(ret.to_string())

print("\n===== drop counts per secid, node and year, by drop code =====")
per = (mf[mf.drop_code != "OK"]
       .groupby(["ticker", "node", "year", "drop_code"]).size()
       .unstack(fill_value=0))
print(per.to_string() if len(per) else "(no drops)")
per.reset_index().to_csv(opath("s1_step3_drops_by_year.csv"), index=False)

print("\n===== median OTM strikes per side, per secid and year "
      "(rows where a bracket was found) =====")
built = mf[mf.expiry_low.notna()]
med = (built.groupby(["ticker", "node", "year"])[
    ["n_strikes_low_put", "n_strikes_low_call", "n_strikes_high_put", "n_strikes_high_call"]]
    .median().astype(int))
med["n_dates"] = built.groupby(["ticker", "node", "year"]).size()
print(med.to_string())
med.reset_index().to_csv(opath("s1_step3_median_strikes.csv"), index=False)

print("\n===== how often the 3-strike floor binds, by side =====")
for c in ["n_strikes_low_put", "n_strikes_low_call", "n_strikes_high_put", "n_strikes_high_call"]:
    print("  %-20s share of bracketed rows with fewer than 3 : %.4f"
          % (c, (built[c] < 3).mean()))

dump_json("s1_step3c_build_mfiv.json", {
    "construction_seconds": round(total, 1),
    "records": len(mf),
    "zerocd_fallback_dates": int(n_fallback),
    "dates_with_duplicate_rows": int(n_dupe_dates),
    "timing": timing,
    "retention": ret.reset_index().to_dict("records"),
    "floor_bind_shares": {c: float((built[c] < 3).mean()) for c in
                          ["n_strikes_low_put", "n_strikes_low_call",
                           "n_strikes_high_put", "n_strikes_high_call"]},
})
