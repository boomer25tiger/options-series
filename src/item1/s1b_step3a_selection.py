"""Step 3a: registered diagnostic A3(a), the selection check on the 3-strike floor.

Per secid and node on the common window: the mean ATM log ratio on dates where the
filtered model-free series is PRESENT against dates where it is ABSENT, with counts,
the difference and a Welch p-value.

A3 labelling rule, fixed in the amendment before any number was seen: if the difference
exceeds 0.10 log units or p is below 0.05, the model-free H1 result for that ETF is
labelled as computed on a selected subsample and the ATM secondary carries the headline.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath, COMMON_START, COMMON_END
import numpy as np
import pandas as pd
from scipy import stats
pd.set_option("display.width", 300); pd.set_option("display.max_rows", 200)

log_to("s1b_step3a_selection.log")
DIFF_THRESHOLD = 0.10
P_THRESHOLD = 0.05

mf = pd.read_parquet(dpath("mfiv.parquet"))
atm = pd.read_parquet(dpath("atmiv.parquet"))
rvsrc = pd.read_parquet(dpath("premium_daily.parquet"))

# ATM log ratio on every date where the ATM measure and RV both exist
base = rvsrc[["ticker", "date", "node", "logratio_atm"]].copy()
present = mf[mf.drop_code == "OK"][["ticker", "date", "node"]].assign(mf_present=True)
j = base.merge(present, on=["ticker", "date", "node"], how="left")
j["mf_present"] = j.mf_present.fillna(False)
j = j[(j.date >= COMMON_START) & (j.date <= COMMON_END)]
j = j.dropna(subset=["logratio_atm"])

print("common window %s .. %s ; rows with an ATM log ratio: %s"
      % (COMMON_START, COMMON_END, "{:,}".format(len(j))))

rows = []
for (tic, node), g in j.groupby(["ticker", "node"]):
    a = g.loc[g.mf_present, "logratio_atm"].values
    b = g.loc[~g.mf_present, "logratio_atm"].values
    if len(b) < 2 or len(a) < 2:
        t, p = np.nan, np.nan
    else:
        t, p = stats.ttest_ind(a, b, equal_var=False)
    diff = (a.mean() - b.mean()) if len(a) and len(b) else np.nan
    flag_diff = abs(diff) > DIFF_THRESHOLD if np.isfinite(diff) else False
    flag_p = (p < P_THRESHOLD) if np.isfinite(p) else False
    rows.append({"ticker": tic, "node": int(node),
                 "n_retained": len(a), "n_dropped": len(b),
                 "mean_atm_retained": a.mean() if len(a) else np.nan,
                 "mean_atm_dropped": b.mean() if len(b) else np.nan,
                 "difference": diff, "welch_t": t, "welch_p": p,
                 "exceeds_0.10": bool(flag_diff), "p_below_0.05": bool(flag_p),
                 "labelled_selected": bool(flag_diff or flag_p)})

t = pd.DataFrame(rows)
print("\n===== A3(a) selection check: ATM log ratio, dates the model-free series "
      "retains vs drops =====")
print(t.round(4).to_string(index=False))

lab = sorted(set(t.loc[t.labelled_selected, "ticker"]))
print("\nA3 labelling rule: difference above %.2f log units OR Welch p below %.2f."
      % (DIFF_THRESHOLD, P_THRESHOLD))
print("ETFs labelled as computed on a selected subsample: %s"
      % (", ".join("%s (%s)" % (r.ticker, "node %d" % r.node) for r in
                   t[t.labelled_selected].itertuples()) or "(none)"))
print("Distinct tickers labelled at either node: %s" % (", ".join(lab) or "(none)"))
print("For those, the ATM secondary carries the headline H1 number in session 2.")

t.to_csv(opath("s1b_a3a_selection.csv"), index=False)
dump_json("s1b_step3a_selection.json", {
    "diff_threshold": DIFF_THRESHOLD, "p_threshold": P_THRESHOLD,
    "rows": t.to_dict("records"), "labelled_tickers": lab})
