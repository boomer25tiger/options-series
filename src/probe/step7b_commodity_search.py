"""Step 7b: search Datastream descriptive tables for commodity series names."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json, OUT_DIR
import pandas as pd
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 60)
pd.set_option("display.max_colwidth", 55)

log_to("step7b_commodity_search.log")
db = connect()

TERMS = ["GOLD", "SILVER", "CRUDE", "WTI", "NATURAL GAS", "HENRY HUB"]
SOURCES = [
    ("tr_ds_comds", "wrds_cmdy_info", "comcode", ["name", "dsname", "comdesc", "dsmnemonic"]),
    ("tr_ds_comds", "dscminfo",       "comcode", ["name_", "dsname", "dsmnemonic"]),
    ("tr_ds_fut",   "dsfutcontr",     "contrcode", ["contrname", "dscontrid", "exchtickersymb"]),
    ("tr_ds_fut",   "wrds_cseries_info", "calcseriescode", ["calcseriesname", "dsmnem"]),
    ("tr_ds_fut",   "wrds_contract_info", "futcode", ["contrname", "dsmnem"]),
]
out = {}
for lib, tbl, codecol, namecols in SOURCES:
    key = "%s.%s" % (lib, tbl)
    try:
        n = db.get_row_count(lib, tbl)
    except Exception as e:
        n = "count failed: %r" % (e,)
    print("\n############ %s (rows=%s) ############" % (key, n))
    out[key] = {"row_count": n, "name_columns": namecols, "terms": {}}
    for term in TERMS:
        where = " or ".join("%s ilike %%(p)s" % c for c in namecols)
        cnt = db.raw_sql("select count(*) as n from %s.%s where %s" % (lib, tbl, where),
                         params={"p": "%%%s%%" % term})
        total = int(cnt.n[0])
        sel = ", ".join([codecol] + namecols)
        df = db.raw_sql("select %s from %s.%s where %s order by %s limit 50"
                        % (sel, lib, tbl, where, codecol), params={"p": "%%%s%%" % term})
        print("\n--- %s : term '%s' -> %d total matches, showing %d ---"
              % (key, term, total, len(df)))
        if len(df):
            print(df.to_string(index=False))
        else:
            print("  (no matches)")
        out[key]["terms"][term] = {"total_matches": total,
                                   "shown": len(df),
                                   "rows": df.to_dict("records")}
dump_json("step7b_commodity_search.json", out)
db.close()
