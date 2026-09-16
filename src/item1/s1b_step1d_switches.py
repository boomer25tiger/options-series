"""Step 1d: cross-position diagnostic, switch dates, CS comparison, coverage,
the pass rule, and the re-run of the section 9 kill check."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import (connect, log_to, dump_json, load_json, dpath, opath,
                          COMMON_START, COMMON_END, SECIDS)
import numpy as np
import pandas as pd
pd.set_option("display.width", 320); pd.set_option("display.max_rows", 300)

log_to("s1b_step1d_switches.log")
TOL = 0.005
MATCH_FLOOR = 0.95
SWITCH_FLOOR = 0.95
COVERAGE_FLOOR = 0.80   # section 9

db = connect()
frames = [db.raw_sql(
    "select date from optionm.secprd%d where secid=%%(s)s and date between %%(a)s and %%(b)s"
    % yr, params={"s": float(SECIDS["SPX"]), "a": COMMON_START, "b": COMMON_END})
    for yr in range(2008, 2026)]
db.close()
SPX_DATES = pd.DatetimeIndex(pd.to_datetime(
    pd.concat(frames, ignore_index=True)["date"]).sort_values().unique())
N_SPX = len(SPX_DATES)
print("SPX trade dates in the common window: %d" % N_SPX)

CLASSES = {"GC": ("CZGC.01", "CZGC.02", "CZGCS01"),
           "SI": ("CZIC.01", "CZIC.02", "CZICS01"),
           "CL": ("NCLC.01", "NCLC.02", None),
           "NG": ("NNGC.01", "NNGC.02", "NNGCS01")}
LABEL = {"GC": "COMEX gold (GLD)", "SI": "COMEX silver (SLV)",
         "CL": "NYMEX WTI light sweet crude (USO)", "NG": "NYMEX Henry Hub natural gas (UNG)"}

def load_series(mn):
    if mn is None:
        return None
    d = pd.read_parquet(dpath("dsser_%s.parquet" % mn.replace(".", "_")))
    if not len(d):
        return None
    d["date"] = pd.to_datetime(d["date"])
    return d.dropna(subset=["settlement"]).set_index("date")["settlement"]

out = {"spx_trade_dates": N_SPX, "tolerance": TOL, "match_floor": MATCH_FLOOR,
       "switch_floor": SWITCH_FLOOR, "coverage_floor": COVERAGE_FLOOR, "classes": {}}

for code, (m1, m2, mcs) in CLASSES.items():
    print("\n\n################ %s — %s ################" % (code, LABEL[code]))
    con = pd.read_parquet(dpath("dsfut_contracts_%s.parquet" % code.lower()))
    val = pd.read_parquet(dpath("dsfut_contractval_%s.parquet" % code.lower()))
    con["lasttrddate"] = pd.to_datetime(con["lasttrddate"])
    val["date"] = pd.to_datetime(val["date"])
    exp = con.dropna(subset=["lasttrddate"]).set_index("futcode")["lasttrddate"]
    v = val.dropna(subset=["settlement"]).copy()
    v["expiry"] = v.futcode.map(exp)
    v = v.dropna(subset=["expiry"])
    by_date = {d: g.sort_values(["expiry", "futcode"]) for d, g in v.groupby("date")}

    s1, s2, scs = load_series(m1), load_series(m2), load_series(mcs)
    rec = {"label": LABEL[code], "trc1": m1, "trc2": m2, "cs": mcs}

    # ---------- cross-position diagnostic: which reference rank does each series track ----------
    print("cross-position: share matching reference rank k within 0.5 percent, convention X and Y")
    cross = {}
    for conv, strict in (("X", False), ("Y", True)):
        for lab, ser in (("TRc1", s1), ("TRc2", s2)):
            if ser is None:
                continue
            for k in range(1, 5):
                hit = tot = 0
                for d in SPX_DATES:
                    g = by_date.get(d)
                    if g is None or len(g) < k or d not in ser.index:
                        continue
                    gg = g[g.expiry > d] if strict else g[g.expiry >= d]
                    if len(gg) < k:
                        continue
                    refv = gg.settlement.iloc[k - 1]
                    x = ser.loc[d]
                    if isinstance(x, pd.Series):
                        x = x.iloc[0]
                    tot += 1
                    if refv and abs(x - refv) / abs(refv) <= TOL:
                        hit += 1
                cross["%s|%s|rank%d" % (conv, lab, k)] = {
                    "n": tot, "share": (hit / tot) if tot else None}
            row = " ".join("rank%d=%.4f" % (k, cross["%s|%s|rank%d" % (conv, lab, k)]["share"])
                           if cross["%s|%s|rank%d" % (conv, lab, k)]["share"] is not None else
                           "rank%d=n/a" % k for k in range(1, 5))
            print("  %s %-5s n=%4d  %s" % (conv, lab, cross["%s|%s|rank1" % (conv, lab)]["n"], row))
    rec["cross_position"] = cross

    # ---------- matched contract identity and switches ----------
    def matched_futcode(ser):
        if ser is None:
            return None
        rows = []
        for d in SPX_DATES:
            g = by_date.get(d)
            if g is None or d not in ser.index:
                continue
            x = ser.loc[d]
            if isinstance(x, pd.Series):
                x = x.iloc[0]
            rel = (g.settlement - x).abs() / g.settlement.abs().replace(0, np.nan)
            j = rel.values.argmin() if len(rel) else None
            if j is None or not np.isfinite(rel.values[j]):
                continue
            rows.append({"date": d, "futcode": g.futcode.values[j],
                         "rel": rel.values[j], "expiry": g.expiry.values[j]})
        return pd.DataFrame(rows)

    m1d, m2d = matched_futcode(s1), matched_futcode(s2)
    sw = {}
    for lab, md in (("TRc1", m1d), ("TRc2", m2d)):
        if md is None or not len(md):
            sw[lab] = {"n_dates": 0, "n_switches": 0}
            print("  %s: no matched-contract series (series empty)" % lab)
            continue
        md = md.sort_values("date").reset_index(drop=True)
        md["switch"] = md.futcode != md.futcode.shift(1)
        md.loc[0, "switch"] = False
        sw[lab] = {"n_dates": int(len(md)), "n_switches": int(md.switch.sum()),
                   "median_rel_to_matched": float(md.rel.median()),
                   "switch_dates": [str(d.date()) for d in md.loc[md.switch, "date"]][:60]}
        print("  %s: matched on %d dates, %d switches, median |rel| to the matched contract %.2e"
              % (lab, len(md), int(md.switch.sum()), md.rel.median()))
    rec["switches"] = sw

    same_day = None
    if m1d is not None and len(m1d) and m2d is not None and len(m2d):
        a = m1d.sort_values("date").reset_index(drop=True)
        b = m2d.sort_values("date").reset_index(drop=True)
        a["sw1"] = a.futcode != a.futcode.shift(1); a.loc[0, "sw1"] = False
        b["sw2"] = b.futcode != b.futcode.shift(1); b.loc[0, "sw2"] = False
        j = a[["date", "sw1"]].merge(b[["date", "sw2"]], on="date", how="inner")
        n1 = int(j.sw1.sum())
        both = int((j.sw1 & j.sw2).sum())
        same_day = {"common_dates": int(len(j)), "trc1_switches": n1,
                    "trc2_switches_same_day": both,
                    "share": (both / n1) if n1 else None}
        print("  TRc1 switches on %d of %d common dates; TRc2 switches the same day on %d "
              "(share %.4f)" % (n1, len(j), both, same_day["share"] if n1 else float("nan")))
    rec["switch_alignment"] = same_day

    # ---------- TRc1 against the CS series on non-switch dates ----------
    cs_cmp = None
    if scs is not None and m1d is not None and len(m1d):
        a = m1d.sort_values("date").reset_index(drop=True)
        a["sw1"] = a.futcode != a.futcode.shift(1); a.loc[0, "sw1"] = False
        j = a[["date", "sw1"]].merge(s1.rename("trc1"), left_on="date", right_index=True)
        j = j.merge(scs.rename("cs"), left_on="date", right_index=True)
        ns = j[~j.sw1]
        eq = (ns.trc1 == ns.cs)
        near = ((ns.trc1 - ns.cs).abs() / ns.cs.abs().replace(0, np.nan) <= TOL)
        cs_cmp = {"cs_series": mcs, "n_nonswitch_dates": int(len(ns)),
                  "share_exact": float(eq.mean()) if len(ns) else None,
                  "share_within_0.5pct": float(near.mean()) if len(ns) else None}
        print("  TRc1 equals %s exactly on %.4f of %d non-switch dates (within 0.5%%: %.4f)"
              % (mcs, cs_cmp["share_exact"], len(ns), cs_cmp["share_within_0.5pct"]))
    elif scs is None:
        cs_cmp = {"cs_series": None, "note": "no CS-format series exists for this class"}
        print("  no CS-format series exists for this class, comparison not possible")
    rec["cs_comparison"] = cs_cmp

    # ---------- TRc2 coverage ----------
    if s2 is not None:
        idx = pd.DatetimeIndex(s2.index)
        inwin = idx[(idx >= pd.Timestamp(COMMON_START)) & (idx <= pd.Timestamp(COMMON_END))]
        matched = inwin.intersection(SPX_DATES)
        cov = {"dates_in_common_window": int(len(inwin)),
               "matched_spx_trade_dates": int(len(matched)),
               "coverage_share": float(len(matched) / N_SPX)}
    else:
        cov = {"dates_in_common_window": 0, "matched_spx_trade_dates": 0, "coverage_share": 0.0}
    print("  TRc2 coverage: %d dates in window, %d matched SPX trade dates, share %.4f"
          % (cov["dates_in_common_window"], cov["matched_spx_trade_dates"], cov["coverage_share"]))
    rec["trc2_coverage"] = cov
    out["classes"][code] = rec

dump_json("s1b_step1d_switches.json", out)
