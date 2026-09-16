"""Step 1c: verify TRc1 / TRc2 identity against individual-contract data (A2).

Two reference conventions are built from the contract data on every SPX trade date in
the common window:

  X  nearest contract whose expiry date is ON OR AFTER the date
  Y  nearest contract whose expiry date is STRICTLY AFTER the date

and the same for the second-nearest. `expirationdate` is null for every contract in all
four classes, so the expiry date used is `lasttrddate`; `sttlmntdate` is reported as a
cross-check.

Pass rule, fixed by the session instruction before any number was seen: a pair is
verified if TRc1 and TRc2 each match their reference under the SAME convention within
0.5 percent on at least 95 percent of dates, and TRc2 switches on the same day as TRc1
on at least 95 percent of TRc1 switches.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import (connect, log_to, dump_json, dpath, opath,
                          COMMON_START, COMMON_END, SECIDS)
import numpy as np
import pandas as pd
pd.set_option("display.width", 320); pd.set_option("display.max_rows", 300)

log_to("s1b_step1c_verify.log")
TOL = 0.005          # 0.5 percent
MATCH_FLOOR = 0.95   # pass rule
SWITCH_FLOOR = 0.95  # pass rule

db = connect()
frames = []
for yr in range(2008, 2026):
    frames.append(db.raw_sql(
        "select date from optionm.secprd%d where secid=%%(s)s and date between %%(a)s and %%(b)s"
        % yr, params={"s": float(SECIDS["SPX"]), "a": COMMON_START, "b": COMMON_END}))
db.close()
spx = pd.to_datetime(pd.concat(frames, ignore_index=True)["date"]).sort_values()
SPX_DATES = pd.DatetimeIndex(spx.unique())
print("SPX trade dates in the common window: %d" % len(SPX_DATES))

CLASSES = {"GC": ("CZGC.01", "CZGC.02", "CZGCS01"),
           "SI": ("CZIC.01", "CZIC.02", "CZICS01"),
           "CL": ("NCLC.01", "NCLC.02", None),
           "NG": ("NNGC.01", "NNGC.02", "NNGCS01")}

def load_series(mn):
    if mn is None:
        return None
    d = pd.read_parquet(dpath("dsser_%s.parquet" % mn.replace(".", "_")))
    if not len(d):
        return d
    d["date"] = pd.to_datetime(d["date"])
    return d[["date", "settlement"]].dropna(subset=["settlement"]).set_index("date")["settlement"]

out = {"spx_trade_dates": len(SPX_DATES), "tolerance": TOL,
       "match_floor": MATCH_FLOOR, "switch_floor": SWITCH_FLOOR, "classes": {}}

for code, (m1, m2, mcs) in CLASSES.items():
    print("\n\n################ %s ################" % code)
    con = pd.read_parquet(dpath("dsfut_contracts_%s.parquet" % code.lower()))
    val = pd.read_parquet(dpath("dsfut_contractval_%s.parquet" % code.lower()))
    con["lasttrddate"] = pd.to_datetime(con["lasttrddate"])
    con["sttlmntdate"] = pd.to_datetime(con["sttlmntdate"])
    val["date"] = pd.to_datetime(val["date"])
    exp = con.dropna(subset=["lasttrddate"]).set_index("futcode")["lasttrddate"]
    same = int((con.lasttrddate == con.sttlmntdate).sum())
    print("contracts %d ; lasttrddate non-null %d ; sttlmntdate equals lasttrddate on %d ; "
          "expirationdate non-null %d"
          % (len(con), int(con.lasttrddate.notna().sum()), same,
             int(con.expirationdate.notna().sum())))
    print("contract value rows %s, %s .. %s"
          % ("{:,}".format(len(val)), val.date.min().date(), val.date.max().date()))

    v = val.dropna(subset=["settlement"]).copy()
    v["expiry"] = v.futcode.map(exp)
    v = v.dropna(subset=["expiry"])
    by_date = {d: g for d, g in v.groupby("date")}

    # reference series under both conventions
    ref = {}
    for conv, strict in (("X", False), ("Y", True)):
        r1f, r1s, r2f, r2s, dts = [], [], [], [], []
        for d in SPX_DATES:
            g = by_date.get(d)
            if g is None:
                continue
            gg = g[g.expiry > d] if strict else g[g.expiry >= d]
            if len(gg) < 2:
                continue
            gg = gg.sort_values(["expiry", "futcode"])
            dts.append(d)
            r1f.append(gg.futcode.iloc[0]); r1s.append(gg.settlement.iloc[0])
            r2f.append(gg.futcode.iloc[1]); r2s.append(gg.settlement.iloc[1])
        ref[conv] = pd.DataFrame({"date": dts, "f1": r1f, "s1": r1s, "f2": r2f, "s2": r2s})
        print("convention %s: reference built on %d SPX trade dates" % (conv, len(ref[conv])))

    s1 = load_series(m1)
    s2 = load_series(m2)
    scs = load_series(mcs)
    rec = {"n_contracts": len(con), "contract_val_rows": len(val),
           "contract_val_min": str(val.date.min().date()),
           "contract_val_max": str(val.date.max().date()),
           "lasttrd_eq_sttlmnt": same,
           "expirationdate_nonnull": int(con.expirationdate.notna().sum()),
           "series": {"TRc1": m1, "TRc2": m2, "CS": mcs},
           "trc1_rows": 0 if s1 is None or not len(s1) else len(s1),
           "trc2_rows": 0 if s2 is None or not len(s2) else len(s2),
           "conventions": {}}

    for conv in ("X", "Y"):
        R = ref[conv]
        block = {}
        for lab, ser, fcol, scol in (("TRc1", s1, "f1", "s1"), ("TRc2", s2, "f2", "s2")):
            if ser is None or not len(ser):
                block[lab] = {"n": 0, "note": "series is empty in dsfutcalcserval"}
                print("  %s %s: series empty, nothing to compare" % (conv, lab))
                continue
            m = R.merge(ser.rename("trc"), left_on="date", right_index=True, how="inner")
            m = m.dropna(subset=["trc", scol])
            if not len(m):
                block[lab] = {"n": 0, "note": "no overlapping dates"}
                continue
            rel = (m["trc"] - m[scol]).abs() / m[scol].abs().replace(0, np.nan)
            exact = (m["trc"] == m[scol])
            within = rel <= TOL
            mism = m.loc[~within.fillna(True), ["date", fcol, scol]].copy()
            mism["trc"] = m.loc[~within.fillna(True), "trc"].values
            mism["rel_diff"] = rel[~within.fillna(True)].values
            block[lab] = {
                "n": int(len(m)),
                "share_exact": float(exact.mean()),
                "share_within_0.5pct": float(within.mean()),
                "median_rel_diff": float(rel.median()),
                "n_mismatch": int((~within.fillna(True)).sum()),
                "mismatches": [{"date": str(r.date.date()), "futcode": float(getattr(r, fcol)),
                                "reference_settle": float(getattr(r, scol)),
                                "series_value": float(r.trc), "rel_diff": float(r.rel_diff)}
                               for r in mism.head(50).itertuples()],
            }
            print("  %s %-5s vs reference: n=%4d  exact=%.4f  within 0.5%%=%.4f  "
                  "median |rel diff|=%.6f  mismatches=%d"
                  % (conv, lab, len(m), exact.mean(), within.mean(), rel.median(),
                     int((~within.fillna(True)).sum())))
        rec["conventions"][conv] = block
    out["classes"][code] = rec

dump_json("s1b_step1c_verify.json", out)
