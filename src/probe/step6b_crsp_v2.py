"""Step 6b: the _v2 S&P 500 index series, since crsp.dsp500 stops in 2024."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json
import pandas as pd
pd.set_option("display.width", 250)

log_to("step6b_crsp_v2.log")
db = connect()
out = {}
for lib, tbl in [("crsp", "dsp500_v2"), ("crsp", "dsp500p"), ("crsp", "msp500_v2")]:
    key = "%s.%s" % (lib, tbl)
    cols = db.raw_sql("select ordinal_position, column_name, data_type from "
                      "information_schema.columns where table_schema=%(s)s and "
                      "table_name=%(t)s order by ordinal_position",
                      params={"s": lib, "t": tbl})
    print("\n===== %s =====" % key)
    if not len(cols):
        print("DOES NOT EXIST"); out[key] = {"exists": False}; continue
    print(cols.to_string(index=False))
    n = db.get_row_count(lib, tbl)
    print("row count: %s" % n)
    dc = "caldt" if "caldt" in list(cols.column_name) else list(cols.column_name)[0]
    d = db.raw_sql("select min(%s) as mn, max(%s) as mx from %s.%s" % (dc, dc, lib, tbl))
    print("%s min=%s max=%s" % (dc, d.mn[0], d.mx[0]))
    out[key] = {"exists": True, "row_count": n, "columns": cols.to_dict("records"),
                "date_col": dc, "min": str(d.mn[0]), "max": str(d.mx[0])}
dump_json("step6b_crsp_v2.json", out)
db.close()
