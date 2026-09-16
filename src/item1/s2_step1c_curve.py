"""Step 1c: build F1, F2, s_t and z_t under A5, re-run the section 9 kill check."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import (connect, log_to, dump_json, load_json, dpath, opath,
                          COMMON_START, COMMON_END, SECIDS)
import numpy as np
import pandas as pd
pd.set_option("display.width", 330); pd.set_option("display.max_rows", 300)

log_to("s2_step1c_curve.log")
COVERAGE_FLOOR = 0.80
SPLICE = pd.Timestamp("2022-12-28")

db = connect()
frames = [db.raw_sql(
    "select date from optionm.secprd%d where secid=%%(s)s and date between %%(a)s and %%(b)s"
    % yr, params={"s": float(SECIDS["SPX"]), "a": COMMON_START, "b": COMMON_END})
    for yr in range(2008, 2026)]
SPX_DATES = pd.DatetimeIndex(pd.to_datetime(
    pd.concat(frames, ignore_index=True)["date"]).sort_values().unique())
N_SPX = len(SPX_DATES)
SPX_SET = set(SPX_DATES)
print("SPX trade dates in the common window: %d" % N_SPX)

cont = load_json("s2_step1b_contrule.json")["accepted"]

INCUMBENT = {"GC": 335.0, "SI": 3607.0, "CL": 1482.0, "NG": 1539.0}
LABEL = {"GC": "COMEX gold (GLD)", "SI": "COMEX silver (SLV)",
         "CL": "NYMEX WTI light sweet crude (USO)", "NG": "NYMEX Henry Hub natural gas (UNG)"}


def f1f2_from(contracts, values, tag):
    exp = contracts.dropna(subset=["lasttrddate"]).set_index("futcode")["lasttrddate"]
    v = values.copy()
    v["expiry"] = v.futcode.map(exp)
    v = v.dropna(subset=["expiry"])
    rows, null_drops = [], 0
    for d, g in v.groupby("date"):
        if d not in SPX_SET:
            continue
        gg = g[g.expiry >= d].sort_values(["expiry", "futcode"])
        if len(gg) < 2:
            continue
        s1, s2 = gg.settlement.iloc[0], gg.settlement.iloc[1]
        if pd.isna(s1) or pd.isna(s2):
            null_drops += 1
            continue
        rows.append({"date": d, "f1": float(s1), "f2": float(s2),
                     "fut1": gg.futcode.iloc[0], "fut2": gg.futcode.iloc[1], "source": tag})
    return pd.DataFrame(rows), null_drops


def pull_class(clscode):
    c = db.raw_sql("select futcode, lasttrddate from tr_ds_fut.dsfutcontrinfo where clscode=%(c)s",
                   params={"c": float(clscode)})
    c["lasttrddate"] = pd.to_datetime(c["lasttrddate"])
    futs = [float(x) for x in c.futcode]
    v = db.raw_sql("""select futcode, date_ as date, settlement from tr_ds_fut.dsfutcontrval
                      where futcode = any(%(f)s) and date_ between %(a)s and %(b)s""",
                   params={"f": futs, "a": COMMON_START, "b": COMMON_END})
    v["date"] = pd.to_datetime(v["date"])
    return c, v


curves, meta = {}, {}
for code, cls in INCUMBENT.items():
    t0 = time.time()
    c = pd.read_parquet(dpath("dsfut_contracts_%s.parquet" % code.lower()))
    v = pd.read_parquet(dpath("dsfut_contractval_%s.parquet" % code.lower()))
    c["lasttrddate"] = pd.to_datetime(c["lasttrddate"]); v["date"] = pd.to_datetime(v["date"])
    base, nulls = f1f2_from(c, v, "class %g" % cls)
    spliced_at = None
    if code in ("GC", "SI") and cont.get(code):
        newcls = cont[code]["clscode"]
        c2, v2 = pull_class(newcls)
        ext, n2 = f1f2_from(c2, v2, "class %g" % newcls)
        ext = ext[ext.date > SPLICE]
        nulls += n2
        base = pd.concat([base[base.date <= SPLICE], ext], ignore_index=True)
        spliced_at = str(SPLICE.date())
        print("%s: spliced class %g into class %g at %s (+%d dates)"
              % (code, newcls, cls, spliced_at, len(ext)))
    base = base.sort_values("date").reset_index(drop=True)
    base["switch"] = base.fut1 != base.fut1.shift(1)
    base.loc[0, "switch"] = False
    curves[code] = base
    meta[code] = {"label": LABEL[code], "incumbent_clscode": cls,
                  "continuation_clscode": cont[code]["clscode"] if (code in ("GC", "SI") and cont.get(code)) else None,
                  "spliced_at": spliced_at,
                  "dates_built": len(base),
                  "dates_dropped_null_settlement": int(nulls),
                  "first_date": str(base.date.min().date()),
                  "last_date": str(base.date.max().date()),
                  "coverage_share": round(len(base) / N_SPX, 4),
                  "front_switches": int(base.switch.sum()),
                  "seconds": round(time.time() - t0, 1)}
    print("%-3s dates built=%4d  dropped for null settlement=%3d  %s .. %s  coverage=%.4f  "
          "front switches=%3d" % (code, len(base), nulls, meta[code]["first_date"],
                                  meta[code]["last_date"], meta[code]["coverage_share"],
                                  meta[code]["front_switches"]))
db.close()

print("\n===== section 9 kill check on the A5 series =====")
print("SPX trade dates %d ; 80 percent floor %.1f" % (N_SPX, COVERAGE_FLOOR * N_SPX))
kk = []
for code in ["GC", "SI", "CL", "NG"]:
    m = meta[code]
    ok = m["coverage_share"] >= COVERAGE_FLOOR
    kk.append({"commodity": code, "underlying_for": LABEL[code],
               "coverage_share": m["coverage_share"], "clears_80pct": ok,
               "spliced_at": m["spliced_at"],
               "outcome": "RETAINED" if ok else "DROPPED"})
k = pd.DataFrame(kk)
print(k.to_string(index=False))
n_drop = int((k.outcome == "DROPPED").sum())
print("\ncurve state RETAINED for %d of 4, DROPPED for %d" % (4 - n_drop, n_drop))

print("\n===== s_t and z_t (section 6.5, A5) =====")
allc = []
for code in ["GC", "SI", "CL", "NG"]:
    d = curves[code].copy()
    d["commodity"] = code
    d["spread"] = d.f2 - d.f1
    d["s_t"] = np.where(d.spread > 0, "contango",
                        np.where(d.spread < 0, "backwardation", "equal"))
    n_eq = int((d.s_t == "equal").sum())
    d["z_raw"] = d.spread / d.f1
    # section 6.5: 2020-04-20 dropped from z_t for CL because F1 is negative
    excluded_2020 = False
    if code == "CL":
        hit = d.date == pd.Timestamp("2020-04-20")
        excluded_2020 = bool(hit.any())
        neg = bool((d.loc[hit, "f1"] < 0).any()) if hit.any() else False
        d.loc[hit, "z_raw"] = np.nan
        print("CL: 2020-04-20 present=%s, F1 negative there=%s, z_t set to null there"
              % (excluded_2020, neg))
    lo, hi = d.z_raw.quantile([0.01, 0.99])
    d["z_t"] = d.z_raw.clip(lo, hi)
    n_cont = int((d.s_t == "contango").sum()); n_back = int((d.s_t == "backwardation").sum())
    tot = len(d)
    print("%-3s n=%4d  contango=%.4f  backwardation=%.4f  equal(dropped from s_t)=%d  "
          "winsor bounds [%.6f, %.6f]  z_t non-null=%d"
          % (code, tot, n_cont / tot, n_back / tot, n_eq, lo, hi, int(d.z_t.notna().sum())))
    meta[code].update({"n_contango": n_cont, "n_backwardation": n_back, "n_equal": n_eq,
                       "share_contango": round(n_cont / tot, 4),
                       "share_backwardation": round(n_back / tot, 4),
                       "winsor_lo": float(lo), "winsor_hi": float(hi),
                       "z_nonnull": int(d.z_t.notna().sum()),
                       "excluded_2020_04_20": excluded_2020 if code == "CL" else None})
    allc.append(d)

cs = pd.concat(allc, ignore_index=True)
cs.loc[cs.s_t == "equal", "s_t"] = np.nan
cs.to_parquet(dpath("curve_state.parquet"), index=False)
print("\nwrote %s : %d rows" % (dpath("curve_state.parquet"), len(cs)))

dump_json("s2_step1c_curve.json", {"spx_trade_dates": N_SPX, "coverage_floor": COVERAGE_FLOOR,
                                   "meta": meta, "killcheck": kk, "n_dropped": n_drop})
