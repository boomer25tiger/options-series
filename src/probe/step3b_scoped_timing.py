"""Step 3b: cost of a secid-scoped read on the same partition, and index visibility."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json, timed
import pandas as pd
pd.set_option("display.width", 250)

log_to("step3b_scoped_timing.log")
db = connect()
out = {}

idx = db.raw_sql("""select schemaname, tablename, indexname
                    from pg_indexes
                    where schemaname in ('optionm','optionm_all')
                      and tablename in ('vsurfd2024','opprcd2024','secprd2024')""")
print("pg_indexes rows visible for these tables: %d" % len(idx))
print(idx.to_string(index=False) if len(idx) else "(none)")
out["n_visible_indexes"] = len(idx)
out["indexes"] = idx.to_dict("records")

SECIDS = [108105.0, 109820.0, 122392.0, 126776.0, 126681.0, 129367.0]
df, el = timed(db, """select secid, min(date) as mn, max(date) as mx,
                             count(distinct date) as nd, count(*) as n
                      from optionm.vsurfd2024 where secid = any(%(s)s)
                      group by secid order by secid""", {"s": SECIDS})
print("\nsecid-scoped aggregate over optionm.vsurfd2024 (6 secids): %.2f s" % el)
print(df.to_string(index=False))
out["scoped_6_secid_seconds"] = round(el, 2)
out["scoped_6_secid_rows_returned"] = int(df.n.sum())

df2, el2 = timed(db, """select count(*) as n from optionm.vsurfd2024
                        where secid = 108105 and days = 30 and delta = 50 and cp_flag = 'C'""")
print("\nsingle-secid single-node count on vsurfd2024: n=%d in %.2f s" % (df2.n[0], el2))
out["single_secid_node_seconds"] = round(el2, 2)
out["single_secid_node_rows"] = int(df2.n[0])

dump_json("step3b_scoped_timing.json", out)
db.close()
