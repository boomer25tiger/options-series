"""Step 4: IBES actuals tables, announcement date/time coverage."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json, OUT_DIR
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)

log_to("step4_ibes.log")
db = connect()
out = {}

libs = [l for l in db.list_libraries() if "ibes" in l.lower()]
print("libraries containing 'ibes': %s" % sorted(libs))
out["ibes_libraries"] = sorted(libs)

tabs = sorted(db.list_tables(library="ibes"))
print("\nibes: %d tables total" % len(tabs))
hits = [t for t in tabs if "actu" in t.lower() or "act_" in t.lower()]
print("tables matching 'actu' or 'act_': %d" % len(hits))
for t in hits:
    print("  " + t)
out["ibes_all_tables"] = tabs
out["ibes_actuals_tables"] = hits

TBL = "actu_epsus"
print("\n===== ibes.%s =====" % TBL)
print("present in ibes table list: %s" % (TBL in tabs))
try:
    print("row count: %s" % db.get_row_count("ibes", TBL))
except Exception as e:
    print("row count FAILED: %r" % (e,))
cols = db.raw_sql(
    "select ordinal_position, column_name, data_type, is_nullable "
    "from information_schema.columns where table_schema='ibes' and table_name=%(t)s "
    "order by ordinal_position", params={"t": TBL})
print(cols.to_string(index=False))
out["actu_epsus_columns"] = cols.to_dict("records")
colnames = set(cols.column_name)
has_time = "anntims" in colnames
print("\nanndats present: %s ; anntims present: %s" % ("anndats" in colnames, has_time))
out["has_anndats"] = "anndats" in colnames
out["has_anntims"] = has_time

span = db.raw_sql("select min(anndats) as mn, max(anndats) as mx, count(*) as n, "
                  "count(anndats) as nn_anndats from ibes.%s" % TBL)
print("\nanndats span: min=%s max=%s  total_rows=%s  non-null anndats=%s"
      % (span.mn[0], span.mx[0], span.n[0], span.nn_anndats[0]))
out["anndats_span"] = {"min": str(span.mn[0]), "max": str(span.mx[0]),
                       "total_rows": int(span.n[0]), "nn_anndats": int(span.nn_anndats[0])}

if has_time:
    t0 = time.time()
    yr = db.raw_sql("""select extract(year from anndats)::int as yr,
                              count(*) as n_rows,
                              count(anndats) as nn_anndats,
                              count(anntims) as nn_anntims
                       from ibes.%s
                       where anndats >= '2010-01-01'
                       group by 1 order by 1""" % TBL)
    print("\nby-year query wall clock: %.1fs" % (time.time() - t0))
    yr["share_nn_anntims"] = yr.nn_anntims / yr.nn_anndats
    print(yr.to_string(index=False))
    yr.to_csv(os.path.join(OUT_DIR, "step4_ibes_anntims_by_year.csv"), index=False)
    out["anntims_by_year"] = yr.to_dict("records")
else:
    print("\nNo announcement-time column on ibes.%s." % TBL)

dump_json("step4_ibes.json", out)
db.close()
