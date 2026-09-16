"""Step 1e: apply the pass rule, save the verified series, re-run the section 9 kill check."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, load_json, dpath, opath, COMMON_START, COMMON_END
import numpy as np
import pandas as pd
pd.set_option("display.width", 330); pd.set_option("display.max_rows", 200)

log_to("s1b_step1e_passrule.log")
ver = load_json("s1b_step1c_verify.json")
sw = load_json("s1b_step1d_switches.json")

MATCH_FLOOR = ver["match_floor"]
SWITCH_FLOOR = ver["switch_floor"]
COVERAGE_FLOOR = 0.80
N_SPX = ver["spx_trade_dates"]

CLASSES = ["GC", "SI", "CL", "NG"]
rows = []
for code in CLASSES:
    v = ver["classes"][code]
    s = sw["classes"][code]
    # Which convention, if either, clears the floor for BOTH legs?
    best = None
    for conv in ("X", "Y"):
        b = v["conventions"][conv]
        s1 = b.get("TRc1", {}).get("share_within_0.5pct")
        s2 = b.get("TRc2", {}).get("share_within_0.5pct")
        if s1 is None or s2 is None:
            continue
        if s1 >= MATCH_FLOOR and s2 >= MATCH_FLOOR:
            cand = (conv, s1, s2, min(s1, s2))
            if best is None or cand[3] > best[3]:
                best = cand
    conv_used = best[0] if best else None
    m1 = best[1] if best else (v["conventions"]["X"].get("TRc1", {}).get("share_within_0.5pct"))
    m2 = best[2] if best else (v["conventions"]["X"].get("TRc2", {}).get("share_within_0.5pct"))
    al = s.get("switch_alignment")
    sh = al["share"] if al and al.get("share") is not None else None
    cov = s["trc2_coverage"]["coverage_share"]

    match_ok = best is not None
    switch_ok = (sh is not None) and (sh >= SWITCH_FLOOR)
    passed = bool(match_ok and switch_ok)
    cov_ok = cov >= COVERAGE_FLOOR
    reasons = []
    if not match_ok:
        if v["conventions"]["X"].get("TRc2", {}).get("n", 0) == 0:
            reasons.append("TRc2 series is empty in dsfutcalcserval")
        else:
            reasons.append("no single convention clears %.2f for both legs (best X: TRc1 %.4f, TRc2 %.4f)"
                           % (MATCH_FLOOR,
                              v["conventions"]["X"].get("TRc1", {}).get("share_within_0.5pct", float("nan")),
                              v["conventions"]["X"].get("TRc2", {}).get("share_within_0.5pct", float("nan"))))
    if not switch_ok:
        reasons.append("TRc2 switches with TRc1 on %s, below %.2f"
                       % ("n/a" if sh is None else "%.4f" % sh, SWITCH_FLOOR))
    rows.append({"commodity": code, "convention": conv_used,
                 "trc1_match": m1, "trc2_match": m2, "switch_alignment": sh,
                 "trc2_coverage": cov, "match_ok": match_ok, "switch_ok": switch_ok,
                 "pass_rule": passed, "coverage_ok": cov_ok,
                 "reasons": "; ".join(reasons)})

t = pd.DataFrame(rows)
print("===== PASS RULE (match within 0.5%% on >= %.2f of dates under one convention, and"
      " TRc2 switching with TRc1 on >= %.2f of TRc1 switches) =====" % (MATCH_FLOOR, SWITCH_FLOOR))
print(t[["commodity", "convention", "trc1_match", "trc2_match", "switch_alignment",
         "pass_rule"]].to_string(index=False))
print("\nreasons for failure:")
for r in rows:
    print("  %-3s %s" % (r["commodity"], r["reasons"] or "(passes)"))

# ---------- save verified series ----------
MN = {"GC": ("CZGC.01", "CZGC.02"), "SI": ("CZIC.01", "CZIC.02"),
      "CL": ("NCLC.01", "NCLC.02"), "NG": ("NNGC.01", "NNGC.02")}
saved = {}
for r in rows:
    code = r["commodity"]
    m1n, m2n = MN[code]
    for leg, mn in (("c1", m1n), ("c2", m2n)):
        src = dpath("dsser_%s.parquet" % mn.replace(".", "_"))
        d = pd.read_parquet(src)
        fn = dpath("ds_%s_%s.parquet" % (code.lower(), leg))
        d.to_parquet(fn, index=False)
        saved.setdefault(code, {})[leg] = {"mnemonic": mn, "file": os.path.basename(fn),
                                           "rows": len(d), "verified": r["pass_rule"]}
    print("saved ds_%s_c1.parquet and ds_%s_c2.parquet (verified=%s)"
          % (code.lower(), code.lower(), r["pass_rule"]))

# ---------- section 9 kill check, re-run ----------
LABEL = {"GC": "COMEX gold (GLD)", "SI": "COMEX silver (SLV)",
         "CL": "NYMEX WTI light sweet crude (USO)", "NG": "NYMEX Henry Hub natural gas (UNG)"}
print("\n\n===== SECTION 9 KILL CHECK, re-run on the verified pairs =====")
print("SPX trade dates in the common window: %d ; 80 percent floor: %.1f dates"
      % (N_SPX, COVERAGE_FLOOR * N_SPX))
kk = []
for r in rows:
    dropped = (not r["pass_rule"]) or (not r["coverage_ok"])
    why = []
    if not r["pass_rule"]:
        why.append("fails the A2 pass rule")
    if not r["coverage_ok"]:
        why.append("TRc2 coverage %.4f below the 0.80 floor" % r["trc2_coverage"])
    kk.append({"commodity": r["commodity"], "underlying_for": LABEL[r["commodity"]],
               "pair_verified": r["pass_rule"], "convention": r["convention"],
               "coverage_share": r["trc2_coverage"], "clears_80pct": r["coverage_ok"],
               "outcome": "DROPPED" if dropped else "RETAINED",
               "reason": "; ".join(why)})
k = pd.DataFrame(kk)
print(k[["commodity", "underlying_for", "pair_verified", "convention", "coverage_share",
         "clears_80pct", "outcome"]].to_string(index=False))
print("\nreasons:")
for r in kk:
    print("  %-3s %s" % (r["commodity"], r["reason"] or "(retained)"))
n_drop = int((k.outcome == "DROPPED").sum())
print("\ncurve state DROPPED for %d of 4; RETAINED for %d" % (n_drop, 4 - n_drop))
if n_drop < 4:
    keep = list(k.loc[k.outcome == "RETAINED", "commodity"])
    print("Section 9 drops the item to the unconditional version only if ALL FOUR are")
    print("dropped. %s survives, so H2 and Q3 are measurable for %s in session 2."
          % (", ".join(keep), ", ".join(keep)))

k.to_csv(opath("s1b_killcheck.csv"), index=False)
dump_json("s1b_step1e_passrule.json", {
    "match_floor": MATCH_FLOOR, "switch_floor": SWITCH_FLOOR,
    "coverage_floor": COVERAGE_FLOOR, "spx_trade_dates": N_SPX,
    "pass_rule": rows, "saved": saved, "killcheck": kk, "n_dropped": n_drop})
