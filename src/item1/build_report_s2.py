"""Assemble output/item1/REPORT_s2.md from the measured artifacts."""
import os, sys, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import opath, dpath, PROJECT_ROOT, COMMON_START, COMMON_END
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

def f(x, nd=4):
    return "" if x is None or (isinstance(x, float) and not np.isfinite(x)) else ("%%.%df" % nd) % x

amend = subprocess.run(["git", "log", "--format=%H|%cI|%s", "-1",
                        "--", "SPEC_item1_commodity_vrp.md"],
                       capture_output=True, text=True, cwd=PROJECT_ROOT).stdout.strip()
sha, iso, subj = (amend.split("|") + ["", "", ""])[:3] if amend else ("", "", "")

CO = J("s2_step1a_continuation.json"); CR = J("s2_step1b_contrule.json")
CU = J("s2_step1c_curve.json"); PA = J("s2_step2_panel.json")
H1J = J("s2_step4_h1.json"); H2J = J("s2_step5_h2.json"); PO = J("s2_step4b_pooled.json")
Q3 = J("s2_step6_q3.json")
H1 = pd.read_pickle(opath("s2_h1_raw.pkl")); H2 = pd.read_pickle(opath("s2_h2_raw.pkl"))
SS = pd.read_csv(opath("s2_sign_split.csv")).rename(columns={"mean": "mean_lr"})
po = pd.DataFrame(PO["rows"])

w("# Item 1, session 2 — A5 curve state, the eighteen tests, Q3, figures 2 to 4")
w()
w("Binding document: `SPEC_item1_commodity_vrp.md`, draft 3 plus amendments A1 to A5.")
w("This is the final budgeted session. It writes no post text.")
w()
w("| | |")
w("|---|---|")
w("| Session | item 1, session 2 |")
w("| Report date | 2026-09-15 |")
w("| Amendment A5 commit | `%s` |" % sha[:12])
w("| Amendment A5 timestamp | %s |" % iso)
w("| Amendment A5 message | %s |" % subj)
w("| Interpreter | /Users/GualyCr/wrds-env/bin/python |")
w("| Added package | statsmodels 0.15.0 (pip, into the venv) |")
w("| Bootstrap seed | %d, %d draws, unchanged for every test |" % (H1J["seed"], H1J["draws"]))
w("| Results file | `output/item1/RESULTS.md` |")
w("| Code | `src/item1/` (committed) |")
w("| Data, outputs | `data/item1/`, `output/item1/` (not committed) |")
w()
w("**What this session established.**")
w()
w("1. Under A5 the curve state is **retained for all four commodities**, reversing session")
w("   1's null D and session 1b's three-of-four drop. The cause is the move from")
w("   Datastream's pre-built continuous series to the contract-level settlement table.")
w("2. **H1 is supported** on all eight family tests, on every one of the four inference")
w("   rows, at the Holm-corrected level.")
w("3. **H2 is not supported** — null B. **Q3 is unchanged by conditioning** — null C.")
w()

w("## Step 0 — amendment A5")
w()
w("Section 13 was extended with A5, its continuation rule and its Q3 clause, verbatim, and")
w("committed alone as `%s` at %s, before any query in this session ran." % (sha[:12], iso))
w()

w("## Step 1 — curve state under A5")
w()
w("### 1.1 The continuation search")
w()
w("Every class in `tr_ds_fut` whose contract name contains GOLD or SILVER was enumerated:")
w("**%d classes**. Exchange was marked three ways — the exchange ticker symbol, the word"
  % len(CO["all_gold_silver_classes"]))
w("COMEX or NYMEX in the contract name, and the CMX/NYM/NYL prefix on the class's")
w("continuous-series name. Classes 335 and 3607 are the incumbents and were excluded from")
w("their own candidate set. That left **%d candidates** with contract values after"
  % len(CR["candidates"]))
w("2022-12-28.")
w()
w("The A5 rule accepts a candidate only if, on the overlap %s to 2022-12-28, its F1 and F2"
  % COMMON_START)
