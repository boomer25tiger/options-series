"""Step 6: CRSP S&P 500 index series and constituent membership."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)

log_to("step6_crsp.log")
db = connect()
out = {}

libs = sorted(l for l in db.list_libraries() if "crsp" in l.lower())
print("libraries containing 'crsp': %s" % libs)
out["crsp_libraries"] = libs

# Which schemas actually hold an object named like dsp500 / sp500 / index?
q = """select table_schema, table_name, table_type
       from information_schema.tables
       where (table_name ilike '%%sp500%%' or table_name ilike '%%dsp5%%'
              or table_name ilike '%%msp500%%')
       order by table_schema, table_name"""
t = db.raw_sql(q)
print("\n===== objects named like sp500 anywhere the account can see =====")
print(t.to_string(index=False))
out["sp500_like_objects"] = t.to_dict("records")

TARGETS = [("crsp", "dsp500"), ("crsp", "dsp500list"),
           ("crsp_a_indexes", "dsp500"), ("crsp_a_indexes", "dsp500list"),
           ("crsp", "dsp500list_v2"), ("crsp", "msp500"), ("crsp", "msp500list")]
out["targets"] = {}
for lib, tbl in TARGETS:
    key = "%s.%s" % (lib, tbl)
    print("\n===== %s =====" % key)
    cols = db.raw_sql(
        "select ordinal_position, column_name, data_type from information_schema.columns "
        "where table_schema=%(s)s and table_name=%(t)s order by ordinal_position",
        params={"s": lib, "t": tbl})
    if not len(cols):
        print("DOES NOT EXIST / not visible to this account")
        out["targets"][key] = {"exists": False}
        continue
    print("EXISTS. columns:")
    print(cols.to_string(index=False))
    rec = {"exists": True, "columns": cols.to_dict("records")}
    names = list(cols.column_name)
    datecols = [c for c in names if c in
                ("caldt", "date", "start", "ending", "mbrstartdt", "mbrenddt")]
    try:
        rec["row_count"] = db.get_row_count(lib, tbl)
        print("row count: %s" % rec["row_count"])
    except Exception as e:
        print("row count FAILED: %r" % (e,))
    for dc in datecols:
        d = db.raw_sql("select min(%s) as mn, max(%s) as mx, count(%s) as nn from %s.%s"
                       % (dc, dc, dc, lib, tbl))
        print("  %-12s min=%s max=%s non-null=%s" % (dc, d.mn[0], d.mx[0], d.nn[0]))
        rec.setdefault("date_spans", {})[dc] = {"min": str(d.mn[0]), "max": str(d.mx[0]),
                                                "non_null": int(d.nn[0])}
    out["targets"][key] = rec

print("\n===== dsf_v2 one-row existence check =====")
try:
    r = db.raw_sql("select * from crsp.dsf_v2 limit 1")
    print("crsp.dsf_v2 readable; %d columns returned in a 1-row probe" % r.shape[1])
    out["dsf_v2"] = {"readable": True, "n_columns": int(r.shape[1])}
except Exception as e:
    print("crsp.dsf_v2 probe FAILED: %r" % (e,))
    out["dsf_v2"] = {"readable": False, "error": str(e)}

dump_json("step6_crsp.json", out)
db.close()
