"""Step 6: Q3 commonality, section 6.6 under A5.

Number one: the share of total variance explained by the first principal component of
the four daily log ratios. Number two: the same after residualising each series on its
own z_t by OLS. Correlation matrices are pairwise-complete (A5), so the matrix need not
be positive semi-definite; the denominator is the trace, which is exactly 4 for a
correlation matrix, and any negative eigenvalue is reported.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath
import numpy as np
import pandas as pd
import statsmodels.api as sm
pd.set_option("display.width", 300); pd.set_option("display.max_rows", 200)

log_to("s2_step6_q3.log")
ETFS = ["GLD", "SLV", "USO", "UNG"]
COL = {"mf": "logratio_mf", "atm": "logratio_atm"}

panel = pd.read_parquet(dpath("test_panel.parquet"))
cw = panel[panel.in_common]


def first_share(C):
    ev = np.linalg.eigvalsh(C)
    ev = ev[::-1]
    return float(ev[0] / C.shape[0]), [float(x) for x in ev]


def wide(node, col, resid=False):
    fr = {}
    for tic in ETFS:
        d = cw[(cw.ticker == tic) & (cw.node == node)][["date", col, "z_t"]].dropna(subset=[col])
        if resid:
            d = d.dropna(subset=["z_t"])
            X = sm.add_constant(d.z_t.values, has_constant="add")
            d = d.assign(**{col: sm.OLS(d[col].values, X).fit().resid})
        fr[tic] = d.set_index("date")[col]
    return pd.DataFrame(fr)


out = {"nodes": {}}
for node in (30, 91):
    print("\n################ node %d ################" % node)
    rec = {}
    for series, col in (("mf", COL["mf"]), ("atm", COL["atm"])):
        # window where all four z_t exist
        zall = None
        for tic in ETFS:
            d = cw[(cw.ticker == tic) & (cw.node == node)]
            s = set(d.loc[d.z_t.notna(), "date"])
            zall = s if zall is None else (zall & s)
        zall = pd.DatetimeIndex(sorted(zall))
        W = wide(node, col)
        Wz = W.loc[W.index.isin(zall)]
        Rz = Wz.corr(min_periods=30)
        share_before, ev_b = first_share(Rz.values)
        Wr = wide(node, col, resid=True)
        Wrz = Wr.loc[Wr.index.isin(zall)]
        Rr = Wrz.corr(min_periods=30)
        share_after, ev_a = first_share(Rr.values)
        Rfull = W.corr(min_periods=30)
        share_full, ev_f = first_share(Rfull.values)
        print("\n--- %s series ---" % series)
        print("window where all four z_t exist: %d dates, %s .. %s"
              % (len(zall), zall.min().date(), zall.max().date()))
        print("first-component share BEFORE conditioning : %.4f" % share_before)
        print("first-component share AFTER  conditioning : %.4f" % share_after)
        print("change                                    : %+.4f" % (share_after - share_before))
        print("unconditioned share on the FULL common window (reference): %.4f  (%d dates)"
              % (share_full, len(W.dropna(how="all"))))
        print("eigenvalues before %s ; after %s"
              % (np.round(ev_b, 4).tolist(), np.round(ev_a, 4).tolist()))
        print("\npairwise correlations BEFORE:")
        print(Rz.round(4).to_string())
        print("pairwise correlations AFTER:")
        print(Rr.round(4).to_string())
        print("pairwise complete-observation counts (before):")
        print(Wz.notna().astype(int).T.dot(Wz.notna().astype(int)).to_string())
        rec[series] = {
            "z_window_dates": len(zall), "z_first": str(zall.min().date()),
            "z_last": str(zall.max().date()),
            "share_before": share_before, "share_after": share_after,
            "change": share_after - share_before,
            "share_full_common_window": share_full,
            "full_window_dates": int(len(W.dropna(how="all"))),
            "eigenvalues_before": ev_b, "eigenvalues_after": ev_a,
            "corr_before": Rz.round(6).to_dict(), "corr_after": Rr.round(6).to_dict(),
            "min_eigenvalue_before": min(ev_b), "min_eigenvalue_after": min(ev_a),
            "pair_counts": Wz.notna().astype(int).T.dot(Wz.notna().astype(int)).to_dict(),
            "mean_abs_corr_before": float(np.abs(Rz.values[np.triu_indices(4, 1)]).mean()),
            "mean_abs_corr_after": float(np.abs(Rr.values[np.triu_indices(4, 1)]).mean()),
        }
    out["nodes"][str(node)] = rec

print("\n===== Q3 summary =====")
rows = []
for node in (30, 91):
    for series in ("mf", "atm"):
        r = out["nodes"][str(node)][series]
        rows.append([node, series, r["z_window_dates"], round(r["share_before"], 4),
                     round(r["share_after"], 4), round(r["change"], 4),
                     round(r["share_full_common_window"], 4),
                     round(r["mean_abs_corr_before"], 4), round(r["mean_abs_corr_after"], 4)])
print(pd.DataFrame(rows, columns=["node", "series", "dates", "share_before", "share_after",
                                  "change", "share_full_window", "mean|corr| before",
                                  "mean|corr| after"]).to_string(index=False))
print("\nWith four series the first component is always a large share; section 6.6 says so.")
dump_json("s2_step6_q3.json", out)