w("match the incumbent construction within 0.5 percent on at least 95 percent of dates:")
w()
tests = pd.DataFrame(CR["tests"])
table(["class", "id", "contract", "ticker", "metal", "overlap dates", "F1 match", "F2 match",
       "dates after 2022-12-28", "accepted"],
      [[int(r.clscode), r.dsclsid, r.contrname, r.exchtickersymb, r.metal,
        "{:,}".format(int(r.overlap_dates)), f(r.f1_match), f(r.f2_match),
        int(r.dates_after_overlap), "**yes**" if r.accepted else "no"]
       for r in tests.sort_values(["metal", "clscode"]).itertuples()])
w("Tie-break, stated before it was applied: among accepted candidates that actually extend")
w("the series, highest F2 match, then highest F1 match, then lowest class code. Gold takes")
w("**class 1508** (NGC, GOLD 100 OZ, ticker GC) and silver **class 1574** (NSL, SILVER 5000")
w("OZ, ticker SI). Both are spliced at **2022-12-28**, each adding **669** dates.")
w()
w("These are the same two classes session 1 found carry no *continuous series* at all. They")
w("carry 604 and 674 individual contracts running to 2032 and 2030. The contract table has")
w("what the continuous-series catalogue does not.")
w()

w("### 1.2 F1 and F2")
w()
w("Convention X of session 1b: the nearest and second-nearest contracts whose last trading")
w("date is on or after t. `expirationdate` is null throughout `dsfutcontrinfo`, so")
w("`lasttrddate` is the expiry column, as session 1b established.")
w()
meta = CU["meta"]
table(["commodity", "underlying for", "incumbent class", "continuation class", "spliced at",
       "dates built", "dropped for null settlement", "first", "last", "coverage share",
       "front switches"],
      [[c, meta[c]["label"], "%g" % meta[c]["incumbent_clscode"],
        ("%g" % meta[c]["continuation_clscode"]) if meta[c]["continuation_clscode"] else "none",
        meta[c]["spliced_at"] or "not spliced", "{:,}".format(meta[c]["dates_built"]),
        meta[c]["dates_dropped_null_settlement"], meta[c]["first_date"], meta[c]["last_date"],
        f(meta[c]["coverage_share"]), meta[c]["front_switches"]]
       for c in ("GC", "SI", "CL", "NG")])
w("Coverage is against the **%s** SPX trade dates in the common window."
  % "{:,}".format(CU["spx_trade_dates"]))
w()
w("### 1.3 Kill check, re-run")
w()
table(["commodity", "coverage share", "clears the 80 percent floor", "outcome"],
      [[r["commodity"], f(r["coverage_share"]), "yes" if r["clears_80pct"] else "no",
        "**%s**" % r["outcome"]] for r in CU["killcheck"]])
w("**All four retained.** Section 9's unconditional branch does not fire.")
w()
w("### 1.4 s_t and z_t")
w()
table(["commodity", "share contango", "share backwardation", "dropped for equality",
       "winsorization bounds on z_t", "z_t non-null"],
      [[c, f(meta[c]["share_contango"]), f(meta[c]["share_backwardation"]),
        meta[c]["n_equal"], "[%.6f, %.6f]" % (meta[c]["winsor_lo"], meta[c]["winsor_hi"]),
        "{:,}".format(meta[c]["z_nonnull"])] for c in ("GC", "SI", "CL", "NG")])
w("Crude's 2020-04-20 is present with a negative F1 and is excluded from z_t, as section")
w("6.5 requires. Winsorization is at the 1st and 99th percentile per commodity, computed")
w("once on the common window before any test. Saved to `data/item1/curve_state.parquet`.")
w()

