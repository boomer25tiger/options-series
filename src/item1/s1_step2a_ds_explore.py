"""Step 2a: column lists for the tr_ds_fut tables, and candidate continuous series."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import connect, log_to, dump_json, cols_of
import pandas as pd
pd.set_option("display.width", 300); pd.set_option("display.max_rows", 600)
pd.set_option("display.max_colwidth", 60)

log_to("s1_step2a_ds_explore.log")
db = connect()
out = {}

TABLES = ["wrds_cseries_info", "dsfutcalcserinfo", "dsfutcalcserval",
          "dsfutcalcsermth", "wrds_fut_series"]
out["columns"] = {}
for t in TABLES:
    c = cols_of(db, "tr_ds_fut", t)
    n = db.get_row_count("tr_ds_fut", t)
    print("\n===== tr_ds_fut.%s (get_row_count estimate: %s) =====" % (t, n))
    print(c.to_string(index=False))
    out["columns"]["tr_ds_fut." + t] = {"row_count_estimate": n,
                                        "columns": c.to_dict("records")}

# Exchange prefixes in Datastream calcseriesname: NYM- / CMX-.
SEARCH = {
    "CL": ("NYM crude light sweet", "(calcseriesname ilike '%%CRUDE%%' or dsmnem ilike '%%CL%%') "
                                    "and calcseriesname ilike '%%NYM%%'"),
    "NG": ("NYM natural gas", "calcseriesname ilike '%%NYM%%' and calcseriesname ilike '%%GAS%%'"),
    "GC": ("CMX gold", "calcseriesname ilike '%%CMX%%' and calcseriesname ilike '%%GOLD%%'"),
    "SI": ("CMX silver", "calcseriesname ilike '%%CMX%%' and calcseriesname ilike '%%SILVER%%'"),
}
out["candidates"] = {}
for code, (label, where) in SEARCH.items():
    df = db.raw_sql("""select calcseriescode, clscode, dsmnem, calcseriesname,
                              isocurrcode, rollmethodcode, rollmethoddesc,
                              positionfwdcode, positionfwddesc, calcmthcode, trdmonths
                       from tr_ds_fut.wrds_cseries_info
                       where %s
                       order by dsmnem limit 100""" % where)
    print("\n\n########## %s (%s) : %d rows (cap 100) ##########" % (code, label, len(df)))
    print(df.to_string(index=False))
    out["candidates"][code] = {"label": label, "where": where,
                               "n": len(df), "rows": df.to_dict("records")}

dump_json("s1_step2a_ds_explore.json", out)
db.close()
