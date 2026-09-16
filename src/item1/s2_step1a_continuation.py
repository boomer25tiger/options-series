"""Step 1a: search for a gold or silver class that continues past 2022-12-28 (A5).

The A5 continuation rule: a candidate class is accepted only if, on the overlap
2008-12-08 to 2022-12-28, its F1 and F2 match the class 335 / 3607 construction within
0.5 percent on at least 95 percent of dates.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import connect, log_to, dump_json, cols_of, dpath, opath
import pandas as pd
pd.set_option("display.width", 330); pd.set_option("display.max_rows", 400)
pd.set_option("display.max_colwidth", 46)

log_to("s2_step1a_continuation.log")
db = connect()
out = {}

# What identifies an exchange in these tables? dsfutcontr has no exchange name column;
# report what is available so the search criterion is auditable.
print("===== tr_ds_fut.dsfutcontr columns =====")
print(cols_of(db, "tr_ds_fut", "dsfutcontr").to_string(index=False))
print("\n===== tr_ds_fut.dsfutclass columns =====")
print(cols_of(db, "tr_ds_fut", "dsfutclass").to_string(index=False))

print("\n===== every class whose CONTRACT name contains GOLD or SILVER =====")
cand = db.raw_sql("""
    select f.clscode, f.dsclsid, f.trdplatformcode, f.trdstatcode,
           d.contrcode, d.dscontrid, d.contrname, d.exchtickersymb, d.srccode,
           count(i.futcode) as n_contracts,
           min(i.lasttrddate) as min_lasttrd,
           max(i.lasttrddate) as max_lasttrd
    from tr_ds_fut.dsfutclass f
    join tr_ds_fut.dsfutcontr d on d.contrcode = f.contrcode
    left join tr_ds_fut.dsfutcontrinfo i on i.clscode = f.clscode
    where d.contrname ilike '%%GOLD%%' or d.contrname ilike '%%SILVER%%'
    group by 1,2,3,4,5,6,7,8,9
    order by max_lasttrd desc nulls last""")
print("classes found: %d" % len(cand))
print(cand.to_string(index=False))
out["all_gold_silver_classes"] = cand.to_dict("records")

# Exchange marker: the prefix Datastream puts on the continuous-series name for the class.
print("\n===== exchange marker per candidate class, from the continuous-series name prefix =====")
codes = [float(x) for x in cand.clscode.dropna().unique()]
pref = db.raw_sql("""select clscode,
                            substring(calcseriesname from '^[A-Z]+') as name_prefix,
                            count(*) as n_series, min(calcseriesname) as example
                     from tr_ds_fut.wrds_cseries_info
                     where clscode = any(%(c)s) group by 1,2 order by 1""",
                  params={"c": codes})
print(pref.to_string(index=False) if len(pref) else "(no continuous series on any of these classes)")
out["exchange_prefix"] = pref.to_dict("records")

EXCH = ("CMX", "NYM", "NYL", "COMEX", "NYMEX")
keep = set(pref.loc[pref.name_prefix.isin(EXCH), "clscode"]) if len(pref) else set()
print("\nclasses whose series prefix marks COMEX/NYMEX (%s): %s"
      % ("/".join(EXCH), sorted(keep) or "none"))

print("\n===== candidates that continue past 2022-12-28 =====")
cand["max_lasttrd"] = pd.to_datetime(cand["max_lasttrd"])
live = cand[(cand.max_lasttrd > pd.Timestamp("2022-12-28")) & (cand.n_contracts > 0)]
print("classes with any contract last trading after 2022-12-28: %d" % len(live))
print(live.to_string(index=False) if len(live) else "(none)")
out["continue_past_2022"] = live.to_dict("records")

# For each such class, does the VALUE table actually hold data after 2022-12-28?
print("\n===== value-table coverage after 2022-12-28 for those classes =====")
rows = []
for r in live.itertuples():
    v = db.raw_sql("""select count(*) as n, min(date_) as mn, max(date_) as mx,
                             count(distinct v.futcode) as n_fut
                      from tr_ds_fut.dsfutcontrval v
                      join tr_ds_fut.dsfutcontrinfo i on i.futcode = v.futcode
                      where i.clscode = %(c)s and v.date_ > '2022-12-28'""",
                   params={"c": float(r.clscode)})
    rows.append({"clscode": r.clscode, "dsclsid": r.dsclsid, "contrname": r.contrname,
                 "exchtickersymb": r.exchtickersymb,
                 "rows_after_2022": int(v.n[0]),
                 "min": str(v.mn[0]), "max": str(v.mx[0]),
                 "n_futcodes": int(v.n_fut[0]),
                 "prefix_marks_comex_nymex": float(r.clscode) in keep})
    print("clscode %7.0f %-6s %-34s ticker=%-8s rows after 2022-12-28=%7d  %s .. %s  "
          "futcodes=%4d  COMEX/NYMEX prefix=%s"
          % (r.clscode, r.dsclsid, str(r.contrname)[:34], str(r.exchtickersymb),
             int(v.n[0]), v.mn[0], v.mx[0], int(v.n_fut[0]), float(r.clscode) in keep))
out["value_coverage_after_2022"] = rows

dump_json("s2_step1a_continuation.json", out)
db.close()
