"""Step 2b: per-secid vsurfd coverage across all year partitions 1996-2025."""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)
pd.set_option("display.max_rows", 1000)

log_to("step2b_vsurfd.log")
db = connect()

CANDIDATES = [7571, 8274, 8321, 100155, 108105, 109820, 111334, 115101,
              122392, 126681, 126776, 126778, 126779, 129361, 129362, 129367]
YEARS = list(range(1996, 2026))

frames = []
t_all = time.time()
for yr in YEARS:
    sql = """select secid, min(date) as mn, max(date) as mx,
                    count(distinct date) as n_dates, count(*) as n_rows,
                    string_agg(distinct days::text, '|') as days_list,
                    string_agg(distinct delta::text, '|') as delta_list,
                    string_agg(distinct cp_flag::text, '|') as cp_list,
                    count(impl_volatility) as nn_iv,
                    count(impl_strike) as nn_impl_strike,
                    count(impl_premium) as nn_impl_premium,
                    count(dispersion) as nn_dispersion
             from optionm.vsurfd%d where secid = any(%%(s)s) group by secid""" % yr
    t0 = time.time()
    df = db.raw_sql(sql, params={"s": [float(x) for x in CANDIDATES]})
    df["year"] = yr
    frames.append(df)
    print("vsurfd%d: %d secids present (%.1fs)" % (yr, len(df), time.time() - t0))

all_df = pd.concat(frames, ignore_index=True)
print("\ntotal scan wall clock: %.1fs" % (time.time() - t_all))

print("\n========== PER-SECID SUMMARY ACROSS 1996-2025 ==========")
summary = []
for secid, g in all_df.groupby("secid"):
    days = sorted({float(d) for lst in g.days_list.dropna() for d in lst.split('|')})
    deltas = sorted({float(d) for lst in g.delta_list.dropna() for d in lst.split('|')})
    cps = sorted({c for lst in g.cp_list.dropna() for c in lst.split('|')})
    rec = {
        "secid": int(secid),
        "first_date": str(g.mn.min()),
        "last_date": str(g.mx.max()),
        "n_dates": int(g.n_dates.sum()),
        "n_rows": int(g.n_rows.sum()),
        "years_present": sorted(int(y) for y in g.year.unique()),
        "n_distinct_days": len(days), "days_values": days,
        "n_distinct_delta": len(deltas), "delta_values": deltas,
        "cp_flag_values": cps,
        "nn_impl_volatility": int(g.nn_iv.sum()),
        "nn_impl_strike": int(g.nn_impl_strike.sum()),
        "nn_impl_premium": int(g.nn_impl_premium.sum()),
        "nn_dispersion": int(g.nn_dispersion.sum()),
    }
    summary.append(rec)
    print("\n--- secid %d ---" % rec["secid"])
    for k in ["first_date", "last_date", "n_dates", "n_rows", "n_distinct_days",
              "n_distinct_delta", "cp_flag_values", "nn_impl_volatility",
              "nn_impl_strike", "nn_impl_premium", "nn_dispersion"]:
        print("  %-20s %s" % (k, rec[k]))
    print("  days_values          %s" % rec["days_values"])
    print("  delta_values         %s" % rec["delta_values"])
    print("  years_present        %d..%d (n=%d)" % (rec["years_present"][0],
          rec["years_present"][-1], len(rec["years_present"])))

missing = sorted(set(CANDIDATES) - {r["secid"] for r in summary})
print("\ncandidate secids with NO vsurfd rows in any year: %s" % missing)

dump_json("step2b_vsurfd.json", {"summary": summary, "no_vsurfd_rows": missing})
all_df.drop(columns=["days_list", "delta_list", "cp_list"]).to_csv(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                 "probe_output", "step2b_vsurfd_by_year.csv"), index=False)
db.close()
