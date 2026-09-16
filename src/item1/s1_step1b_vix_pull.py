"""Step 1 (cont.): pull the daily VIX close over the common window."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import connect, log_to, dump_json, dpath, COMMON_START, COMMON_END
import pandas as pd

log_to("s1_step1b_vix_pull.log")
db = connect()

t0 = time.time()
df = db.raw_sql("""select date, vixo, vixh, vixl, vix
                   from cboe.cboe
                   where date between %(a)s and %(b)s
                   order by date""",
                params={"a": COMMON_START, "b": COMMON_END})
el = time.time() - t0
df["date"] = pd.to_datetime(df["date"])
for c in ["vixo", "vixh", "vixl", "vix"]:
    df[c] = pd.to_numeric(df[c])

print("pull wall clock: %.2f s" % el)
print("rows: %d" % len(df))
print("first date: %s" % df.date.min().date())
print("last  date: %s" % df.date.max().date())
print("non-null vix (close): %d  (share %.6f)" % (df.vix.notna().sum(),
                                                  df.vix.notna().mean()))
print("\nfull-table span for reference:")
full = db.raw_sql("select min(date) as mn, max(date) as mx, count(*) as n from cboe.cboe")
print(full.to_string(index=False))

df.to_parquet(dpath("vix.parquet"), index=False)
print("\nwrote %s (%d bytes)" % (dpath("vix.parquet"), os.path.getsize(dpath("vix.parquet"))))

dump_json("s1_step1b_vix_pull.json", {
    "table": "cboe.cboe", "close_column": "vix",
    "pull_seconds": round(el, 2),
    "common_window": [COMMON_START, COMMON_END],
    "rows": len(df),
    "first_date": str(df.date.min().date()), "last_date": str(df.date.max().date()),
    "nonnull_vix": int(df.vix.notna().sum()),
    "nonnull_share": float(df.vix.notna().mean()),
    "full_table_min": str(full.mn[0]), "full_table_max": str(full.mx[0]),
    "full_table_rows": int(full.n[0]),
})
db.close()