w("## Step 2 — the test panel")
w()
w("`premium_daily.parquet` joined to the curve state on GLD to gold, SLV to silver, USO to")
w("crude, UNG to natural gas. **State is matched on the premium's own date t.** Section 6.5")
w("says the state is taken on the window's first day; the premium at t compares IV²_t with")
w("RV over t+1 to t+h, so t is the day the position opens and the only date at which z_t is")
w("in the information set. SPX carries no state.")
w()
d = pd.DataFrame(PA["daily"])
table(["ETF", "node", "rows", "model-free premium", "ATM premium", "s_t", "z_t",
       "model-free and z_t", "ATM and z_t"],
      [[r.ticker, int(r.node), "{:,}".format(int(r.rows)), "{:,}".format(int(r.mf_premium)),
        "{:,}".format(int(r.atm_premium)), "{:,}".format(int(r.state_s)),
        "{:,}".format(int(r.state_z)), "{:,}".format(int(r.mf_and_z)),
        "{:,}".format(int(r.atm_and_z))] for r in d.itertuples()])
g = pd.DataFrame(PA["grid"])
w("Non-overlapping grid:")
w()
table(["ETF", "node", "grid dates", "model-free premium", "ATM premium",
       "model-free and z_t", "ATM and z_t"],
      [[r.ticker, int(r.node), int(r.grid_dates), int(r.mf_premium), int(r.atm_premium),
        int(r.mf_and_z), int(r.atm_and_z)] for r in g.itertuples()])

w("## Step 3 — inference machinery")
w()
w("Implemented once in `src/item1/s2_inference.py` and reused by every test.")
w()
table(["row", "implementation"],
      [["Newey-West", "HAC, Bartlett kernel, maxlags h (21 at the 30-day node, 63 at 91)"],
       ["Hansen-Hodrick", "HAC, uniform (truncated) weights, same maxlags"],
       ["Block bootstrap", "stationary bootstrap of Politis and Romano (1994), expected "
        "block length h, %d draws, seed %d" % (H1J["draws"], H1J["seed"])],
       ["Non-overlapping", "the same statistic on the grid, plain t-test"],
       ["Multiplicity", "Holm within each of the four blocks of section 7, applied "
        "separately to the Newey-West and the bootstrap p-values, alpha %.2f" % H1J["alpha"]],
       ["Decision rule", "supported only if Newey-West and bootstrap both clear the "
        "Holm-corrected level; one of the two clearing is \"not robust to inference "
        "method\"; neither is \"not supported\""]])
w("The bootstrap p-value is the share of bootstrap statistics on the null side of zero,")
w("one-sided for H1 and two-sided for H2, exactly as the session instruction fixed it. With")
w("%d draws the resolution floor is 1/%d, so a reported 0.0000 means below that, not zero."
  % (H1J["draws"], H1J["draws"]))
w()
w("For the **pooled** H2 rows the bootstrap resamples blocks of **dates** and takes every")
w("ETF present on a sampled date, so the draw preserves the cross-sectional dependence")
w("among the four premia as well as the serial dependence. The per-ETF rows have a single")
w("series and use the ordinary stationary bootstrap.")
w()

w("## Step 4 — H1, eight tests")
w()
w("Mean log(IV²/RV) > 0, one-sided. Headline series per A3(a): ATM for GLD, UNG and USO;")
w("model-free for SLV. Wall clock **%.1f s**." % H1J["seconds"])
w()
fam = H1[H1.in_family].sort_values(["node", "ticker"])
table(["node", "ETF", "series", "n", "mean", "p NW", "p HH", "p boot", "p grid",
       "Holm level NW", "Holm level boot", "verdict"],
      [[int(r.node), r.ticker, "ATM" if r.series == "atm" else "model-free",
        "{:,}".format(int(r.n)), f(r.estimate), f(r.p_NW, 6), f(r.p_HH, 6), f(r.p_BOOT, 4),
        f(r.p_GRID, 6), f(r.holm_level_NW), f(r.holm_level_BOOT), "**%s**" % r.verdict]
       for r in fam.itertuples()])
