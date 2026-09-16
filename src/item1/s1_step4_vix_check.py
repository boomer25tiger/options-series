"""Step 4: validate the SPX 30-day model-free volatility against VIX (spec 6.1).

Stop rule: correlation below 0.98, or median absolute gap above 1 vol point, stops
session 1 here.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath, COMMON_START, COMMON_END
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

log_to("s1_step4_vix_check.log")

CORR_FLOOR = 0.98      # spec 6.1
MEDIAN_GAP_CEIL = 1.0  # vol points, spec 6.1

mf = pd.read_parquet(dpath("mfiv.parquet"))
vix = pd.read_parquet(dpath("vix.parquet"))

spx = mf[(mf.ticker == "SPX") & (mf.node == 30) & (mf.drop_code == "OK")].copy()
spx["mfvol"] = np.sqrt(spx.mfiv) * 100.0
spx = spx[["date", "mfvol", "mfiv", "expiry_low", "expiry_high"]]
print("SPX 30-day model-free series, drop_code OK: %d dates, %s .. %s"
      % (len(spx), spx.date.min().date(), spx.date.max().date()))
print("VIX series: %d dates, %s .. %s"
      % (len(vix), vix.date.min().date(), vix.date.max().date()))

m = spx.merge(vix[["date", "vix"]], on="date", how="inner").dropna(subset=["mfvol", "vix"])
m["diff"] = m.mfvol - m.vix
m["absdiff"] = m["diff"].abs()
m["dte_low"] = (m.expiry_low - m.date).dt.days
m["dte_high"] = (m.expiry_high - m.date).dt.days
print("\noverlap used for the check: %d dates, %s .. %s"
      % (len(m), m.date.min().date(), m.date.max().date()))

corr = float(np.corrcoef(m.mfvol, m.vix)[0, 1])
mean_d = float(m["diff"].mean())
med_d = float(m["diff"].median())
med_abs = float(m["absdiff"].median())
n_gt2 = int((m.absdiff > 2).sum())
share_gt2 = float((m.absdiff > 2).mean())

print("\n===== SECTION 6.1 VALIDATION =====")
print("correlation of levels (sqrt(mfiv)*100 vs VIX close) : %.6f" % corr)
print("mean   level difference (model-free minus VIX)      : %+.4f vol points" % mean_d)
print("median level difference                             : %+.4f vol points" % med_d)
print("median ABSOLUTE gap                                 : %.4f vol points" % med_abs)
print("dates differing by more than 2 vol points           : %d of %d (share %.4f)"
      % (n_gt2, len(m), share_gt2))
print("\nadditional detail (not part of the rule):")
print("  sd of difference        : %.4f" % m["diff"].std())
print("  90th pct absolute gap   : %.4f" % m.absdiff.quantile(0.90))
print("  max absolute gap        : %.4f on %s"
      % (m.absdiff.max(), m.loc[m.absdiff.idxmax(), "date"].date()))
print("  bracketing dte, median  : low %d, high %d" % (m.dte_low.median(), m.dte_high.median()))
print("\n  by year:")
by = m.groupby(m.date.dt.year).agg(
    n=("diff", "size"), corr=("diff", lambda s: np.nan),
    mean_diff=("diff", "mean"), median_diff=("diff", "median"),
    median_absdiff=("absdiff", "median"), share_gt2=("absdiff", lambda s: (s > 2).mean()))
for y, g in m.groupby(m.date.dt.year):
    by.loc[y, "corr"] = np.corrcoef(g.mfvol, g.vix)[0, 1] if len(g) > 2 else np.nan
print(by.round(4).to_string())

passed = (corr >= CORR_FLOOR) and (med_abs <= MEDIAN_GAP_CEIL)
print("\ncorrelation >= %.2f      : %s (%.6f)" % (CORR_FLOOR, corr >= CORR_FLOOR, corr))
print("median absolute gap <= %.1f : %s (%.4f)" % (MEDIAN_GAP_CEIL, med_abs <= MEDIAN_GAP_CEIL, med_abs))
print("\nVALIDATION %s" % ("PASSED - session continues to step 5"
                           if passed else "FAILED - STOP RULE FIRES, session ends at step 4"))

m.to_parquet(opath("vix_check.parquet"), index=False)

fig, ax = plt.subplots(1, 2, figsize=(13, 5.2))
ax[0].scatter(m.vix, m.mfvol, s=3, alpha=0.25, color="#1f4e79", edgecolors="none")
lim = [0, max(m.vix.max(), m.mfvol.max()) * 1.05]
ax[0].plot(lim, lim, color="#c00000", lw=1, ls="--", label="45 degrees")
ax[0].set_xlim(lim); ax[0].set_ylim(lim)
ax[0].set_xlabel("VIX close (vol points)")
ax[0].set_ylabel("SPX 30-day model-free vol, sqrt(mfiv) x 100")
ax[0].set_title("Levels, n = %d, corr = %.4f" % (len(m), corr))
ax[0].legend(frameon=False, fontsize=9)
ax[0].grid(alpha=0.25, lw=0.5)

ax[1].plot(m.date, m.vix, lw=0.7, color="#c00000", label="VIX close")
ax[1].plot(m.date, m.mfvol, lw=0.7, color="#1f4e79", alpha=0.8, label="model-free 30-day")
ax[1].set_ylabel("vol points")
ax[1].set_title("Overlay, %s to %s" % (m.date.min().date(), m.date.max().date()))
ax[1].legend(frameon=False, fontsize=9)
ax[1].grid(alpha=0.25, lw=0.5)
fig.suptitle("Section 6.1 validation: SPX model-free 30-day volatility against VIX", y=0.99)
fig.tight_layout()
fig.savefig(opath("fig_vix_check.png"), dpi=150)
print("\nwrote %s" % opath("fig_vix_check.png"))

dump_json("s1_step4_vix_check.json", {
    "n_overlap": len(m),
    "first_date": str(m.date.min().date()), "last_date": str(m.date.max().date()),
    "correlation": corr, "mean_diff": mean_d, "median_diff": med_d,
    "median_abs_diff": med_abs,
    "n_gt_2_vol_points": n_gt2, "share_gt_2_vol_points": share_gt2,
    "sd_diff": float(m["diff"].std()),
    "p90_abs_diff": float(m.absdiff.quantile(0.90)),
    "max_abs_diff": float(m.absdiff.max()),
    "corr_floor": CORR_FLOOR, "median_gap_ceiling": MEDIAN_GAP_CEIL,
    "passed": bool(passed),
    "by_year": by.reset_index().rename(columns={"date": "year"}).to_dict("records"),
})
