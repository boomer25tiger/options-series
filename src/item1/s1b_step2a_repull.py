"""Step 2a: re-pull opprcd with the A1 columns (ss_flag, root, suffix, contract_size).

Same secids, same spans, same 7-to-200-day exdate window and the same secid-and-date-first
filter as session 1. Overwrites the session 1 parquet files.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import connect, log_to, dump_json, dpath, SECIDS, PULL_SPAN
import pandas as pd

log_to("s1b_step2a_repull.log")
db = connect()

SQL = """select date, exdate, cp_flag, strike_price, best_bid, best_offer, forward_price,
                am_settlement, impl_volatility, volume, open_interest,
                ss_flag, root, suffix, contract_size
         from optionm.opprcd%d
         where secid = %%(s)s and date between %%(a)s and %%(b)s
           and exdate >= date + 7 and exdate <= date + 200"""

log = []
t_start = time.time()
for tic in ["UNG", "USO", "SLV", "GLD", "SPX"]:
    sid = SECIDS[tic]
    a, b = PULL_SPAN[tic]
    for yr in range(int(a[:4]), int(b[:4]) + 1):
        fn = dpath("opprcd_%s_%d.parquet" % (tic, yr))
        t0 = time.time()
        df = db.raw_sql(SQL % yr, params={"s": float(sid), "a": a, "b": b})
        t_pull = time.time() - t0
        df["strike_price"] = df["strike_price"] / 1000.0
        df["date"] = pd.to_datetime(df["date"])
        df["exdate"] = pd.to_datetime(df["exdate"])
        for c in ["best_bid", "best_offer", "forward_price", "am_settlement",
                  "impl_volatility", "volume", "open_interest", "contract_size"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df.to_parquet(fn, index=False, compression="zstd")
        rec = {"ticker": tic, "year": yr, "rows": len(df),
               "pull_seconds": round(t_pull, 2),
               "total_seconds": round(time.time() - t0, 2),
               "parquet_bytes": os.path.getsize(fn)}
        log.append(rec)
        print("%-4s %d  rows=%9d  pull=%6.1fs  total=%6.1fs  parquet=%7.1f MB"
              % (tic, yr, rec["rows"], rec["pull_seconds"], rec["total_seconds"],
                 rec["parquet_bytes"] / 1e6))
        del df

total = time.time() - t_start
print("\nTOTAL re-pull wall clock: %.1f s (%.1f min) over %d pulls, %.2f GB, %s rows"
      % (total, total / 60.0, len(log), sum(r["parquet_bytes"] for r in log) / 1e9,
         "{:,}".format(sum(r["rows"] for r in log))))
dump_json("s1b_step2a_repull.json", {"total_seconds": round(total, 1), "pulls": log})
db.close()
