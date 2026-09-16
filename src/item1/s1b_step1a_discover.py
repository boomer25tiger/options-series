"""Step 1a: column lists, contract inventory per class, and series code resolution."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import connect, log_to, dump_json, cols_of
import pandas as pd
pd.set_option("display.width", 320); pd.set_option("display.max_rows", 400)
pd.set_option("display.max_colwidth", 46)

log_to("s1b_step1a_discover.log")
db = connect()
out = {}

TABLES = ["dsfutcontr", "dsfutcontrinfo", "dsfutcontrval", "wrds_fut_contract",
          "dsfutcalcserval"]
out["columns"] = {}
for t in TABLES:
    c = cols_of(db, "tr_ds_fut", t)
    print("\n===== tr_ds_fut.%s =====" % t)
    print(c.to_string(index=False))
    out["columns"]["tr_ds_fut." + t] = c.to_dict("records")

CLS = {"GC": 335.0, "SI": 3607.0, "CL": 1482.0, "NG": 1539.0}
NAME = {"GC": "NYL-GOLD 100 OZ", "SI": "NYL-SILVER 5000 OZ",
        "CL": "NYM-LIGHT CRUDE OIL", "NG": "NYM-NATURAL GAS"}

print("\n\n===== individual contracts per class (dsfutcontrinfo) =====")
out["contracts"] = {}
for code, cls in CLS.items():
    n = db.raw_sql("select count(*) as n from tr_ds_fut.dsfutcontrinfo where clscode=%(c)s",
                   params={"c": cls})
    d = db.raw_sql("""select count(*) as n,
                             count(lasttrddate) as nn_lasttrd,
                             count(expirationdate) as nn_expiry,
                             count(sttlmntdate) as nn_settle,
                             count(firstnoticedate) as nn_firstnotice,
                             min(lasttrddate) as min_lasttrd, max(lasttrddate) as max_lasttrd,
                             min(expirationdate) as min_exp, max(expirationdate) as max_exp,
                             count(distinct contrdate) as n_contrdate
                      from tr_ds_fut.dsfutcontrinfo where clscode=%(c)s""",
                   params={"c": cls})
    print("\n--- %s (%s), clscode %d ---" % (code, NAME[code], cls))
    print(d.to_string(index=False))
    out["contracts"][code] = {"clscode": cls, "name": NAME[code],
                              "n_contracts": int(n.n[0]), "summary": d.to_dict("records")[0]}
    s = db.raw_sql("""select futcode, dsmnem, contrdate, contrdatefmt, trdstatcode,
                             startdate, lasttrddate, sttlmntdate, expirationdate,
                             firstnoticedate, isocurrcode
                      from tr_ds_fut.dsfutcontrinfo where clscode=%(c)s
                      order by lasttrddate limit 6""", params={"c": cls})
    print("first 6 by lasttrddate:")
    print(s.to_string(index=False))

print("\n\n===== continuous series codes (TRc1/TRc2 and the CS family) =====")
MNEMS = {"GC": ["CZGC.01", "CZGC.02", "CZGCS00", "CZGCS01"],
         "SI": ["CZIC.01", "CZIC.02", "CZICS00", "CZICS01"],
         "CL": ["NCLC.01", "NCLC.02", "NCLCS00", "NCLCS01"],
         "NG": ["NNGC.01", "NNGC.02", "NNGCS00", "NNGCS01"]}
out["series"] = {}
allm = [m for v in MNEMS.values() for m in v]
df = db.raw_sql("""select calcseriescode, clscode, dsmnem, calcseriesname, rollmethodcode,
                          rollmethoddesc, positionfwdcode, positionfwddesc, calcmthcode
                   from tr_ds_fut.wrds_cseries_info where dsmnem = any(%(m)s)
                   order by dsmnem""", params={"m": allm})
print(df.to_string(index=False))
found = set(df.dsmnem)
print("\nrequested but NOT present: %s" % sorted(set(allm) - found))
out["series"]["rows"] = df.to_dict("records")
out["series"]["missing"] = sorted(set(allm) - found)
out["series"]["requested"] = MNEMS

print("\n\n===== value-table row counts for those series (dsfutcalcserval) =====")
rows = []
for r in df.itertuples():
    v = db.raw_sql("""select count(*) as n, min(date_) as mn, max(date_) as mx,
                             count(settlement) as nn_settle
                      from tr_ds_fut.dsfutcalcserval where calcseriescode=%(c)s""",
                   params={"c": float(r.calcseriescode)})
    rows.append({"dsmnem": r.dsmnem, "calcseriescode": r.calcseriescode,
                 "rows": int(v.n[0]), "min": str(v.mn[0]), "max": str(v.mx[0]),
                 "nn_settlement": int(v.nn_settle[0])})
    print("%-9s code=%-8.0f rows=%6d  %s .. %s  settlement non-null=%d"
          % (r.dsmnem, r.calcseriescode, int(v.n[0]), v.mn[0], v.mx[0], int(v.nn_settle[0])))
out["series"]["value_counts"] = rows

dump_json("s1b_step1a_discover.json", out)
db.close()
