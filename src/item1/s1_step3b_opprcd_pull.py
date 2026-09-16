"""Step 3b: pull opprcd one secid and one year partition at a time.

Every query filters on secid and date before any other predicate, per the handling
rules. strike_price is divided by 1000 on read (OptionMetrics scales it by 1000).
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import connect, log_to, dump_json, dpath, SECIDS, PULL_SPAN
import pandas as pd

BUDGET_SECONDS = 60 * 60  # session instruction: 60 minutes total for the opprcd pulls

log_to("s1_step3b_opprcd_pull.log")
db = connect()

SQL = """select date, exdate, cp_flag, strike_price, best_bid, best_offer, forward_price,
                am_settlement, impl_volatility, volume, open_interest
         from optionm.opprcd%d
         where secid = %%(s)s and date between %%(a)s and %%(b)s
           and exdate >= date + 7 and exdate <= date + 200"""

log = []
t_start = time.time()
stopped = False
# heaviest secid last so a budget stop costs the fewest secids
ORDER = ["UNG", "USO", "SLV", "GLD", "SPX"]
for tic in ORDER:
    sid = SECIDS[tic]
    a, b = PULL_SPAN[tic]
    y0, y1 = int(a[:4]), int(b[:4])
    for yr in range(y0, y1 + 1):
        elapsed = time.time() - t_start
        if elapsed > BUDGET_SECONDS:
            print("\n*** BUDGET STOP: %.1f min elapsed, %s %d and later NOT PULLED ***"
                  % (elapsed / 60.0, tic, yr))
            stopped = True
            break
        fn = dpath("opprcd_%s_%d.parquet" % (tic, yr))
        t0 = time.time()
        df = db.raw_sql(SQL % yr, params={"s": float(sid), "a": a, "b": b})
        t_pull = time.time() - t0
        df["strike_price"] = df["strike_price"] / 1000.0
        df["date"] = pd.to_datetime(df["date"])
        df["exdate"] = pd.to_datetime(df["exdate"])
        for c in ["best_bid", "best_offer", "forward_price", "am_settlement",
                  "impl_volatility", "volume", "open_interest"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df.to_parquet(fn, index=False, compression="zstd")
        sz = os.path.getsize(fn)
        rec = {"ticker": tic, "secid": sid, "year": yr, "rows": len(df),
               "pull_seconds": round(t_pull, 2),
               "total_seconds": round(time.time() - t0, 2),
               "parquet_bytes": sz,
               "n_dates": int(df.date.nunique()) if len(df) else 0,
               "n_exdates": int(df.exdate.nunique()) if len(df) else 0,
               "fwd_nonnull": int(df.forward_price.notna().sum()),
               "file": os.path.basename(fn)}
        log.append(rec)
        print("%-4s %d  rows=%9d  pull=%6.1fs  total=%6.1fs  parquet=%7.1f MB  dates=%4d  "
              "exdates=%4d  fwd_nonnull=%d"
              % (tic, yr, rec["rows"], rec["pull_seconds"], rec["total_seconds"],
                 sz / 1e6, rec["n_dates"], rec["n_exdates"], rec["fwd_nonnull"]))
        del df
    if stopped:
        break

total = time.time() - t_start
print("\nTOTAL opprcd pull wall clock: %.1f s (%.1f min) over %d pulls"
      % (total, total / 60.0, len(log)))
print("TOTAL parquet bytes: %.2f GB" % (sum(r["parquet_bytes"] for r in log) / 1e9))
print("TOTAL rows: %d" % sum(r["rows"] for r in log))
done = {(r["ticker"], r["year"]) for r in log}
missing = []
for tic in ORDER:
    a, b = PULL_SPAN[tic]
    for yr in range(int(a[:4]), int(b[:4]) + 1):
        if (tic, yr) not in done:
            missing.append("%s %d" % (tic, yr))
print("NOT PULLED: %s" % (missing if missing else "(none)"))

dump_json("s1_step3b_opprcd_pull.json",
          {"budget_seconds": BUDGET_SECONDS, "total_seconds": round(total, 1),
           "stopped_on_budget": stopped, "pulls": log, "not_pulled": missing})
db.close()
