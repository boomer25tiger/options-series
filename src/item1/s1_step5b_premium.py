"""Step 5b: realized variance (6.3), both premium measures (6.4), and the
non-overlapping grid."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import (log_to, dump_json, dpath, opath, SECIDS, NODES,
                          COMMON_START, COMMON_END)
import numpy as np
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)

log_to("s1_step5b_premium.log")
t_all = time.time()

H = {30: 21, 91: 63}           # spec 6.3
TRADING_DAYS = 252.0

mf = pd.read_parquet(dpath("mfiv.parquet"))
atm = pd.read_parquet(dpath("atmiv.parquet"))
sp = pd.read_parquet(dpath("secprd_returns.parquet"))
atm["node"] = atm["node"].astype(int)

# ---------------------------------------------------------- 6.3 realized variance ---
rv_rows = []
for tic, g in sp.sort_values("date").groupby("ticker"):
    g = g.reset_index(drop=True)
    r = np.log1p(g["return"].values.astype(float))
    ok = ~np.isnan(r)
    r2 = np.where(ok, r * r, 0.0)
    n = len(g)
    for node, h in H.items():
        # forward window t+1 .. t+h
        cs = np.concatenate([[0.0], np.cumsum(r2)])
        cok = np.concatenate([[0], np.cumsum(ok.astype(int))])
        idx = np.arange(n)
        end = idx + h          # inclusive index t+h
        valid = end < n
        s = np.full(n, np.nan)
        cnt = np.zeros(n, dtype=int)
        s[valid] = cs[end[valid] + 1] - cs[idx[valid] + 1]
        cnt[valid] = cok[end[valid] + 1] - cok[idx[valid] + 1]
        rv = np.where(valid & (cnt == h), s * (TRADING_DAYS / h), np.nan)
        rv_rows.append(pd.DataFrame({"ticker": tic, "date": g.date.values,
                                     "node": node, "rv": rv,
                                     "rv_obs": cnt, "rv_window_complete": valid & (cnt == h)}))
rv = pd.concat(rv_rows, ignore_index=True)
print("realized variance rows: %d" % len(rv))
print("\nRV windows dropped for an incomplete window, per ticker and node:")
d = rv.groupby(["ticker", "node"]).agg(dates=("rv", "size"),
                                       complete=("rv_window_complete", "sum"))
d["dropped"] = d.dates - d.complete
d["share_dropped"] = (d.dropped / d.dates).round(4)
print(d.to_string())

# ------------------------------------------------------------------- 6.4 premium ---
p = (mf[["secid", "ticker", "date", "node", "mfiv", "drop_code"]]
     .merge(atm[["ticker", "date", "node", "atmiv"]], on=["ticker", "date", "node"], how="left")
     .merge(rv[["ticker", "date", "node", "rv"]], on=["ticker", "date", "node"], how="left"))
p.loc[p.drop_code != "OK", "mfiv"] = np.nan
p.loc[p.rv <= 0, "rv"] = np.nan

p["logratio_mf"] = np.log(p.mfiv / p.rv)
p["logratio_atm"] = np.log(p.atmiv / p.rv)
p["diff_mf"] = p.mfiv - p.rv
p["diff_atm"] = p.atmiv - p.rv
p["year"] = p.date.dt.year

cols = ["secid", "ticker", "date", "node", "mfiv", "atmiv", "rv",
        "logratio_mf", "logratio_atm", "diff_mf", "diff_atm", "drop_code", "year"]
p[cols].to_parquet(dpath("premium_daily.parquet"), index=False)
print("\nwrote %s : %d rows" % (dpath("premium_daily.parquet"), len(p)))

print("\n===== daily premium series: non-null counts =====")
s = p.groupby(["ticker", "node"]).agg(
    rows=("date", "size"), mfiv=("mfiv", "count"), atmiv=("atmiv", "count"),
    rv=("rv", "count"), logratio_mf=("logratio_mf", "count"),
    logratio_atm=("logratio_atm", "count"))
print(s.to_string())

print("\n===== mean log(IV2/RV), full pull span (descriptive, no test) =====")
m1 = p.groupby(["ticker", "node"]).agg(
    n_mf=("logratio_mf", "count"), mean_mf=("logratio_mf", "mean"),
    median_mf=("logratio_mf", "median"),
    n_atm=("logratio_atm", "count"), mean_atm=("logratio_atm", "mean"))
print(m1.round(4).to_string())

cw = p[(p.date >= COMMON_START) & (p.date <= COMMON_END)]
print("\n===== mean log(IV2/RV), common window %s..%s (descriptive, no test) ====="
      % (COMMON_START, COMMON_END))
m2 = cw.groupby(["ticker", "node"]).agg(
    n_mf=("logratio_mf", "count"), mean_mf=("logratio_mf", "mean"),
    median_mf=("logratio_mf", "median"),
    n_atm=("logratio_atm", "count"), mean_atm=("logratio_atm", "mean"),
    mean_diff_mf=("diff_mf", "mean"))
print(m2.round(4).to_string())

# --------------------------------------------------- non-overlapping grid (6.4/7) ---
grid_rows = []
for tic, g in sp.sort_values("date").groupby("ticker"):
    dates = g.date.reset_index(drop=True)
    start = dates[dates >= pd.Timestamp(COMMON_START)]
    if not len(start):
        continue
    i0 = start.index[0]
    within = dates[(dates >= pd.Timestamp(COMMON_START)) & (dates <= pd.Timestamp(COMMON_END))]
    last_i = within.index[-1]
    for node, h in H.items():
        picks = list(range(i0, last_i + 1, h))
        grid_rows.append(pd.DataFrame({"ticker": tic, "node": node,
                                       "date": dates.iloc[picks].values,
                                       "grid_index": range(len(picks))}))
grid = pd.concat(grid_rows, ignore_index=True)
gp = grid.merge(p[cols], on=["ticker", "date", "node"], how="left")
gp.to_parquet(dpath("premium_grid.parquet"), index=False)
print("\nwrote %s : %d rows" % (dpath("premium_grid.parquet"), len(gp)))

print("\n===== non-overlapping grid, anchored on %s =====" % COMMON_START)
gs = gp.groupby(["ticker", "node"]).agg(
    grid_dates=("date", "size"), first=("date", "min"), last=("date", "max"),
    n_logratio_mf=("logratio_mf", "count"), mean_mf=("logratio_mf", "mean"),
    n_logratio_atm=("logratio_atm", "count"))
print(gs.round(4).to_string())

print("\nTOTAL step 5b wall clock: %.1f s" % (time.time() - t_all))
dump_json("s1_step5b_premium.json", {
    "seconds": round(time.time() - t_all, 1),
    "daily_rows": len(p), "grid_rows": len(gp),
    "rv_windows": d.reset_index().to_dict("records"),
    "daily_counts": s.reset_index().to_dict("records"),
    "mean_full_span": m1.reset_index().to_dict("records"),
    "mean_common_window": m2.reset_index().to_dict("records"),
    "grid_summary": gs.reset_index().to_dict("records"),
})
