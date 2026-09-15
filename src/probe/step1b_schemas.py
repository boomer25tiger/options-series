"""Step 1 (cont.): column lists for core OptionMetrics tables + feed span.

Note: db.describe_table() raises TypeError under wrds 3.5.0 + pandas 2.2.3 +
SQLAlchemy 2.0.53 (its internal parameter binding is broken). Its row-count
half (get_row_count) works, so we take the row count from there and the column
list from information_schema, which is the same catalog describe_table reads.
"""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json, timed

log_to("step1b_schemas.log")
db = connect()

LIB = "optionm"
TARGETS = ["vsurfd2025", "opprcd2025", "secprd2025", "securd", "securd1",
           "secnmd", "zerocd", "distrd", "idxdvd"]
schemas = {}
for tbl in TARGETS:
    print("\n===== %s.%s =====" % (LIB, tbl))
    try:
        n = db.get_row_count(LIB, tbl)
        print("row count (get_row_count): %s" % n)
    except Exception as e:
        n = None
        print("row count FAILED: %r" % (e,))
    try:
        db.describe_table(library=LIB, table=tbl)
    except Exception as e:
        print("describe_table() raised: %r  -> using information_schema" % (e,))
    cols = db.raw_sql(
        "select ordinal_position, column_name, data_type, is_nullable "
        "from information_schema.columns "
        "where table_schema=%(s)s and table_name=%(t)s order by ordinal_position",
        params={"s": LIB, "t": tbl})
    print(cols.to_string(index=False))
    schemas[tbl] = {"row_count": n, "columns": cols.to_dict("records")}

dump_json("step1b_schemas.json", schemas)

print("\n\n===== FEED SPAN =====")
span = {}
for base in ["secprd", "vsurfd"]:
    for yr in [1996, 2025]:
        t = "%s%d" % (base, yr)
        df, secs = timed(db, "select min(date) as mn, max(date) as mx, count(*) as n from %s.%s" % (LIB, t))
        print("%s.%s  min=%s max=%s rows=%s  (%.1fs)" % (LIB, t, df.mn[0], df.mx[0], df.n[0], secs))
        span["%s.%s" % (LIB, t)] = {"min": str(df.mn[0]), "max": str(df.mx[0]),
                                    "rows": int(df.n[0]), "seconds": round(secs, 2)}

today = datetime.date(2026, 9, 15)
for k, v in span.items():
    if k.endswith("2025"):
        mx = datetime.date.fromisoformat(v["max"][:10])
        v["gap_days_from_2026_09_15"] = (today - mx).days
        print("FEED END %s = %s ; gap from 2026-09-15 = %d calendar days"
              % (k, v["max"], v["gap_days_from_2026_09_15"]))

dump_json("step1b_span.json", span)
db.close()
