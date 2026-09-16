"""Step 1: is a daily VIX close available in a cboe library on WRDS?"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import (connect, log_to, dump_json, cols_of, dpath,
                          COMMON_START, COMMON_END)
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)

log_to("s1_step1_vix.log")
db = connect()
out = {}

libs = sorted(l for l in db.list_libraries() if "cboe" in l.lower())
print("libraries containing 'cboe': %s" % libs)
out["cboe_libraries"] = libs

out["tables"] = {}
for lib in libs:
    try:
        tabs = sorted(db.list_tables(library=lib))
    except Exception as e:
        print("  %s list_tables FAILED %r" % (lib, e))
        out["tables"][lib] = {"error": str(e)}
        continue
    out["tables"][lib] = tabs
    print("\n=== %s : %d tables ===" % (lib, len(tabs)))
    for t in tabs:
        print("   " + t)

# Any table in those libraries whose NAME or whose COLUMNS suggest a daily VIX close.
if libs:
    cand = db.raw_sql("""
        select table_schema, table_name, column_name, data_type
        from information_schema.columns
        where table_schema = any(%(l)s)
        order by table_schema, table_name, ordinal_position""", params={"l": libs})
    out["all_columns"] = cand.to_dict("records")
    name_hit = sorted({(r.table_schema, r.table_name) for r in cand.itertuples()
                       if "vix" in r.table_name.lower()})
    col_hit = sorted({(r.table_schema, r.table_name) for r in cand.itertuples()
                      if "vix" in r.column_name.lower()})
    print("\ntables whose NAME contains 'vix': %s" % (name_hit or "(none)"))
    print("tables with a COLUMN containing 'vix': %s" % (col_hit or "(none)"))
    out["name_hits"] = [list(x) for x in name_hit]
    out["col_hits"] = [list(x) for x in col_hit]

    targets = sorted(set(name_hit) | set(col_hit))
    out["schemas"] = {}
    for sch, tbl in targets:
        c = cols_of(db, sch, tbl)
        n = db.raw_sql("select count(*) as n from %s.%s" % (sch, tbl))
        print("\n===== %s.%s : %s rows (count(*)) =====" % (sch, tbl, int(n.n[0])))
        print(c.to_string(index=False))
        out["schemas"]["%s.%s" % (sch, tbl)] = {
            "row_count_exact": int(n.n[0]), "columns": c.to_dict("records")}
else:
    print("\nNo library on this account contains the string 'cboe'.")
    out["name_hits"] = []; out["col_hits"] = []; out["schemas"] = {}

# Widen: any table ANYWHERE the account can see whose name looks like a VIX series.
wide = db.raw_sql("""
    select table_schema, table_name, table_type
    from information_schema.tables
    where table_name ilike '%%vix%%'
    order by table_schema, table_name""")
print("\n===== objects named like '%%vix%%' anywhere the account can see: %d =====" % len(wide))
print(wide.to_string(index=False) if len(wide) else "(none)")
out["vix_named_objects_anywhere"] = wide.to_dict("records")

dump_json("s1_step1_vix.json", out)
db.close()
