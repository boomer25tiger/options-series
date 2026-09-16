"""Assemble output/item1/RESULTS.md from the measured artifacts."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import opath, dpath, COMMON_START, COMMON_END
import numpy as np
import pandas as pd

def J(n):
    with open(opath(n)) as f:
        return json.load(f)

L = []
def w(s=""):
    L.append(s)

def table(headers, rows):
    w("| " + " | ".join(str(h) for h in headers) + " |")
    w("|" + "|".join("---" for _ in headers) + "|")
    for r in rows:
        w("| " + " | ".join("" if c is None or (isinstance(c, float) and not np.isfinite(c))
                            else str(c) for c in r) + " |")
    w()

def p(x, nd=4):
    if x is None or not np.isfinite(x):
        return ""
    if x == 0:
        return "<0.0005"
    if x < 0.0001:
        return "%.2e" % x
    return ("%%.%df" % nd) % x

def f(x, nd=4):
    return "" if x is None or not np.isfinite(x) else ("%%.%df" % nd) % x

H1 = pd.read_pickle(opath("s2_h1_raw.pkl"))
H2 = pd.read_pickle(opath("s2_h2_raw.pkl"))
PO = J("s2_step4b_pooled.json")
Q3 = J("s2_step6_q3.json")
CU = J("s2_step1c_curve.json")
CR = J("s2_step1b_contrule.json")
SS = pd.read_csv(opath("s2_sign_split.csv")).rename(columns={"mean": "mean_lr"})
po = pd.DataFrame(PO["rows"])

h30 = po[(po.node == 30) & (po.series == "atm")].iloc[0]
h30mf = po[(po.node == 30) & (po.series == "mf")].iloc[0]

w("# Item 1 — results")
w()
w("Every number below is measured and citable. Sample ends **%s**. Inference follows"
  % COMMON_END)
w("section 7: Newey-West and block bootstrap must both clear the Holm-corrected level")
w("within their block for a hypothesis to be reported as supported.")
w()
w("## Headline")
w()
w("**Pooled H1 at the 30-day node: mean log(IV²/RV) = %.4f, Newey-West 95 percent interval"
  % h30.estimate)
w("[%.4f, %.4f], on %s daily observations.** Block-bootstrap interval [%.4f, %.4f]."
  % (h30.nw_ci_lo, h30.nw_ci_hi, "{:,}".format(int(h30.n_dates_all_four)),
     h30.boot_ci_lo, h30.boot_ci_hi))
w("All four inference rows give p below 0.0005.")
w()
w("- **Sample end: %s.**" % COMMON_END)
w("- **H1 is supported.** All eight tests — four ETFs at two maturities — clear the")
w("  Holm-corrected level on both the Newey-West and the block-bootstrap row.")
w("- **H2 is not supported.** Nine of the ten tests fail on both rows; SLV at 30 days is")
w("  \"not robust to inference method\". This is null B of section 12.")
w("- **Q3 is unchanged by conditioning.** The first-component share moves by between")
w("  %+.4f and %+.4f after residualising each premium on its own z_t. This is null C."
  % (min(Q3["nodes"][n][s]["change"] for n in ("30", "91") for s in ("mf", "atm")),
     max(Q3["nodes"][n][s]["change"] for n in ("30", "91") for s in ("mf", "atm"))))
w()

w("## Pooled H1 (section 11) — outside the eighteen-test family")
w()
w("**Definition, fixed in session 2 before the number was computed:** the equal-weighted")
w("average across GLD, SLV, USO and UNG of the daily log(IV²/RV), computed on the **ATM**")
w("series for all four so that one measure covers every ETF at full retention. Averaging")
w("across ETFs per date and then running the section 7 inference on that single series")
w("carries the cross-sectional dependence among the four premia into the standard errors.")
w("The model-free pooled number is reported alongside on the dates where all four")
w("model-free series exist. This number is **not** one of the eighteen tests and carries no")
w("Holm correction.")
w()
table(["node", "series", "dates with all four", "span", "pooled mean", "NW 95% interval",
       "p NW", "p HH", "boot 95% interval", "p boot", "grid n", "grid mean", "p grid"],
      [[int(r.node), "ATM" if r.series == "atm" else "model-free",
        "{:,}".format(int(r.n_dates_all_four)), "%s .. %s" % (r.first_date, r.last_date),
        f(r.estimate), "[%s, %s]" % (f(r.nw_ci_lo), f(r.nw_ci_hi)),
        p(r.p_NW), p(r.p_HH), "[%s, %s]" % (f(r.boot_ci_lo), f(r.boot_ci_hi)),
        p(r.p_BOOT), int(r.n_grid), f(r.grid_estimate), p(r.p_GRID)]
       for r in po.sort_values(["node", "series"], ascending=[True, False]).itertuples()])
w("The model-free pooled series rests on **%s** dates at the 30-day node and **%s** at the"
  % ("{:,}".format(int(h30mf.n_dates_all_four)),
     "{:,}".format(int(po[(po.node == 91) & (po.series == 'mf')].iloc[0].n_dates_all_four))))
w("91-day node, against %s and %s for the ATM pooled series, because the model-free"
  % ("{:,}".format(int(h30.n_dates_all_four)),
     "{:,}".format(int(po[(po.node == 91) & (po.series == 'atm')].iloc[0].n_dates_all_four))))
w("construction drops dates that the ATM surface does not. That is the reason the ATM")
w("series is the primary pooled measure.")
w()

# ---------------------------------------------------------------- H1 family ---
w("## H1 — the eight family tests")
w()
w("Headline series per amendment A3(a): the ATM secondary carries GLD, UNG and USO,")
w("because session 1b's selection check found their model-free drops are not independent")
w("of the premium level; SLV keeps the model-free series. Holm is applied within each node")
w("block of four, separately to the Newey-West and the bootstrap p-values.")
w()
fam = H1[H1.in_family].sort_values(["node", "ticker"])
table(["node", "ETF", "headline series", "n", "mean log(IV²/RV)", "p NW", "p HH", "p boot",
       "grid n", "p grid", "Holm level NW", "Holm level boot", "NW clears", "boot clears",
       "verdict"],
      [[int(r.node), r.ticker, "ATM" if r.series == "atm" else "model-free",
        "{:,}".format(int(r.n)), f(r.estimate), p(r.p_NW), p(r.p_HH), p(r.p_BOOT),
        int(r.n_grid), p(r.p_GRID), f(r.holm_level_NW), f(r.holm_level_BOOT),
        "yes" if r.reject_NW else "no", "yes" if r.reject_BOOT else "no",
        "**%s**" % r.verdict] for r in fam.itertuples()])
w("### Both series side by side")
w()
both = H1[(H1.measure == "logratio") & (H1["sample"] == "full") &
          (H1.series.isin(["mf", "atm"])) & (H1.ticker != "SPX")]
table(["node", "ETF", "series", "n", "mean", "p NW", "p HH", "p boot", "p grid", "headline?"],
      [[int(r.node), r.ticker, "ATM" if r.series == "atm" else "model-free",
        "{:,}".format(int(r.n)), f(r.estimate), p(r.p_NW), p(r.p_HH), p(r.p_BOOT),
        p(r.p_GRID), "yes" if r.in_family else ""]
       for r in both.sort_values(["node", "ticker", "series"]).itertuples()])

w("### SPX benchmark — outside the family")
w()
spx = H1[(H1.ticker == "SPX") & (H1.measure == "logratio") & (H1["sample"] == "full") &
         (H1.series.isin(["mf", "atm"]))]
table(["node", "series", "n", "mean", "p NW", "p HH", "p boot", "grid n", "p grid"],
      [[int(r.node), "ATM" if r.series == "atm" else "model-free", "{:,}".format(int(r.n)),
        f(r.estimate), p(r.p_NW), p(r.p_HH), p(r.p_BOOT), int(r.n_grid), p(r.p_GRID)]
       for r in spx.sort_values(["node", "series"]).itertuples()])
w("SPX carries no curve state and enters for H1 only, per section 4.")
w()

w("### H1 robustness rows")
w()
w("**April 2020 excluded** — windows starting 2020-03-01 to 2020-04-30 (section 6.7):")
w()
ex = H1[(H1["sample"] == "ex-Apr2020") & (H1.series.isin(["mf", "atm"]))]
table(["node", "ETF", "series", "n", "mean", "p NW", "p HH", "p boot", "p grid"],
      [[int(r.node), r.ticker, "ATM" if r.series == "atm" else "model-free",
        "{:,}".format(int(r.n)), f(r.estimate), p(r.p_NW), p(r.p_HH), p(r.p_BOOT), p(r.p_GRID)]
       for r in ex.sort_values(["node", "ticker", "series"]).itertuples()])
w("**Floor-of-2 model-free series** (amendment A3(b)):")
w()
f2 = H1[H1.series == "mf_floor2"]
table(["node", "ETF", "n", "mean", "p NW", "p HH", "p boot", "p grid"],
      [[int(r.node), r.ticker, "{:,}".format(int(r.n)), f(r.estimate), p(r.p_NW),
        p(r.p_HH), p(r.p_BOOT), p(r.p_GRID)]
       for r in f2.sort_values(["node", "ticker"]).itertuples()])
w("**IV² − RV in annualised variance points** (section 6.4 secondary):")
w()
df = H1[H1.measure == "diff"]
table(["node", "ETF", "series", "n", "mean IV² − RV", "p NW", "p HH", "p boot", "p grid"],
      [[int(r.node), r.ticker, "ATM" if r.series == "atm" else "model-free",
        "{:,}".format(int(r.n)), f(r.estimate, 6), p(r.p_NW), p(r.p_HH), p(r.p_BOOT),
        p(r.p_GRID)] for r in df.sort_values(["node", "ticker", "series"]).itertuples()])
w("The secondary measure is the one place where the two implied-variance measures part:")
w("on the ATM series USO at both nodes and SPX at 30 days do not clear an uncorrected 0.05,")
w("while every model-free row does. The log ratio, which is the primary measure of section")
w("6.4, is positive and clears on both series for every ETF.")
w()

# ---------------------------------------------------------------- H2 family ---
w("## H2 — the ten family tests")
w()
w("OLS of the headline log ratio on z_t, two-sided, sign not registered. Pooled is the")
w("within-ETF demeaned log ratio on within-ETF demeaned z_t. Holm within each node block")
w("of five, separately on the Newey-West and the bootstrap p-values.")
w()
fam2 = H2[H2.in_family].sort_values(["node", "unit"])
table(["node", "unit", "series", "n", "slope", "p NW", "p HH", "p boot", "grid n", "p grid",
       "Holm level NW", "Holm level boot", "NW clears", "boot clears", "verdict"],
      [[int(r.node), r.unit, "ATM" if r.series == "atm" else
        ("model-free" if r.series == "mf" else r.series),
        "{:,}".format(int(r.n)), f(r.estimate, 3), p(r.p_NW), p(r.p_HH), p(r.p_BOOT),
        int(r.n_grid), p(r.p_GRID), f(r.holm_level_NW), f(r.holm_level_BOOT),
        "yes" if r.reject_NW else "no", "yes" if r.reject_BOOT else "no",
        "**%s**" % r.verdict] for r in fam2.itertuples()])
w("**The raw slope is not comparable across commodities.** z_t for gold and silver is an")
w("order of magnitude smaller than for crude and natural gas, so the coefficients span")
w("three orders of magnitude. Scaled to a one-standard-deviation move in each commodity's")
w("own z_t — a pure rescaling that leaves every t statistic and p value unchanged:")
w()
f3 = pd.read_csv(opath("fig3_table.csv"))
table(["node", "unit", "sd of z_t", "slope per 1 sd", "NW 95% interval", "boot 95% interval",
       "verdict"],
      [[int(r.node), r.unit, "%.5f" % r.sd_z, "%+.4f" % r.est_sd,
        "[%+.4f, %+.4f]" % (r.nw_lo, r.nw_hi), "[%+.4f, %+.4f]" % (r.bt_lo, r.bt_hi),
        r.verdict] for r in f3.sort_values(["node", "unit"]).itertuples()])
_ex_nw = ["%d-day %s" % (int(r.node), r.unit) for r in f3.itertuples()
          if r.nw_lo * r.nw_hi > 0]
_ex_bt = ["%d-day %s" % (int(r.node), r.unit) for r in f3.itertuples()
          if r.bt_lo * r.bt_hi > 0]
w("No effect exceeds %.4f log units per standard deviation in absolute value. The"
  % f3.est_sd.abs().max())
w("Newey-West interval excludes zero for %s; the bootstrap interval excludes zero for %s."
  % (", ".join(_ex_nw) or "no unit", ", ".join(_ex_bt) or "no unit"))
w()
w("Note that an interval excluding zero is **not** the decision rule. Section 7 requires")
w("both p-values to clear the **Holm-corrected** level within their block. SLV at 30 days")
w("has both intervals excluding zero and both uncorrected p-values under 0.05 (NW %.4f,"
  % float(fam2[(fam2.node == 30) & (fam2.unit == "SLV")].p_NW.iloc[0]))
w("bootstrap %.4f), yet its bootstrap p misses the Holm level of %.4f for its rank in the"
  % (float(fam2[(fam2.node == 30) & (fam2.unit == "SLV")].p_BOOT.iloc[0]),
     float(fam2[(fam2.node == 30) & (fam2.unit == "SLV")].holm_level_BOOT.iloc[0])))
w("block of five, so the verdict is \"not robust to inference method\" and not support.")
w()
w("**Gold and silver sample span.** Amendment A5 required these rows to disclose their")
w("sample end. The A5 continuation splice carried both to the full window, so no row is")
w("truncated:")
w()
table(["node", "unit", "z_t first date", "z_t last date"],
      [[int(r.node), r.unit, r.z_first, r.z_last]
       for r in fam2[fam2.unit.isin(["GLD", "SLV"])].itertuples()])
w("### H2 April 2020 exclusion rows")
w()
ex2 = H2[~H2.in_family].sort_values(["node", "unit"])
table(["node", "unit", "n", "slope", "p NW", "p HH", "p boot", "p grid"],
      [[int(r.node), r.unit, "{:,}".format(int(r.n)), f(r.estimate, 3), p(r.p_NW),
        p(r.p_HH), p(r.p_BOOT), p(r.p_GRID)] for r in ex2.itertuples()])
w("Excluding April 2020 does not change the H2 conclusion at the Holm-corrected level for")
w("any unit.")
w()

# --------------------------------------------------------------- sign split ---
w("## Sign split behind figure 2 — no test")
w()
w("Mean log ratio by curve state, headline series per A3(a), with block-bootstrap 95")
w("percent intervals. `n windows` counts **non-overlapping** windows, which is what the")
w("section 5 reporting floor is defined on: under 30 windows a state is reported but not")
w("tested, 30 to 63 is tested with an underpower note, 64 is the power threshold. The split")
w("is nested in H2 and carries no test of its own.")
w()
table(["node", "ETF", "state", "daily obs", "n windows", "mean", "boot 95% interval",
       "section 5 status"],
      [[int(r.node), r.ticker, r.state, "{:,}".format(int(r.n_daily)), int(r.n_windows),
        f(r.mean_lr), "[%s, %s]" % (f(r.ci_lo), f(r.ci_hi)), r.power]
       for r in SS.sort_values(["node", "ticker", "state"]).itertuples()])
n_under = int((SS.n_windows < 64).sum())
w("**%d of the %d state cells fall below the 64-window power threshold**, and %d fall below"
  % (n_under, len(SS), int((SS.n_windows < 30).sum())))
w("the 30-window reporting floor. Backwardation is the scarce state for the metals: silver")
w("has 5 non-overlapping windows in backwardation at 30 days and 2 at 91 days.")
w()

# ----------------------------------------------------------------------- Q3 ---
w("## Q3 — commonality")
w()
w("First-component share of the pairwise-complete correlation matrix of the four daily log")
w("ratios, before and after residualising each on its own z_t by OLS, on the window where")
w("all four z_t exist (A5). With four series a share of 0.25 is what uncorrelated series")
w("would give.")
w()
rows = []
for node in ("30", "91"):
    for s in ("mf", "atm"):
        r = Q3["nodes"][node][s]
        rows.append([int(node), "model-free" if s == "mf" else "ATM",
                     "{:,}".format(r["z_window_dates"]),
                     "%s .. %s" % (r["z_first"], r["z_last"]),
                     f(r["share_before"]), f(r["share_after"]), "%+.4f" % r["change"],
                     f(r["share_full_common_window"]),
                     "{:,}".format(r["full_window_dates"]),
                     f(r["mean_abs_corr_before"]), f(r["mean_abs_corr_after"])])
table(["node", "series", "dates", "span", "share before", "share after", "change",
       "unconditioned share, full common window", "full-window dates",
       "mean absolute correlation before", "mean absolute correlation after"], rows)
w("### Pairwise correlations, model-free")
w()
for node in ("30", "91"):
    r = Q3["nodes"][node]["mf"]
    for lab, key in (("before conditioning", "corr_before"), ("after conditioning", "corr_after")):
        C = pd.DataFrame(r[key])
        w("**%s-day node, %s:**" % (node, lab))
        w()
        table([""] + list(C.columns),
              [[i] + [f(C.loc[i, c]) for c in C.columns] for i in C.index])
w("The first component is a large share before conditioning and the same large share after.")
w("Conditioning on each commodity's own curve slope removes essentially none of the")
w("commonality, which is null C.")
w()

# ------------------------------------------------------------- A5 coverage ---
w("## A5 curve-state coverage")
w()
meta = CU["meta"]
table(["commodity", "underlying for", "incumbent class", "continuation class", "spliced at",
       "dates built", "dropped for null settlement", "span", "coverage share",
       "front-contract switches"],
      [[c, meta[c]["label"], "%g" % meta[c]["incumbent_clscode"],
        ("%g" % meta[c]["continuation_clscode"]) if meta[c]["continuation_clscode"] else "none",
        meta[c]["spliced_at"] or "not spliced", "{:,}".format(meta[c]["dates_built"]),
        meta[c]["dates_dropped_null_settlement"],
        "%s .. %s" % (meta[c]["first_date"], meta[c]["last_date"]),
        f(meta[c]["coverage_share"]), meta[c]["front_switches"]]
       for c in ("GC", "SI", "CL", "NG")])
w("### The A5 continuation rule, applied")
w()
w("A candidate class is accepted only if, on the overlap %s to 2022-12-28, its F1 and F2"
  % COMMON_START)
w("match the class 335 / 3607 construction within 0.5 percent on at least 95 percent of")
w("dates. Candidates were every class with contract values after 2022-12-28 whose exchange")
w("is COMEX or NYMEX by ticker symbol, contract name or continuous-series prefix.")
w()
tests = pd.DataFrame(CR["tests"])
table(["class", "id", "contract", "metal", "overlap dates", "F1 match", "F2 match",
       "dates after 2022-12-28", "accepted"],
      [[int(r.clscode), r.dsclsid, r.contrname, r.metal, "{:,}".format(int(r.overlap_dates)),
        f(r.f1_match), f(r.f2_match), int(r.dates_after_overlap),
        "**yes**" if r.accepted else "no"]
       for r in tests.sort_values(["metal", "clscode"]).itertuples()])
w("Tie-break, stated before it was applied: among accepted candidates that actually extend")
w("the series, take the highest F2 match share, then the highest F1 match share, then the")
w("lowest class code. **Gold takes class 1508 (NGC, GOLD 100 OZ, ticker GC) and silver")
w("class 1574 (NSL, SILVER 5000 OZ, ticker SI), both spliced at 2022-12-28, each adding")
w("669 dates.**")
w()
w("### Curve state")
w()
table(["commodity", "share contango", "share backwardation", "dates dropped for equality",
       "winsorization bounds on z_t", "z_t non-null"],
      [[c, f(meta[c]["share_contango"]), f(meta[c]["share_backwardation"]),
        meta[c]["n_equal"], "[%.6f, %.6f]" % (meta[c]["winsor_lo"], meta[c]["winsor_hi"]),
        "{:,}".format(meta[c]["z_nonnull"])] for c in ("GC", "SI", "CL", "NG")])
w("Crude's 2020-04-20 is present in the data with a negative F1 and is excluded from z_t,")
w("as section 6.5 requires; it remains in s_t, which is a sign and needs no ratio.")
w()

# ------------------------------------------------------------- kill check ---
w("## Section 9 kill check, re-run on the A5 series")
w()
w("Common window trade dates **%s**; the 80 percent floor is **%.1f** dates."
  % ("{:,}".format(CU["spx_trade_dates"]), CU["coverage_floor"] * CU["spx_trade_dates"]))
w()
table(["commodity", "underlying for", "coverage share", "clears 80 percent", "spliced at",
       "outcome"],
      [[r["commodity"], r["underlying_for"], f(r["coverage_share"]),
        "yes" if r["clears_80pct"] else "no", r["spliced_at"] or "not spliced",
        "**%s**" % r["outcome"]] for r in CU["killcheck"]])
w("**Curve state is retained for all four commodities**, so section 9's unconditional")
w("branch does not fire and H2 and Q3 are measurable as specified. This reverses session")
w("1's null D and session 1b's three-of-four drop; the cause is amendment A5, which moved")
w("the construction from Datastream's pre-built continuous series to the contract-level")
w("settlement table.")
w()

path = opath("RESULTS.md")
with open(path, "w") as fh:
    fh.write("\n".join(L) + "\n")
print("wrote %s (%d lines, %d bytes)" % (path, len(L), os.path.getsize(path)))
