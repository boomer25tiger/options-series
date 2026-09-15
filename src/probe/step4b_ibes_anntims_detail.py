"""Step 4b: is anntims a real clock time or a placeholder? (supplementary, measured)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100)

log_to("step4b_ibes_anntims_detail.log")
db = connect()
df = db.raw_sql("""
 select extract(year from anndats)::int as yr,
        count(*) as n,
        count(*) filter (where anntims = '00:00:00') as n_midnight,
        count(distinct anntims) as n_distinct_anntims,
        min(anntims) as min_anntims, max(anntims) as max_anntims,
        count(*) filter (where anntims >= '09:30:00' and anntims < '16:00:00') as n_in_rth
 from ibes.actu_epsus where anndats >= '2010-01-01' group by 1 order by 1""")
df["share_midnight"] = df.n_midnight / df.n
df["share_in_rth_0930_1600"] = df.n_in_rth / df.n
print(df.to_string(index=False))
dump_json("step4b_ibes_anntims_detail.json", df.to_dict("records"))
db.close()
