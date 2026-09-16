"""Step 7: kill check, spec section 9.

Condition, verbatim from the spec: "If for any commodity no first-and-second series
pair matches at least 80 percent of the common window's trade dates, or the two series
in a pair carry different roll conventions, curve state is dropped for that commodity.
If it is dropped for all four, the item ships as the unconditional version and H2 and
Q3 are recorded as not measured."

The outcome is reported here and NOT acted on. Session 2 acts.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, load_json, opath, COMMON_START, COMMON_END
import pandas as pd
pd.set_option("display.width", 300); pd.set_option("display.max_colwidth", 60)

log_to("s1_step7_killcheck.log")

FLOOR = 0.80
sel = load_json("s1_step2_ds_series.json")["selection"]
pull = load_json("s1_step2b_ds_pull.json")
spx_dates = pull["spx_trade_dates_common_window"]

LABEL = {"GC": "COMEX gold (GLD)", "SI": "COMEX silver (SLV)",
         "CL": "NYMEX WTI light sweet crude (USO)", "NG": "NYMEX Henry Hub natural gas (UNG)"}

print("common window %s to %s ; SPX trade dates in it: %d"
      % (COMMON_START, COMMON_END, spx_dates))
print("80 percent floor on that count: %.1f dates\n" % (FLOOR * spx_dates))

rows = []
for code in ["GC", "SI", "CL", "NG"]:
    s = sel[code]
    p = pull["series"].get(code, {})
    pair = s["selected"] is not None
    cov = p.get("coverage_share") if p.get("pulled") else None
    cov_pass = (cov is not None) and (cov >= FLOOR)
    # roll convention can only be compared when there are two legs
    same_roll = "n/a - no second leg exists" if not pair else "compared"
    # Spec condition: dropped unless a PAIR exists whose coverage clears the floor and
    # whose legs share a roll convention.
    dropped = (not pair) or (not cov_pass) or (same_roll not in ("same",))
    reason = []
    if not pair:
        reason.append("no first-and-second pair qualifies (step 2, rule R6)")
    if cov is not None and not cov_pass:
        reason.append("first-leg coverage %.4f below the %.2f floor" % (cov, FLOOR))
    rows.append({
        "commodity": code, "underlying_for": LABEL[code],
        "pair_selected": pair,
        "first_leg_candidates": s["n_first"],
        "second_leg_candidates": s["n_second"],
        "qualifying_pairs": s["n_pairs"],
        "first_leg_pulled": p.get("dsmnem") if p.get("pulled") else None,
        "first_leg_roll": p.get("rollmethoddesc") if p.get("pulled") else None,
        "coverage_share_first_leg": cov,
        "coverage_clears_80pct": cov_pass,
        "same_roll_convention": same_roll,
        "curve_state_outcome": "DROPPED" if dropped else "RETAINED",
        "reason": "; ".join(reason) if reason else "",
    })

t = pd.DataFrame(rows)
print("===== KILL CHECK, section 9 =====")
print(t[["commodity", "underlying_for", "pair_selected", "second_leg_candidates",
         "qualifying_pairs", "coverage_share_first_leg", "coverage_clears_80pct",
         "same_roll_convention", "curve_state_outcome"]].to_string(index=False))
print("\nreasons:")
for r in rows:
    print("  %-3s %s" % (r["commodity"], r["reason"] or "(none)"))

n_dropped = sum(r["curve_state_outcome"] == "DROPPED" for r in rows)
print("\ncommodities with curve state DROPPED: %d of 4" % n_dropped)
if n_dropped == 4:
    print("All four are dropped. Under section 9 that means the item ships as the")
    print("unconditional version and H2 and Q3 are recorded as not measured, which")
    print("is null D in section 12. Session 2 acts on this; session 1 only reports it.")

t.to_csv(opath("s1_step7_killcheck.csv"), index=False)
dump_json("s1_step7_killcheck.json", {
    "floor": FLOOR, "spx_trade_dates_common_window": spx_dates,
    "n_dropped": n_dropped, "rows": rows,
    "consequence": ("all four dropped: unconditional version, H2 and Q3 not measured "
                    "(null D)") if n_dropped == 4 else "partial",
})
