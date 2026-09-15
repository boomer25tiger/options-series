"""Step 3: sizing the single vsurfd node days=30, delta=50, cp_flag='C'."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json

log_to("step3_sizing.log")
db = connect()

sql = """select count(*) as n_rows, count(distinct secid) as n_secids,
                count(distinct date) as n_dates,
                min(date) as mn, max(date) as mx
         from optionm.vsurfd2024
         where days = 30 and delta = 50 and cp_flag = 'C'"""
t0 = time.time()
df = db.raw_sql(sql)
el = time.time() - t0
r = df.iloc[0]
print("SQL:\n%s\n" % sql)
print("n_rows   = %d" % r.n_rows)
print("n_secids = %d" % r.n_secids)
print("n_dates  = %d  (%s .. %s)" % (r.n_dates, r.mn, r.mx))
print("wall clock = %.2f s" % el)

N_YEARS = 30  # vsurfd partitions 1996..2025 inclusive; 2025 is partial (ends 2025-08-29)
proj = int(r.n_rows) * N_YEARS
print("\nPROJECTION (not a measurement): %d rows x %d year partitions = %d rows"
      % (r.n_rows, N_YEARS, proj))

dump_json("step3_sizing.json", {
    "node": {"days": 30, "delta": 50, "cp_flag": "C"},
    "year_measured": 2024,
    "n_rows": int(r.n_rows), "n_secids": int(r.n_secids), "n_dates": int(r.n_dates),
    "min_date": str(r.mn), "max_date": str(r.mx),
    "seconds": round(el, 2),
    "n_year_partitions_1996_to_feed_end": N_YEARS,
    "projected_rows_1996_to_feed_end": proj,
    "projection_note": "projection = 2024 count x 30 partitions; 2025 is partial and early years have fewer secids",
})
db.close()
