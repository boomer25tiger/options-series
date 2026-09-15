"""Step 2c: opprcd calendar-2024 profile for the resolved secids."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json, OUT_DIR
import pandas as pd
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 60)

log_to("step2c_opprcd2024.log")
db = connect()
CANDIDATES = [7571, 8274, 8321, 100155, 108105, 109820, 111334, 115101,
              122392, 126681, 126776, 126778, 126779, 129361, 129362, 129367]

sql = """
select secid,
       count(*)                                          as n_rows,
       count(distinct exdate)                            as n_exdates,
       count(distinct date)                              as n_dates,
       min(date)                                         as first_date,
       max(date)                                         as last_date,
       min(exdate - date)                                as min_dte,
       max(exdate - date)                                as max_dte,
       sum(volume)                                       as tot_volume,
       sum(case when exdate - date = 0 then volume end)  as vol_dte0,
       sum(case when exdate - date = 1 then volume end)  as vol_dte1,
       count(*) filter (where exdate - date = 0)         as n_rows_dte0,
       count(*) filter (where exdate - date = 1)         as n_rows_dte1,
       count(*) filter (where exdate - date < 0)         as n_rows_dte_negative
from optionm.opprcd2024
where secid = any(%(s)s)
group by secid order by secid
"""
t0 = time.time()
df = db.raw_sql(sql, params={"s": [float(x) for x in CANDIDATES]})
el = time.time() - t0
print("query wall clock: %.1fs" % el)

df["share_vol_dte0"] = df.vol_dte0 / df.tot_volume
df["share_vol_dte1"] = df.vol_dte1 / df.tot_volume
print(df.to_string(index=False))
df.to_csv(os.path.join(OUT_DIR, "step2c_opprcd2024.csv"), index=False)
dump_json("step2c_opprcd2024.json",
          {"seconds": round(el, 2), "rows": df.to_dict("records")})
print("\ncandidate secids absent from opprcd2024: %s"
      % sorted(set(CANDIDATES) - set(int(x) for x in df.secid)))
db.close()