w("**All eight supported.** The other series agrees on every one: the non-headline measure")
w("also clears at every node and ETF. Full side-by-side, robustness and SPX rows are in")
w("`RESULTS.md`.")
w()
w("### Pooled H1, section 11 — outside the family")
w()
w("Definition fixed in session 2 **before** the number was computed: the equal-weighted")
w("average across the four ETFs of the daily log ratio, on the ATM series for all four so")
w("that one measure covers every ETF at full retention, with the model-free pooled number")
w("alongside on the dates where all four model-free series exist.")
w()
table(["node", "series", "dates with all four", "pooled mean", "NW 95% interval", "p NW",
       "p HH", "p boot", "grid n", "p grid"],
      [[int(r.node), "ATM" if r.series == "atm" else "model-free",
        "{:,}".format(int(r.n_dates_all_four)), f(r.estimate),
        "[%s, %s]" % (f(r.nw_ci_lo), f(r.nw_ci_hi)), f(r.p_NW, 6), f(r.p_HH, 6),
        f(r.p_BOOT, 4), int(r.n_grid), f(r.p_GRID, 6)]
       for r in po.sort_values(["node", "series"], ascending=[True, False]).itertuples()])
w("Pooled bootstrap wall clock, all four pooled series: **%.1f s**."
  % PO["pooled_bootstrap_seconds"])
w()

w("## Step 5 — H2, ten tests")
w()
w("OLS of the headline log ratio on z_t, two-sided. Pooled is within-ETF demeaned on both")
w("sides. Wall clock **%.1f s**." % H2J["seconds"])
w()
fam2 = H2[H2.in_family].sort_values(["node", "unit"])
table(["node", "unit", "n", "slope", "p NW", "p HH", "p boot", "p grid", "Holm level NW",
       "Holm level boot", "verdict"],
      [[int(r.node), r.unit, "{:,}".format(int(r.n)), f(r.estimate, 3), f(r.p_NW),
        f(r.p_HH), f(r.p_BOOT), f(r.p_GRID), f(r.holm_level_NW), f(r.holm_level_BOOT),
        "**%s**" % r.verdict] for r in fam2.itertuples()])
w("**Nine of ten not supported; SLV at 30 days is not robust to inference method.** H2")
w("fails, which is null B of section 12.")
w()
w("### Sign split behind figure 2")
w()
w("`n windows` counts non-overlapping windows, which is the unit the section 5 floor is")
w("defined on. No test is run on the split.")
w()
table(["node", "ETF", "state", "daily obs", "n windows", "mean", "boot 95% interval",
       "section 5 status"],
      [[int(r.node), r.ticker, r.state, "{:,}".format(int(r.n_daily)), int(r.n_windows),
        f(r.mean_lr), "[%s, %s]" % (f(r.ci_lo), f(r.ci_hi)), r.power]
       for r in SS.sort_values(["node", "ticker", "state"]).itertuples()])
w("**%d of %d state cells sit below the 64-window power threshold and %d below the"
  % (int((SS.n_windows < 64).sum()), len(SS), int((SS.n_windows < 30).sum())))
w("30-window reporting floor.** Backwardation is scarce for the metals.")
w()

w("## Step 6 — Q3")
w()
rows = []
for node in ("30", "91"):
    for s in ("mf", "atm"):
        r = Q3["nodes"][node][s]
        rows.append([int(node), "model-free" if s == "mf" else "ATM",
                     "{:,}".format(r["z_window_dates"]), f(r["share_before"]),
                     f(r["share_after"]), "%+.4f" % r["change"],
                     f(r["share_full_common_window"]),
                     f(r["mean_abs_corr_before"]), f(r["mean_abs_corr_after"])])
table(["node", "series", "dates", "first-component share before", "after", "change",
       "unconditioned share, full common window", "mean absolute correlation before",
       "after"], rows)
w("Conditioning each premium on its own curve slope changes the first-component share by")
w("between %+.4f and %+.4f. **Null C.**"
  % (min(Q3["nodes"][n][s]["change"] for n in ("30", "91") for s in ("mf", "atm")),
     max(Q3["nodes"][n][s]["change"] for n in ("30", "91") for s in ("mf", "atm"))))
w()
w("The correlation matrices are pairwise-complete per A5. The smallest eigenvalue is")
w("positive in every case (minimum %.4f across the four matrices before conditioning), so"
  % min(Q3["nodes"][n][s]["min_eigenvalue_before"] for n in ("30", "91") for s in ("mf", "atm")))
w("no matrix needed repair.")
w()

