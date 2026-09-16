"""Step 2: assemble the test panel.

State is matched on the premium's own date t. Section 6.5 says "state is taken on the
window's first day"; the premium observation at t compares IV^2_t with RV over t+1..t+h,
so t is the day the position opens and the only date at which z_t is in the information
set. Matching on t+1 would put the regressor outside the information set at t.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath, COMMON_START, COMMON_END
import numpy as np
import pandas as pd
pd.set_option("display.width", 300); pd.set_option("display.max_rows", 300)

log_to("s2_step2_panel.log")

MAP = {"GLD": "GC", "SLV": "SI", "USO": "CL", "UNG": "NG"}

prem = pd.read_parquet(dpath("premium_daily.parquet"))
grid = pd.read_parquet(dpath("premium_grid.parquet"))
cs = pd.read_parquet(dpath("curve_state.parquet"))
f2 = pd.read_parquet(dpath("mfiv_floor2.parquet"))[["ticker", "date", "node", "mfiv", "drop_code"]]
f2 = f2.rename(columns={"mfiv": "mfiv_floor2", "drop_code": "drop_code_floor2"})

prem["commodity"] = prem.ticker.map(MAP)
grid["commodity"] = grid.ticker.map(MAP)
keep = ["commodity", "date", "f1", "f2", "spread", "s_t", "z_t", "z_raw", "switch"]

panel = prem.merge(cs[keep], on=["commodity", "date"], how="left")
panel = panel.merge(f2, on=["ticker", "date", "node"], how="left")
panel["in_common"] = (panel.date >= COMMON_START) & (panel.date <= COMMON_END)
# April 2020 robustness flag: windows starting 2020-03-01 to 2020-04-30 (section 6.7)
panel["apr2020"] = (panel.date >= "2020-03-01") & (panel.date <= "2020-04-30")
panel.to_parquet(dpath("test_panel.parquet"), index=False)
print("wrote %s : %d rows" % (dpath("test_panel.parquet"), len(panel)))

cw = panel[panel.in_common]
print("\n===== daily rows in the common window with a premium and a state =====")
rows = []
for (tic, node), g in cw.groupby(["ticker", "node"]):
    rows.append({
        "ticker": tic, "node": int(node), "rows": len(g),
        "mf_premium": int(g.logratio_mf.notna().sum()),
        "atm_premium": int(g.logratio_atm.notna().sum()),
        "state_s": int(g.s_t.notna().sum()),
        "state_z": int(g.z_t.notna().sum()),
        "mf_and_z": int((g.logratio_mf.notna() & g.z_t.notna()).sum()),
        "atm_and_z": int((g.logratio_atm.notna() & g.z_t.notna()).sum()),
        "mf_and_s": int((g.logratio_mf.notna() & g.s_t.notna()).sum()),
        "atm_and_s": int((g.logratio_atm.notna() & g.s_t.notna()).sum()),
        "floor2_premium": int((g.mfiv_floor2.notna() & g.rv.notna() & (g.rv > 0)).sum()),
    })
t = pd.DataFrame(rows)
print(t.to_string(index=False))

gp = grid.merge(cs[keep], on=["commodity", "date"], how="left")
gp = gp.merge(f2, on=["ticker", "date", "node"], how="left")
gp.to_parquet(dpath("test_grid.parquet"), index=False)
print("\n===== non-overlapping grid rows with a premium and a state =====")
grows = []
for (tic, node), g in gp.groupby(["ticker", "node"]):
    grows.append({"ticker": tic, "node": int(node), "grid_dates": len(g),
                  "mf_premium": int(g.logratio_mf.notna().sum()),
                  "atm_premium": int(g.logratio_atm.notna().sum()),
                  "mf_and_z": int((g.logratio_mf.notna() & g.z_t.notna()).sum()),
                  "atm_and_z": int((g.logratio_atm.notna() & g.z_t.notna()).sum())})
gt = pd.DataFrame(grows)
print(gt.to_string(index=False))

print("\n===== gold and silver: last date with a state, for the disclosure A5 requires =====")
for tic in ["GLD", "SLV"]:
    g = cw[(cw.ticker == tic) & cw.z_t.notna()]
    src = cs[(cs.commodity == MAP[tic]) & cs.z_t.notna()]
    print("%s: z_t spans %s .. %s, %d dates; spliced source present after 2022-12-28: %d dates"
          % (tic, g.date.min().date(), g.date.max().date(), int(g.date.nunique()),
             int((src.date > "2022-12-28").sum())))

dump_json("s2_step2_panel.json", {"daily": t.to_dict("records"), "grid": gt.to_dict("records"),
                                  "panel_rows": len(panel), "grid_rows": len(gp)})
