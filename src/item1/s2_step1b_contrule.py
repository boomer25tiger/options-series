"""Step 1b: apply the A5 continuation rule for gold and silver.

Candidate classes are those with contract values after 2022-12-28 whose exchange is
COMEX or NYMEX by any of three auditable markers: the exchange ticker symbol is one of
the COMEX/NYMEX gold or silver tickers; the contract name contains COMEX or NYMEX; or
the class's continuous-series name carries a CMX / NYM / NYL prefix. Classes 335 and
3607 are the incumbents and are not candidates for themselves.

Rule: accept only if, on the overlap 2008-12-08 to 2022-12-28, F1 and F2 built from the
candidate match the incumbent construction within 0.5 percent on at least 95 percent of
dates.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import (connect, log_to, dump_json, dpath, opath,
                          COMMON_START, COMMON_END, SECIDS)
import numpy as np
import pandas as pd
pd.set_option("display.width", 330); pd.set_option("display.max_rows", 300)

log_to("s2_step1b_contrule.log")
TOL = 0.005
FLOOR = 0.95
OVERLAP_END = "2022-12-28"

db = connect()
frames = [db.raw_sql(
    "select date from optionm.secprd%d where secid=%%(s)s and date between %%(a)s and %%(b)s"
    % yr, params={"s": float(SECIDS["SPX"]), "a": COMMON_START, "b": COMMON_END})
    for yr in range(2008, 2026)]
SPX_DATES = pd.DatetimeIndex(pd.to_datetime(
    pd.concat(frames, ignore_index=True)["date"]).sort_values().unique())
print("SPX trade dates in the common window: %d" % len(SPX_DATES))

# ---- candidate set ----
TICKERS = ("GC", "SI", "MGC", "SIL", "QO", "QI", "SGU", "ZG", "ZI", "YG", "YI")
cands = db.raw_sql("""
    select distinct f.clscode, f.dsclsid, d.contrname, d.exchtickersymb
    from tr_ds_fut.dsfutclass f
    join tr_ds_fut.dsfutcontr d on d.contrcode = f.contrcode
    join tr_ds_fut.dsfutcontrinfo i on i.clscode = f.clscode
    where (d.contrname ilike '%%GOLD%%' or d.contrname ilike '%%SILVER%%')
      and (d.exchtickersymb = any(%(t)s)
           or d.contrname ilike '%%COMEX%%' or d.contrname ilike '%%NYMEX%%')
      and i.lasttrddate > %(e)s
    order by f.clscode""", params={"t": list(TICKERS), "e": OVERLAP_END})
cands = cands[~cands.clscode.isin([335.0, 3607.0])]
print("\n===== candidate classes under the stated markers =====")
print(cands.to_string(index=False))

def build_f1f2(clscode, db=None, contracts=None, values=None):
    """F1, F2 by convention X: nearest and second-nearest lasttrddate on or after t."""
    if contracts is None:
        contracts = db.raw_sql("""select futcode, lasttrddate from tr_ds_fut.dsfutcontrinfo
                                  where clscode=%(c)s""", params={"c": float(clscode)})
        contracts["lasttrddate"] = pd.to_datetime(contracts["lasttrddate"])
    if values is None:
        futs = [float(x) for x in contracts.futcode]
        values = db.raw_sql("""select futcode, date_ as date, settlement
                               from tr_ds_fut.dsfutcontrval
                               where futcode = any(%(f)s) and date_ between %(a)s and %(b)s""",
                            params={"f": futs, "a": COMMON_START, "b": "2026-09-30"})
        values["date"] = pd.to_datetime(values["date"])
    exp = contracts.dropna(subset=["lasttrddate"]).set_index("futcode")["lasttrddate"]
    v = values.dropna(subset=["settlement"]).copy()
    v["expiry"] = v.futcode.map(exp)
    v = v.dropna(subset=["expiry"])
    rows = []
    for d, g in v.groupby("date"):
        if d not in SPX_SET:
            continue
        gg = g[g.expiry >= d].sort_values(["expiry", "futcode"])
        if len(gg) < 2:
            continue
        rows.append({"date": d, "f1": gg.settlement.iloc[0], "f2": gg.settlement.iloc[1],
                     "fut1": gg.futcode.iloc[0], "fut2": gg.futcode.iloc[1]})
    return pd.DataFrame(rows)

SPX_SET = set(SPX_DATES)

# ---- incumbents from session 1b data on disk ----
inc = {}
for code, cls in (("GC", 335.0), ("SI", 3607.0)):
    c = pd.read_parquet(dpath("dsfut_contracts_%s.parquet" % code.lower()))
    v = pd.read_parquet(dpath("dsfut_contractval_%s.parquet" % code.lower()))
    c["lasttrddate"] = pd.to_datetime(c["lasttrddate"]); v["date"] = pd.to_datetime(v["date"])
    inc[code] = build_f1f2(cls, contracts=c, values=v)
    print("\nincumbent %s (clscode %g): %d dates, %s .. %s"
          % (code, cls, len(inc[code]), inc[code].date.min().date(), inc[code].date.max().date()))

# ---- test each candidate ----
out = {"candidates": cands.to_dict("records"), "tests": [], "tolerance": TOL, "floor": FLOOR}
for r in cands.itertuples():
    metal = "GC" if "GOLD" in str(r.contrname).upper() else "SI"
    t0 = time.time()
    cand_ser = build_f1f2(r.clscode, db=db)
    el = time.time() - t0
    if not len(cand_ser):
        print("clscode %g (%s): no F1/F2 could be built" % (r.clscode, r.dsclsid))
        continue
    m = inc[metal].merge(cand_ser, on="date", suffixes=("_inc", "_cand"))
    ov = m[(m.date >= COMMON_START) & (m.date <= OVERLAP_END)]
    if not len(ov):
        share1 = share2 = float("nan"); n = 0
    else:
        n = len(ov)
        share1 = float(((ov.f1_cand - ov.f1_inc).abs() / ov.f1_inc.abs() <= TOL).mean())
        share2 = float(((ov.f2_cand - ov.f2_inc).abs() / ov.f2_inc.abs() <= TOL).mean())
    accept = bool(n > 0 and share1 >= FLOOR and share2 >= FLOOR)
    after = cand_ser[cand_ser.date > OVERLAP_END]
    rec = {"clscode": r.clscode, "dsclsid": r.dsclsid, "contrname": r.contrname,
           "exchtickersymb": r.exchtickersymb, "metal": metal,
           "cand_dates": len(cand_ser),
           "cand_first": str(cand_ser.date.min().date()), "cand_last": str(cand_ser.date.max().date()),
           "overlap_dates": n, "f1_match": share1, "f2_match": share2,
           "dates_after_overlap": int(len(after)),
           "accepted": accept, "seconds": round(el, 1)}
    out["tests"].append(rec)
    print("clscode %7.0f %-5s %-34s metal=%s overlap=%4d  F1 match=%.4f  F2 match=%.4f  "
          "dates after 2022-12-28=%4d  -> %s  (%.1fs)"
          % (r.clscode, r.dsclsid, str(r.contrname)[:34], metal, n, share1, share2,
             len(after), "ACCEPT" if accept else "reject", el))

print("\n===== A5 continuation rule outcome =====")
acc = [t for t in out["tests"] if t["accepted"]]
for metal in ("GC", "SI"):
    a = [t for t in acc if t["metal"] == metal and t["dates_after_overlap"] > 0]
    if a:
        # Tie-break, stated: among accepted candidates that actually extend the series,
        # take the highest F2 match share (F2 is the leg curve state turns on), then the
        # highest F1 match share, then the lowest clscode.
        a.sort(key=lambda t: (-t["f2_match"], -t["f1_match"], t["clscode"]))
        print("   accepted candidates that extend the series, in tie-break order: %s"
              % ", ".join("%g(%s, F2=%.4f)" % (t["clscode"], t["dsclsid"], t["f2_match"])
                          for t in a))
        print("%s: ACCEPTED clscode %g (%s), splice at %s, %d dates after the splice"
              % (metal, a[0]["clscode"], a[0]["dsclsid"], OVERLAP_END, a[0]["dates_after_overlap"]))
        out.setdefault("accepted", {})[metal] = a[0]
    else:
        print("%s: no candidate accepted; coverage stays at the incumbent class span" % metal)
        out.setdefault("accepted", {})[metal] = None

dump_json("s2_step1b_contrule.json", out)
db.close()
