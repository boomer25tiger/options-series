"""Step 2g: exactly what A1 moved, row by row, against the session 1 series."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath
import numpy as np
import pandas as pd
pd.set_option("display.width", 300)

log_to("s1b_step2g_delta.log")
a = pd.read_parquet(dpath("mfiv_nofilter.parquet"))
b = pd.read_parquet(dpath("mfiv.parquet"))

rows = []
for tic in ["SPX", "GLD", "SLV", "USO", "UNG"]:
    x = a[a.ticker == tic][["date", "node", "mfiv", "drop_code"]].set_index(["date", "node"])
    y = b[b.ticker == tic][["date", "node", "mfiv", "drop_code"]].set_index(["date", "node"])
    j = x.join(y, lsuffix="_before", rsuffix="_after", how="outer")
    both = j.dropna(subset=["mfiv_before", "mfiv_after"])
    d = (both.mfiv_before - both.mfiv_after).abs()
    rel = d / both.mfiv_before.abs()
    rows.append({
        "ticker": tic,
        "rows_before_only": int(j.mfiv_after.isna().sum() & 0) or int(
            (j.drop_code_after.isna()).sum()),
        "common_rows": int(len(j.dropna(subset=["drop_code_before", "drop_code_after"]))),
        "both_nonnull_mfiv": int(len(both)),
        "bit_identical": int((d == 0).sum()),
        "rel_diff_over_1e9": int((rel > 1e-9).sum()),
        "max_abs_diff": float(d.max()) if len(d) else 0.0,
        "max_rel_diff": float(rel.max()) if len(rel) else 0.0,
        "drop_code_changed": int((j.drop_code_before != j.drop_code_after).sum()),
    })
    print("%-4s common=%5d  both-nonnull=%5d  bit-identical=%5d  moved(rel>1e-9)=%4d  "
          "max|abs|=%.3e  max|rel|=%.3e  drop_code changed=%4d"
          % (tic, rows[-1]["common_rows"], rows[-1]["both_nonnull_mfiv"],
             rows[-1]["bit_identical"], rows[-1]["rel_diff_over_1e9"],
             rows[-1]["max_abs_diff"], rows[-1]["max_rel_diff"],
             rows[-1]["drop_code_changed"]))

t = pd.DataFrame(rows)
print("\n" + t.to_string(index=False))
t.to_csv(opath("s1b_a1_delta.csv"), index=False)
dump_json("s1b_step2g_delta.json", {"rows": rows})