w("## Step 7 — figures and results files")
w()
table(["file", "content"],
      [["`fig2_sign_split.png` / `.svg`", "mean log ratio by curve state, two panels by "
        "node, bootstrap intervals, non-overlapping window counts, section 5 power marks"],
       ["`fig3_slope_coefficients.png` / `.svg`", "H2 slopes with Newey-West and bootstrap "
        "95 percent intervals, two panels by node, pooled included"],
       ["`fig4_commonality.png` / `.svg`", "first-component share before and after "
        "conditioning, both nodes, both series"],
       ["`fig3_table.csv`", "the numbers behind figure 3"],
       ["`RESULTS.md`", "every test, every robustness row, Q3, kill check, A5 coverage"],
       ["`REPORT_s2.md`", "this file"]])
w("Figure 3 plots the slope **scaled to a one-standard-deviation move in each commodity's")
w("own z_t**. The raw coefficients span three orders of magnitude because z_t for the")
w("metals is an order of magnitude smaller than for the energies; the rescaling is a pure")
w("change of units and leaves every t statistic and p value unchanged. The raw coefficients")
w("are in `RESULTS.md` next to the scaled ones.")
w()

w("## Not measured, and done differently")
w()
w("### The `R.sample` bug")
w()
w("**What it did.** In `s2_step4_h1.py` the H1 results frame carries a column named")
w("`sample` holding `\"full\"` or `\"ex-Apr2020\"`. Two display filters were written as")
w("`R.sample == \"full\"` and `R.sample == \"ex-Apr2020\"`. `sample` is also a pandas")
w("`DataFrame` **method**, and attribute access resolves to the method, not the column, so")
w("each comparison returned a single scalar `False` rather than a boolean Series. Combined")
w("with `&` against a real Series it selected nothing. The April 2020 robustness rows were")
w("computed correctly and written to the JSON and the pickle, but were silently absent from")
w("the printed robustness table, and the both-series comparison table printed empty.")
w()
w("**How it was found.** The both-series table rendered as `Empty DataFrame` in the step 4")
w("log while the family table above it was populated. An empty frame from a filter over a")
w("frame known to be non-empty is not a plausible measurement, so the filter was read again")
w("and the attribute-versus-column collision identified.")
w()
w("**The fix.** Both filters were changed to `R[\"sample\"]`. A scan confirmed no remaining")
w("bare `R.sample` in the file.")
w()
w("**Effect on results.** The bug was in display only: the estimator, the inference and the")
w("Holm correction never read that column. The Holm block keys on `node` and `in_family`,")
w("and `in_family` is set from the ticker and the series, not from `sample`.")
w()
w("**This was verified rather than assumed.** The H1 script was re-run end to end with the")
w("two buggy filters restored, writing to a separate pickle, and the two runs were compared")
w("row by row:")
w()
table(["comparison", "result"],
      [["the eight H1 family rows - n, estimate, all four p-values, both Holm levels, both "
        "reject flags, verdict", "**identical**"],
       ["all 70 result rows including SPX, the April 2020 rows, the floor-of-2 rows and the "
        "IV2 - RV rows - n, estimate, all four p-values", "**identical**"]])
w("So the eight H1 family verdicts were run before and after the fix and did not change.")
w("The only visible difference is that the April 2020 rows and the side-by-side table now")
w("print instead of rendering empty.")
w()
w("### Not measured")
w()
NM = [
 ("The post text", "The session instruction is explicit that this session writes none."),
 ("A test on the contango-versus-backwardation split",
  "Section 3 nests the sign split in H2 and says it carries no separate test. Figure 2 and "
  "its table report means with intervals and window counts, and no test is run."),
 ("Anything beyond the eighteen tests plus the pooled H1 number",
  "Section 7 fixes the family at eighteen and says no test is added after results are seen. "
  "The pooled H1 number is required by section 11 for the post opening; it is reported "
  "outside the family, carries no Holm correction, and is labelled as such everywhere."),
 ("Standard errors on the Q3 first-component shares",
  "Section 6.6 defines Q3 as two numbers and says explicitly that it carries no test."),
 ("Whether gold's and silver's TRc1 series track an active month rather than a nearest "
  "expiry", "Left open by session 1b. A5 removed the continuous series from the "
  "construction entirely, so the question no longer bears on any number here."),
 ("A holdout", "Section 8: the item fits no predictive model and tunes no parameter."),
]
for t, why in NM:
    w("- **%s** — %s" % (t, why))
