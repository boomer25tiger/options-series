"""Step 1c: is optionm a view layer over optionm_all, and do both end on the same date?"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100)

log_to("step1c_optionm_all.log")
db = connect()
t = db.raw_sql("""select table_schema, table_type, count(*) as n
                  from information_schema.tables
                  where table_schema in ('optionm','optionm_all')
                  group by 1,2 order by 1,2""")
print(t.to_string(index=False))

v = db.raw_sql("""select table_schema, table_name, view_definition
                  from information_schema.views
                  where table_schema='optionm' and table_name in ('vsurfd2025','opprcd2025','securd1')""")
for r in v.itertuples():
    print("\n%s.%s view_definition:\n%s" % (r.table_schema, r.table_name, r.view_definition))

out = {"table_types": t.to_dict("records"), "views": v.to_dict("records"), "spans": {}}
for lib in ["optionm", "optionm_all"]:
    for tbl in ["vsurfd2025", "secprd2025", "opprcd2025"]:
        d = db.raw_sql("select min(date) as mn, max(date) as mx from %s.%s" % (lib, tbl))
        print("%-12s %-12s min=%s max=%s" % (lib, tbl, d.mn[0], d.mx[0]))
        out["spans"]["%s.%s" % (lib, tbl)] = {"min": str(d.mn[0]), "max": str(d.mx[0])}
dump_json("step1c_optionm_all.json", out)
db.close()
