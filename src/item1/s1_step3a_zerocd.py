"""Step 3a: pull optionm.zerocd in full."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import connect, log_to, dump_json, cols_of, dpath
import pandas as pd
pd.set_option("display.width", 250)

log_to("s1_step3a_zerocd.log")
db = connect()
print(cols_of(db, "optionm", "zerocd").to_string(index=False))
t0 = time.time()
z = db.raw_sql("select date, days, rate from optionm.zerocd order by date, days")
el = time.time() - t0
z["date"] = pd.to_datetime(z["date"])
z.to_parquet(dpath("zerocd.parquet"), index=False)
print("\npull wall clock %.2f s ; rows %d (count(*) on the table: %s)"
      % (el, len(z), int(db.raw_sql("select count(*) as n from optionm.zerocd").n[0])))
print("date span : %s .. %s  (%d distinct dates)"
      % (z.date.min().date(), z.date.max().date(), z.date.nunique()))
print("days span : %.0f .. %.0f" % (z.days.min(), z.days.max()))
print("rate: min %.4f max %.4f mean %.4f  (units: percent per annum)"
      % (z.rate.min(), z.rate.max(), z.rate.mean()))
print("null rate rows: %d" % z.rate.isna().sum())
print("\nrows per date, describe:")
print(z.groupby("date").size().describe().to_string())
print("\nhead:"); print(z.head(12).to_string(index=False))
dump_json("s1_step3a_zerocd.json", {
    "pull_seconds": round(el, 2), "rows": len(z),
    "min_date": str(z.date.min().date()), "max_date": str(z.date.max().date()),
    "n_dates": int(z.date.nunique()),
    "days_min": float(z.days.min()), "days_max": float(z.days.max()),
    "rate_min": float(z.rate.min()), "rate_max": float(z.rate.max()),
    "rate_null": int(z.rate.isna().sum())})
db.close()