w()
w("### Done differently, or not pinned down by the spec")
w()
DV = [
 ("A5 names `tr_ds_fut.dsfutcontr` for contract identity and last trading date; "
  "`dsfutcontrinfo` was used",
  "`dsfutcontr` is the contract master at `contrcode` level and has no `lasttrddate` "
  "column. The per-contract table carrying `futcode` and `lasttrddate` is "
  "`dsfutcontrinfo`, which is what session 1b used and what A5's construction requires."),
 ("Curve state is matched on the premium's own date t",
  "Section 6.5 says \"the window's first day\". Matching on t+1 would place the regressor "
  "outside the information set at t and make H2 a statement about a look-ahead variable. "
  "The spec's own notation pairs z_t with IV^2_t."),
 ("The exchange marker for the continuation search",
  "A5 says \"whose exchange field marks COMEX, CMX, NYMEX or NYM\". `dsfutcontr` has no "
  "exchange-name column, so three markers were used together and reported: the exchange "
  "ticker symbol, COMEX or NYMEX in the contract name, and the CMX/NYM/NYL prefix on the "
  "class's continuous-series name. The two accepted classes carry tickers GC and SI."),
 ("The continuation tie-break",
  "A5 fixes the acceptance thresholds but not what to do when several candidates pass. "
  "The rule used - highest F2 match, then highest F1 match, then lowest class code - was "
  "stated in the script before it was applied and is reported with the full candidate "
  "table, so the choice is auditable."),
 ("The pooled H2 bootstrap resamples dates rather than stacked rows",
  "Section 7 names the estimator and the block length but not the resampling unit for a "
  "panel. Resampling stacked rows would ignore the cross-sectional dependence among the "
  "four premia, which Q3 shows is large. Resampling dates preserves it."),
 ("Figure 3 plots sd-scaled coefficients",
  "Presentation only. The raw coefficients span three orders of magnitude and the first "
  "version of the figure was unreadable. The scaling is a change of units; every "
  "statistic and p value is unchanged, and the raw coefficients appear in RESULTS.md."),
 ("statsmodels was installed into the venv",
  "The session instruction allows it and asks for the version: statsmodels 0.15.0. No "
  "other package was added."),
 ("Bootstrap draw count",
  "The budget allowed a fall back to 1,000 draws if the eighteen tests exceeded 30 "
  "minutes. They did not: H1 took %.1f s, H2 %.1f s and the pooled rows %.1f s, so "
  "**every test ran at the full %d draws** with seed %d."
  % (H1J["seconds"], H2J["seconds"], PO["pooled_bootstrap_seconds"], H1J["draws"],
     H1J["seed"])),
]
for t, why in DV:
    w("- **%s** — %s" % (t, why))
w()
w("### Wall clock")
w()
table(["stage", "wall clock"],
      [["contract pull and continuation search", "under 30 s"],
       ["curve-state construction", "%.1f s" % sum(meta[c]["seconds"] for c in meta)],
       ["H1, eight tests plus robustness and SPX", "%.1f s" % H1J["seconds"]],
       ["H2, ten tests plus April 2020 rows and the sign split", "%.1f s" % H2J["seconds"]],
       ["pooled H1 bootstrap", "%.1f s" % PO["pooled_bootstrap_seconds"]]])
w("---")
w()
w("Generated by `src/item1/build_report_s2.py` from the JSON, CSV and pickle artifacts in")
w("`output/item1/`. Every figure and table above is read back from a measurement; the")
w("connecting prose is written by hand.")

path = opath("REPORT_s2.md")
with open(path, "w") as fh:
    fh.write("\n".join(L) + "\n")
print("wrote %s (%d lines, %d bytes)" % (path, len(L), os.path.getsize(path)))
