"""Step 1b: pull individual contracts and their settlement history, plus the
continuous series (TRc1, TRc2 and the CS family) for the four classes."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import connect, log_to, dump_json, dpath
import pandas as pd
pd.set_option("display.width", 320); pd.set_option("display.max_rows", 200)

BUDGET_PER_CLASS = 20 * 60  # session instruction

log_to("s1b_step1b_pull.log")
db = connect()

CLS = {"GC": 335.0, "SI": 3607.0, "CL": 1482.0, "NG": 1539.0}
VAL_START, VAL_END = "2008-06-01", "2025-09-30"
SERIES = {  # dsmnem -> calcseriescode, resolved in step 1a
    "CZGC.01": 18502.0, "CZGC.02": 18503.0, "CZGCS00": 6815.0, "CZGCS01": 9921.0,
    "CZIC.01": 18505.0, "CZIC.02": 17168.0, "CZICS00": 2408.0, "CZICS01": 11932.0,
    "NCLC.01": 28020.0, "NCLC.02": 28019.0,
    "NNGC.01": 18337.0, "NNGC.02": 18338.0, "NNGCS01": 3372.0,
}

out = {"contracts": {}, "values": {}, "series": {}, "budget_per_class": BUDGET_PER_CLASS}
skipped = []
for code, cls in CLS.items():
    t0 = time.time()
    c = db.raw_sql("""select futcode, contrcode, clscode, dsmnem, contrdate, contrdatefmt,
                             trdstatcode, startdate, lasttrddate, sttlmntdate,
                             expirationdate, firstnoticedate, lastnoticedate,
                             firstdelvrydate, isocurrcode
                      from tr_ds_fut.dsfutcontrinfo where clscode=%(c)s
                      order by lasttrddate""", params={"c": cls})
    for dc in ["contrdate"]:
        pass
    for dc in ["startdate", "lasttrddate", "sttlmntdate", "expirationdate",
               "firstnoticedate", "lastnoticedate", "firstdelvrydate"]:
        c[dc] = pd.to_datetime(c[dc])
    c.to_parquet(dpath("dsfut_contracts_%s.parquet" % code.lower()), index=False)
    t_c = time.time() - t0

    futs = [float(x) for x in c.futcode]
    t1 = time.time()
    v = db.raw_sql("""select futcode, date_ as date, settlement, volume, openinterest
                      from tr_ds_fut.dsfutcontrval
                      where futcode = any(%(f)s) and date_ between %(a)s and %(b)s""",
                   params={"f": futs, "a": VAL_START, "b": VAL_END})
    v["date"] = pd.to_datetime(v["date"])
    v.to_parquet(dpath("dsfut_contractval_%s.parquet" % code.lower()), index=False)
    t_v = time.time() - t1
    el = time.time() - t0

    print("%-3s clscode %6.0f : %3d contracts (%.1fs) ; %s value rows %s..%s (%.1fs) ; total %.1fs"
          % (code, cls, len(c), t_c, "{:,}".format(len(v)),
             v.date.min().date() if len(v) else "-", v.date.max().date() if len(v) else "-",
             t_v, el))
    out["contracts"][code] = {
        "clscode": cls, "n_contracts": len(c), "seconds": round(t_c, 2),
        "lasttrddate_min": str(c.lasttrddate.min().date()),
        "lasttrddate_max": str(c.lasttrddate.max().date()),
        "nn_lasttrddate": int(c.lasttrddate.notna().sum()),
        "nn_sttlmntdate": int(c.sttlmntdate.notna().sum()),
        "nn_expirationdate": int(c.expirationdate.notna().sum()),
        "nn_firstnoticedate": int(c.firstnoticedate.notna().sum()),
        "lasttrd_equals_sttlmnt": int((c.lasttrddate == c.sttlmntdate).sum()),
    }
    out["values"][code] = {
        "rows": len(v), "seconds": round(t_v, 2),
        "min_date": str(v.date.min().date()) if len(v) else None,
        "max_date": str(v.date.max().date()) if len(v) else None,
        "n_futcodes_with_data": int(v.futcode.nunique()),
        "nn_settlement": int(v.settlement.notna().sum()),
    }
    if el > BUDGET_PER_CLASS:
        print("   *** class %s exceeded the %d s budget ***" % (code, BUDGET_PER_CLASS))
        skipped.append(code)

print("\n===== continuous series =====")
for mn, cscode in SERIES.items():
    t0 = time.time()
    s = db.raw_sql("""select date_ as date, settlement, volume, openinterest
                      from tr_ds_fut.dsfutcalcserval where calcseriescode=%(c)s
                      order by date_""", params={"c": cscode})
    el = time.time() - t0
    if len(s):
        s["date"] = pd.to_datetime(s["date"])
    s.to_parquet(dpath("dsser_%s.parquet" % mn.replace(".", "_")), index=False)
    out["series"][mn] = {"calcseriescode": cscode, "rows": len(s),
                         "seconds": round(el, 2),
                         "min_date": str(s.date.min().date()) if len(s) else None,
                         "max_date": str(s.date.max().date()) if len(s) else None,
                         "nn_settlement": int(s.settlement.notna().sum()) if len(s) else 0}
    print("%-9s code=%-8.0f rows=%6d  %s .. %s  (%.1fs)"
          % (mn, cscode, len(s), out["series"][mn]["min_date"],
             out["series"][mn]["max_date"], el))

out["classes_over_budget"] = skipped
dump_json("s1b_step1b_pull.json", out)
db.close()
