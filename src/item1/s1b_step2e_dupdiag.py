"""Step 2e: re-run the REPORT_s1 section 3.7 duplicate diagnostic on the A1-filtered data."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath, PULL_SPAN
from item1.s1b_step2c_build import a1_filter, SS_FLAG_STANDARD, CONTRACT_SIZE_STANDARD
import numpy as np
import pandas as pd
pd.set_option("display.width", 280); pd.set_option("display.max_rows", 300)

log_to("s1b_step2e_dupdiag.log")
print("A1 encoding in force: ss_flag == %r and contract_size == %g"
      % (SS_FLAG_STANDARD, CONTRACT_SIZE_STANDARD))

KEY = ["date", "exdate", "am_settlement", "cp_flag", "strike_price"]
rows = []
for tic in ["SPX", "GLD", "SLV", "USO", "UNG"]:
    a, b = PULL_SPAN[tic]
    n_before = n_after = 0
    dup_dates_before = dup_dates_after = 0
    dup_rows_before = dup_rows_after = 0
    dates_total = 0
    for yr in range(int(a[:4]), int(b[:4]) + 1):
        fn = dpath("opprcd_%s_%d.parquet" % (tic, yr))
        if not os.path.exists(fn):
            continue
        q = pd.read_parquet(fn)
        n_before += len(q)
        d0 = q.duplicated(KEY, keep=False)
        dup_rows_before += int(d0.sum())
        dup_dates_before += int(q.loc[d0, "date"].nunique())
        dates_total += int(q.date.nunique())
        f = a1_filter(q)
        n_after += len(f)
        d1 = f.duplicated(KEY, keep=False)
        dup_rows_after += int(d1.sum())
        dup_dates_after += int(f.loc[d1, "date"].nunique())
    rows.append({"ticker": tic, "dates": dates_total,
                 "rows_before": n_before, "rows_after": n_after,
                 "share_rows_kept": round(n_after / max(n_before, 1), 4),
                 "dup_dates_before": dup_dates_before,
                 "dup_dates_after": dup_dates_after,
                 "dup_rows_before": dup_rows_before,
                 "dup_rows_after": dup_rows_after,
                 "share_dates_dup_before": round(dup_dates_before / max(dates_total, 1), 4),
                 "share_dates_dup_after": round(dup_dates_after / max(dates_total, 1), 4)})
    print("%-4s dates=%4d  rows %s -> %s (kept %.4f) | duplicate dates %4d -> %4d | "
          "duplicate rows %6d -> %5d"
          % (tic, dates_total, "{:,}".format(n_before), "{:,}".format(n_after),
             n_after / max(n_before, 1), dup_dates_before, dup_dates_after,
             dup_rows_before, dup_rows_after))

t = pd.DataFrame(rows)
print("\n===== summary =====")
print(t.to_string(index=False))
print("\nTotal secid-dates that still fall back to the A4 open-interest collapse: %d"
      % int(t.dup_dates_after.sum()))
t.to_csv(opath("s1b_dup_diag.csv"), index=False)
dump_json("s1b_step2e_dupdiag.json", {"encoding": {"ss_flag": SS_FLAG_STANDARD,
                                                   "contract_size": CONTRACT_SIZE_STANDARD},
                                      "rows": rows})
