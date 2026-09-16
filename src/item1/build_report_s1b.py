"""Assemble output/item1/REPORT_s1b.md from the measured artifacts."""
import os, sys, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import OUT_DIR, DATA_DIR, PROJECT_ROOT, opath, dpath, COMMON_START, COMMON_END
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
        cells = []
        for c in r:
            if c is None or (isinstance(c, float) and not np.isfinite(c)):
                cells.append("")
            else:
                cells.append(str(c))
        w("| " + " | ".join(cells) + " |")
    w()

def f4(x, nd=4):
    return "" if x is None or (isinstance(x, float) and not np.isfinite(x)) else ("%%.%df" % nd) % x

ROOT = PROJECT_ROOT
amend = subprocess.run(["git", "log", "--format=%H|%cI|%s", "-1",
                        "--", "SPEC_item1_commodity_vrp.md"],
                       capture_output=True, text=True, cwd=ROOT).stdout.strip()
sha, iso, subj = (amend.split("|") + ["", "", ""])[:3] if amend else ("", "", "")

w("# Item 1, session 1b — Datastream identity check, A1 rebuild, A3 diagnostics")
w()
w("Binding document: `SPEC_item1_commodity_vrp.md`, draft 3 plus amendments A1 to A4.")
w("This session corrects session 1's step 2, applies A1 to the construction, and runs the")
w("two A3 diagnostics. **It runs no hypothesis test.**")
w()
w("| | |")
w("|---|---|")
w("| Session | item 1, session 1b |")
w("| Report date | 2026-09-15 |")
w("| Amendment commit | `%s` |" % sha[:12])
w("| Amendment timestamp | %s |" % iso)
w("| Amendment message | %s |" % subj)
w("| Session 1 report | `output/item1/REPORT_s1.md` |")
w("| Interpreter | /Users/GualyCr/wrds-env/bin/python |")
w("| Code | `src/item1/` (committed) |")
w("| Data, outputs | `data/item1/`, `output/item1/` (not committed) |")
w()
w("**The three results that matter.**")
w()
w("1. Session 1's step-2 conclusion was **wrong for crude**. A2 is correct that the coded")
w("   `positionfwdcode` and `rollmethodcode` columns misread `XXXX.NN` mnemonics. Verified")
w("   against individual-contract data, `NCLC.01` and `NCLC.02` are a genuine first and")
w("   second nearby pair on NYMEX light sweet crude, matching their references on")
w("   **4,208 of 4,208** dates. Curve state is **retained for CL**, so the item does not")
w("   ship as the unconditional version and H2 is measurable for USO in session 2.")
w("2. A1 removes **every** spliced-chain duplicate: 950,508 duplicate rows across GLD, USO")
w("   and UNG go to zero, and **no date** falls back to the A4 open-interest collapse.")
w("   The clearest single case: UNG's 2011 30-day annual cell, which REPORT_s1 plotted as")
w("   a mean log ratio of 3.29 from three surviving days, was entirely spliced-chain")
w("   artefact. Under A1 no date in that cell survives at all, and the 91-day cell falls")
w("   from 1.93 to 0.37 with its maximum implied volatility down from 99 to 40 points.")
w("3. The A3(a) selection check **labels GLD, UNG and USO** as computed on a selected")
w("   subsample: their model-free drops are not independent of the premium level. SLV and")
w("   SPX are clean. For the three labelled ETFs the ATM secondary carries the headline H1")
w("   number in session 2.")
w()

# ------------------------------------------------------------------ step 0 ---
w("## Step 0 — amendments")
w()
w("Section 13 was appended to `SPEC_item1_commodity_vrp.md` verbatim and committed alone")
w("as `%s` at %s, before any query in this session ran." % (sha[:12], iso))
w()

# ------------------------------------------------------------------ step 1 ---
d1 = J("s1b_step1a_discover.json")
p1 = J("s1b_step1b_pull.json")
v1 = J("s1b_step1c_verify.json")
s1 = J("s1b_step1d_switches.json")
k1 = J("s1b_step1e_passrule.json")

w("## Step 1 — Datastream identity verification (A2)")
w()
w("### 1.1 Column lists, verbatim")
w()
for t in ["dsfutcontr", "dsfutcontrinfo", "dsfutcontrval", "wrds_fut_contract",
          "dsfutcalcserval"]:
    w("**`tr_ds_fut.%s`**" % t)
    w()
    table(["#", "column_name", "data_type", "is_nullable"],
          [[c["ordinal_position"], c["column_name"], c["data_type"], c["is_nullable"]]
           for c in d1["columns"]["tr_ds_fut." + t]])

w("### 1.2 Individual contracts per class")
w()
w("**`expirationdate` is null for every contract in all four classes.** The usable expiry")
w("column is `lasttrddate`, which is non-null on all but six contracts; `sttlmntdate`")
w("equals it on the large majority and is reported as the cross-check. Every reference")
w("series below is therefore built on `lasttrddate`.")
w()
rows = []
for code in ["GC", "SI", "CL", "NG"]:
    c = p1["contracts"][code]
    v = p1["values"][code]
    vv = s1["classes"][code]
    rows.append([code, vv["label"], int(c["clscode"]), c["n_contracts"],
                 c["nn_lasttrddate"], c["nn_expirationdate"], c["lasttrd_equals_sttlmnt"],
                 "%s .. %s" % (c["lasttrddate_min"], c["lasttrddate_max"]),
                 "{:,}".format(v["rows"]),
                 "%s .. %s" % (v["min_date"], v["max_date"]),
                 "%.1f s" % (c["seconds"] + v["seconds"])])
table(["class", "underlying for", "clscode", "contracts", "non-null lasttrddate",
       "non-null expirationdate", "lasttrddate == sttlmntdate",
       "lasttrddate span", "settlement rows 2008-06-01..2025-09-30",
       "value span", "pull"], rows)
w("**Gold and silver contract value data stops on 2022-12-28**, against crude and natural")
w("gas which run to the pull end. That alone caps what gold and silver can cover.")
w()

w("### 1.3 The continuous series, and their value-table coverage")
w()
rows = [[r["dsmnem"], int(r["calcseriescode"]), "{:,}".format(r["rows"]),
         r["min"] or "", r["max"] or "", "{:,}".format(r["nn_settlement"])]
        for r in d1["series"]["value_counts"]]
table(["dsmnem", "calcseriescode", "rows in dsfutcalcserval", "first", "last",
       "non-null settlement"], rows)
w("Requested but absent from `wrds_cseries_info`: `%s`."
  % "`, `".join(d1["series"]["missing"]))
w()
w("Two facts decide three of the four classes before any comparison is run:")
w()
w("- **`NNGC.02` has zero rows** in `dsfutcalcserval` and zero in `wrds_fut_series`. The")
w("  natural gas TRc2 slot exists in the catalogue and carries no data.")
w("- **`CZGC.01/.02` and `CZIC.01/.02` stop on 2013-12-17**, a quarter of the way into a")
w("  common window that ends 2025-08-29.")
w()

w("### 1.4 Reference series and the two conventions")
w()
w("On every SPX trade date in the common window (**%s** dates) two references are built"
  % "{:,}".format(v1["spx_trade_dates"]))
w("from the contract data:")
w()
w("- **convention X** — the nearest contract whose expiry is **on or after** the date, and")
w("  the second nearest on the same basis;")
w("- **convention Y** — the nearest contract whose expiry is **strictly after** the date,")
w("  and the second nearest on the same basis.")
w()
w("TRc1 is compared to the first-nearest reference and TRc2 to the second-nearest, under")
w("both conventions.")
w()
rows = []
for code in ["GC", "SI", "CL", "NG"]:
    for conv in ("X", "Y"):
        b = v1["classes"][code]["conventions"][conv]
        for lab in ("TRc1", "TRc2"):
            e = b.get(lab, {})
            if e.get("n", 0) == 0:
                rows.append([code, conv, lab, 0, "", "", "", e.get("note", "")])
                continue
            rows.append([code, conv, lab, "{:,}".format(e["n"]),
                         f4(e["share_exact"]), f4(e["share_within_0.5pct"]),
                         e["n_mismatch"], ""])
table(["class", "convention", "series", "dates compared", "share exact",
       "share within 0.5%", "mismatches beyond 0.5%", "note"], rows)
w("Mismatch dates beyond 0.5 percent are listed, up to 50 per cell, in")
w("`output/item1/s1b_step1c_verify.json`. Crude has **zero** mismatches under convention X")
w("on either leg and 112 and 118 under Y; natural gas TRc1 has zero under X and 173 under")
w("Y. The X-versus-Y difference is entirely the treatment of the expiry day itself.")
w()

w("### 1.5 Cross-position diagnostic: which rank does each series actually track")
w()
w("The share matching reference rank k within 0.5 percent, for k = 1 to 4. This is what")
w("separates a series that tracks a fixed nearby position from one that does not.")
w()
for code in ["GC", "SI", "CL", "NG"]:
    cr = s1["classes"][code]["cross_position"]
    rows = []
    for lab in ("TRc1", "TRc2"):
        for conv in ("X", "Y"):
            key = "%s|%s|rank1" % (conv, lab)
            if key not in cr:
                continue
            rows.append([lab, conv, "{:,}".format(cr[key]["n"])] +
                        [f4(cr["%s|%s|rank%d" % (conv, lab, k)]["share"]) for k in range(1, 5)])
    if not rows:
        continue
    w("**%s — %s**" % (code, s1["classes"][code]["label"]))
    w()
    table(["series", "convention", "n", "rank 1", "rank 2", "rank 3", "rank 4"], rows)
w("Crude is unambiguous: TRc1 matches rank 1 at 1.0000 and rank 2 at only 0.42, TRc2")
w("matches rank 2 at 1.0000 and rank 1 at 0.42. Natural gas TRc1 matches rank 1 at 1.0000.")
w("**Gold and silver TRc1 match no rank** — roughly 0.60 to 0.74 at every rank — so they")
w("are not tracking a nearest-by-last-trading-day position at all, while their TRc2 matches")
w("rank 2 at 1.0000. That asymmetry is what the pass rule is for.")
w()

w("### 1.6 Switches, the CS comparison, and TRc2 coverage")
w()
rows = []
for code in ["GC", "SI", "CL", "NG"]:
    r = s1["classes"][code]
    sw = r["switches"]; al = r["switch_alignment"]; cs = r["cs_comparison"]
    cov = r["trc2_coverage"]
    rows.append([code,
                 sw.get("TRc1", {}).get("n_switches", ""),
                 sw.get("TRc2", {}).get("n_switches", ""),
                 (al or {}).get("trc1_switches", ""),
                 (al or {}).get("trc2_switches_same_day", ""),
                 f4((al or {}).get("share")),
                 cs.get("cs_series") or "none exists",
                 f4(cs.get("share_exact")) if cs.get("share_exact") is not None else "",
                 cs.get("n_nonswitch_dates", ""),
                 "{:,}".format(cov["matched_spx_trade_dates"]),
                 f4(cov["coverage_share"])])
table(["class", "TRc1 switches", "TRc2 switches", "TRc1 switches on common dates",
       "TRc2 switches the same day", "share same day", "CS series",
       "TRc1 == CS exactly on non-switch dates", "non-switch dates",
       "TRc2 matched SPX dates", "TRc2 coverage share"], rows)
w("Crude's two legs roll together on 0.9853 of TRc1 switches. Gold manages 0.7692 and")
w("silver 0.5783 — their two legs are not rolling on the same schedule, which on its own")
w("disqualifies them as a first-and-second pair.")
w()
w("`NCLCS00` and `NCLCS01` do not exist, so crude has no CS-format series to compare")
w("against. For natural gas TRc1 equals `NNGCS01` exactly on only 0.1076 of non-switch")
w("dates but within 0.5 percent on **1.0000** of them — the two series carry the same")
w("contract at different rounding.")
w()

w("### 1.7 Pass rule and the re-run kill check")
w()
w("Pass rule, fixed by the session instruction before any number was seen: TRc1 and TRc2")
w("each match their reference under the **same** convention within 0.5 percent on at least")
w("%.0f percent of dates, and TRc2 switches on the same day as TRc1 on at least %.0f"
  % (k1["match_floor"] * 100, k1["switch_floor"] * 100))
w("percent of TRc1 switches. Nothing was tuned to reach it.")
w()
rows = [[r["commodity"], r["convention"] or "none clears", f4(r["trc1_match"]),
         f4(r["trc2_match"]), f4(r["switch_alignment"]),
         "**PASS**" if r["pass_rule"] else "FAIL", r["reasons"] or ""]
        for r in k1["pass_rule"]]
table(["class", "convention used", "TRc1 match", "TRc2 match", "switch alignment",
       "pass rule", "reason"], rows)
w("### Section 9 kill check, re-run")
w()
w("Common window trade dates **%s**; the 80 percent floor is **%.1f** dates."
  % ("{:,}".format(k1["spx_trade_dates"]), k1["coverage_floor"] * k1["spx_trade_dates"]))
w()
rows = [[r["commodity"], r["underlying_for"], "yes" if r["pair_verified"] else "no",
         r["convention"] or "", f4(r["coverage_share"]),
         "yes" if r["clears_80pct"] else "no",
         "**%s**" % r["outcome"], r["reason"] or ""]
        for r in k1["killcheck"]]
table(["class", "underlying for", "pair verified", "convention", "TRc2 coverage",
       "clears 80%", "outcome", "reason"], rows)
w("**Curve state is dropped for %d of 4 and retained for %d.** Section 9 sends the item to"
  % (k1["n_dropped"], 4 - k1["n_dropped"]))
w("the unconditional version only if all four are dropped, so that branch does not fire.")
w("H2 is measurable for **USO** at both nodes in session 2. Q3 as section 6.6 defines it")
w("residualises each of the four premia on its own z_t; three of the four have no z_t, so")
w("Q3 is not computable as written. Session 2 acts on that; this session only records it.")
w()
w("Verified and unverified series are both saved, marked: `data/item1/ds_cl_c1.parquet`")
w("and `ds_cl_c2.parquet` are the verified crude pair; the gold, silver and natural gas")
w("files carry `verified=False` in `output/item1/s1b_step1e_passrule.json`.")
w()

# ------------------------------------------------------------------ step 2 ---
rp = J("s1b_step2a_repull.json")
en = J("s1b_step2b_encoding.json")
dd = J("s1b_step2e_dupdiag.json")
b3 = J("s1b_build_mfiv.json")
b2 = J("s1b_build_mfiv_floor2.json")
cm = J("s1b_step2f_compare.json")
vx = J("s1_step4_vix_check.json")
vx1 = J("s1_step4_vix_check_SESSION1.json")
pr = J("s1_step5b_premium.json")
fg = J("s1_step6_fig1.json")

w("## Step 2 — rebuild under A1")
w()
w("### 2.1 Re-pull with the A1 columns")
w()
pulls = pd.DataFrame(rp["pulls"])
tot = pulls.groupby("ticker").agg(partitions=("year", "size"), rows=("rows", "sum"),
                                  secs=("pull_seconds", "sum"),
                                  bytes=("parquet_bytes", "sum")).reset_index()
table(["ticker", "partitions", "rows", "pull wall clock", "parquet"],
      [[r.ticker, r.partitions, "{:,}".format(int(r.rows)), "%.1f s" % r.secs,
        "%.1f MB" % (r.bytes / 1e6)] for r in tot.itertuples()])
w("**Total %.1f s (%.1f min), %s rows** — identical to session 1's row count, so adding"
  % (rp["total_seconds"], rp["total_seconds"] / 60.0, "{:,}".format(int(pulls.rows.sum()))))
w("`ss_flag`, `root`, `suffix` and `contract_size` changed nothing about what the pull")
w("selects. The session 1 parquet files are overwritten.")
w()

w("### 2.2 The ss_flag and contract_size encodings, read from the data")
w()
w("Read and reported **before** the filter encoding was chosen, as A1 requires.")
w()
a = pd.DataFrame(en["ss_flag"])
table(["ticker", "ss_flag", "rows", "share"],
      [[r.ticker, r.ss_flag, "{:,}".format(int(r.rows)), f4(r.share, 6)] for r in a.itertuples()])
w("`ss_flag` takes exactly two values, `'0'` and `'1'`. Contract size:")
w()
b = pd.DataFrame(en["contract_size"])
table(["ticker", "contract_size", "rows", "share"],
      [[r.ticker, "%g" % r.contract_size, "{:,}".format(int(r.rows)), f4(r.share, 6)]
       for r in b.itertuples()])
w("The joint distribution settles the encoding without ambiguity:")
w()
c = pd.DataFrame(en["joint"])
table(["ticker", "ss_flag", "contract_size", "rows", "share"],
      [[r.ticker, r.ss_flag, "%g" % r.contract_size, "{:,}".format(int(r.rows)), f4(r.share, 6)]
       for r in c.itertuples()])
w("**`ss_flag == '0'` and `contract_size == 100` are the same set of rows, exactly**, in")
w("all five secids: every `ss_flag == '0'` row has `contract_size == 100`, and every")
w("`ss_flag == '1'` row has a contract size of 10, 12, 25, 50 or -99. SPX and SLV are")
w("entirely standard; GLD is 5.79 percent non-standard, UNG 3.61 percent, USO 1.43 percent.")
w()
w("**Encoding used, recorded per A1: `ss_flag == '0'` and `contract_size == 100`.**")
w()

w("### 2.3 The section 3.7 duplicate diagnostic, re-run on filtered data")
w()
rows = [[r["ticker"], "{:,}".format(r["dates"]), "{:,}".format(r["rows_before"]),
         "{:,}".format(r["rows_after"]), f4(r["share_rows_kept"]),
         "{:,}".format(r["dup_dates_before"]), r["dup_dates_after"],
         "{:,}".format(r["dup_rows_before"]), r["dup_rows_after"]]
        for r in dd["rows"]]
table(["ticker", "dates", "rows before A1", "rows after A1", "share kept",
       "duplicate dates before", "duplicate dates after",
       "duplicate rows before", "duplicate rows after"], rows)
tot_dup = sum(r["dup_rows_before"] for r in dd["rows"])
w("**A1 removes every duplicate.** %s duplicate rows across GLD, USO and UNG go to zero,"
  % "{:,}".format(tot_dup))
w("and the number of secid-dates that fall back to the A4 open-interest collapse is **%d**."
  % b3["dupe_dates_surviving"])
w("The key here is the full expiry identity `(date, exdate, am_settlement, cp_flag,")
w("strike_price)`; SPX shows no duplicates on it because `am_settlement` separates its")
w("AM-settled and PM-settled chains, which is A4's adopted expiry identity.")
w()

w("### 2.4 Construction rerun, and retention before and after A1")
w()
w("Construction wall clock **%.1f s (%.1f min)** for %s records. Quote rows entering the"
  % (b3["seconds"], b3["seconds"] / 60.0, "{:,}".format(b3["records"])))
w("estimator fell from %s to %s, a kept share of %.4f."
  % ("{:,}".format(b3["rows_before_filter"]), "{:,}".format(b3["rows_after_filter"]),
     b3["rows_after_filter"] / b3["rows_before_filter"]))
w()
w("The session 1 output is retained as `data/item1/mfiv_nofilter.parquet`; the A1 output is")
w("`data/item1/mfiv.parquet` and is the primary series from here.")
w()
cmp = pd.DataFrame(cm["comparison"])
table(["ticker", "node", "dates", "surviving before A1", "share before",
       "surviving after A1", "share after", "change in share",
       "mean log ratio before", "mean log ratio after", "change in mean"],
      [[r.ticker, int(r.node), "{:,}".format(int(r.before_dates)),
        "{:,}".format(int(r.before_ok)), f4(r.before_share_ok),
        "{:,}".format(int(r.after_ok)), f4(r.after_share_ok), f4(r.delta_share_ok),
        f4(r.before_mean_lr), f4(r.after_mean_lr), f4(r.delta_mean_lr)]
       for r in cmp.itertuples()])
w("### 2.5 Drop codes and median strikes after A1")
w()
dc = pd.DataFrame(b3["drop_codes"])
piv = dc.pivot_table(index=["ticker", "node"], columns="drop_code", values="n",
                     fill_value=0, aggfunc="sum")
table(["ticker", "node"] + list(piv.columns),
      [[i[0], int(i[1])] + [int(v) for v in r] for i, r in zip(piv.index, piv.values)])
w("Median OTM strikes per side over each secid's whole span, after A1:")
w()
ms = pd.DataFrame(b3["median_strikes"])
table(["ticker", "node", "near expiry puts", "near expiry calls",
       "far expiry puts", "far expiry calls"],
      [[r.ticker, int(r.node), "%.0f" % r.n_strikes_low_put, "%.0f" % r.n_strikes_low_call,
        "%.0f" % r.n_strikes_high_put, "%.0f" % r.n_strikes_high_call]
       for r in ms.itertuples()])
w("Per-year medians are in `output/item1/s1b_median_strikes_mfiv.csv` and the by-year drop")
w("table in `output/item1/s1b_drops_mfiv.csv`.")
w()

w("### 2.6 VIX validation, re-run")
w()
table(["statistic", "session 1 (no filter)", "session 1b (A1)", "spec threshold"],
      [["correlation of levels", f4(vx1["correlation"], 6), "**%s**" % f4(vx["correlation"], 6),
        "at least %.2f" % vx["corr_floor"]],
       ["median absolute gap", "%s vol points" % f4(vx1["median_abs_diff"]),
        "**%s** vol points" % f4(vx["median_abs_diff"]), "at most %.1f" % vx["median_gap_ceiling"]],
       ["mean level difference", "%+.4f" % vx1["mean_diff"], "**%+.4f**" % vx["mean_diff"], "reported"],
       ["dates over 2 vol points", "%d of %s" % (vx1["n_gt_2_vol_points"], "{:,}".format(vx1["n_overlap"])),
        "%d of %s" % (vx["n_gt_2_vol_points"], "{:,}".format(vx["n_overlap"])), "reported"]])
dl = J("s1b_step2g_delta.json")
w("SPX carries no non-standard contracts at all (2.2), so A1 removes no SPX quote and the")
w("SPX validation is unchanged to every digit the spec reports. It is not bit-identical:")
w("the correlation moves by %.1e and the mean difference by %.1e, because the re-pull"
  % (abs(vx["correlation"] - vx1["correlation"]), abs(vx["mean_diff"] - vx1["mean_diff"])))
w("returns rows in a different order and one tie in the put-call parity strike selection")
w("breaks the other way. Exactly one SPX row of 8,688 moves, by 1.9e-06 in relative terms.")
w()
w("**What A1 moved, row by row.** This is the full accounting of the amendment's effect on")
w("the model-free series:")
w()
table(["ticker", "rows compared", "both non-null", "bit-identical",
       "moved by more than 1e-9 relative", "max absolute change", "max relative change",
       "drop code changed"],
      [[r["ticker"], "{:,}".format(r["common_rows"]), "{:,}".format(r["both_nonnull_mfiv"]),
        "{:,}".format(r["bit_identical"]), r["rel_diff_over_1e9"],
        "%.3e" % r["max_abs_diff"], "%.3e" % r["max_rel_diff"], r["drop_code_changed"]]
       for r in dl["rows"]])
w("**SLV is bit-identical throughout**, as its zero non-standard rows predict. SPX moves")
w("one row by floating-point noise. GLD, which REPORT_s1 3.7 called benign because its")
w("flagged dates carried ordinary volatilities, in fact has **391 rows** that move by more")
w("than a part in a billion, one by 27.8 percent. USO moves 108 values and 175 drop codes,")
w("UNG 222 values and 533 drop codes.")
w()
w("The stop rule does not fire.")
w()

w("### 2.7 Premium files and figure 1, rebuilt")
w()
w("`data/item1/premium_daily.parquet` (%s rows) and `data/item1/premium_grid.parquet`"
  % "{:,}".format(pr["daily_rows"]))
w("(%s rows) are rebuilt on the A1 series. Mean log(IV^2/RV) over the common window,"
  % "{:,}".format(pr["grid_rows"]))
w("descriptive only:")
w()
cw = pd.DataFrame(pr["mean_common_window"])
table(["ticker", "node", "n", "mean log ratio, model-free", "median",
       "mean log ratio, ATM", "mean IV2 - RV"],
      [[r.ticker, int(r.node), "{:,}".format(int(r.n_mf)), f4(r.mean_mf), f4(r.median_mf),
        f4(r.mean_atm), f4(r.mean_diff_mf)] for r in cw.itertuples()])
w("Figure 1 is regenerated in both versions:")
w("`output/item1/fig1_annual_logratio.png` and `.svg`,")
w("`output/item1/fig1_atm_annual_logratio.png` and `.svg`, table `fig1_table.csv`.")
w("The session 1 table is preserved as `fig1_table_SESSION1.csv`.")
w()
w("**Cells resting on fewer than 30 surviving days, after A1:**")
w()
thin = pd.DataFrame(cm["thin_cells_after"]) if cm["thin_cells_after"] else pd.DataFrame()
if len(thin):
    table(["ticker", "node", "year", "days", "mean log ratio"],
          [[r.ticker, int(r.node), int(r.year), int(r.n), f4(r.mean_lr)]
           for r in thin.itertuples()])
else:
    w("**None.** Every annual cell now rests on at least 30 surviving days.")
    w()

# ------------------------------------------------------------------ step 3 ---
a3a = J("s1b_step3a_selection.json")
a3b = J("s1b_step3b_floor2.json")

w("## Step 3 — registered diagnostics (A3)")
w()
w("Both are run before any test and are counted outside the eighteen-test family.")
w()
w("### 3.1 A3(a) — selection check on the 3-strike floor")
w()
w("Per secid and node on the common window: the mean ATM log ratio on dates where the")
w("A1-filtered model-free series is present, against dates where it is absent. If the")
w("model-free drops were unrelated to the level of the premium, the two means would agree.")
w()
rows = [[r["ticker"], int(r["node"]), "{:,}".format(r["n_retained"]), "{:,}".format(r["n_dropped"]),
         f4(r["mean_atm_retained"]), f4(r["mean_atm_dropped"]), f4(r["difference"]),
         f4(r["welch_t"], 3),
         ("%.3g" % r["welch_p"]) if r["welch_p"] is not None and np.isfinite(r["welch_p"]) else "",
         "yes" if r["exceeds_0.10"] else "no", "yes" if r["p_below_0.05"] else "no",
         "**LABELLED**" if r["labelled_selected"] else "clean"]
        for r in a3a["rows"]]
table(["ticker", "node", "n retained", "n dropped", "mean ATM log ratio, retained",
       "mean, dropped", "difference", "Welch t", "Welch p", "diff > 0.10", "p < 0.05",
       "A3(a) verdict"], rows)
w("A3's labelling rule: a difference above **%.2f** log units **or** a Welch p below"
  % a3a["diff_threshold"])
w("**%.2f** labels that ETF's model-free H1 result as computed on a selected subsample,"
  % a3a["p_threshold"])
w("and the ATM secondary carries its headline.")
w()
lab = a3a["labelled_tickers"]
if lab:
    w("**Labelled: %s.**" % ", ".join("`%s`" % x for x in lab))
    w("For these the ATM secondary carries the headline H1 number in session 2.")
else:
    w("**No ETF is labelled.** The model-free drops do not select on the premium level at")
    w("either node, so the model-free measure keeps the headline for every ETF.")
w()
w("Cells where no date is dropped have no comparison group; those show an empty p-value.")
w()

w("### 3.2 A3(b) — floor-of-2 robustness series")
w()
w("The construction rerun with the section 6.1 step-6 floor at 2 instead of 3, A1 in force")
w("throughout. Saved to `data/item1/mfiv_floor2.parquet`. This is the robustness row that")
w("sits next to every primary H1 number in session 2.")
w()
rows = []
for r in a3b["rows"]:
    rows.append([r["ticker"], int(r["node"]),
                 "{:,}".format(int(r["floor3_ok"])), f4(r["floor3_share_ok"]),
                 "{:,}".format(int(r["floor2_ok"])), f4(r["floor2_share_ok"]),
                 f4(r["delta_share_ok"]),
                 f4(r["floor3_mean_lr"]), f4(r["floor2_mean_lr"]), f4(r["delta_mean_lr"])])
table(["ticker", "node", "surviving, floor 3", "share", "surviving, floor 2", "share",
       "change in share", "mean log ratio, floor 3", "mean log ratio, floor 2",
       "change in mean"], rows)
w("Construction wall clock for the floor-2 run: %.1f s (%.1f min)."
  % (b2["seconds"], b2["seconds"] / 60.0))
w()

# ------------------------------------------------------- closing ---
w("## Not measured, and done differently")
w()
w("### Not measured")
w()
NM = [
 ("Every hypothesis test",
  "The session instruction is explicit that this session runs none, and A3 is counted "
  "outside the test family. All means reported here are descriptive and carry no standard "
  "error, no p-value for H1 and no Holm correction. The only p-values in this report are "
  "the A3(a) Welch p-values, which are a diagnostic, not a test of H1 or H2."),
 ("Curve state s_t and z_t themselves",
  "Step 1 verifies the crude pair and retains it. Building s_t and z_t from ds_cl_c1 and "
  "ds_cl_c2, winsorising z_t, and dropping 2020-04-20 are section 6.5 work that section 9 "
  "places in session 2."),
 ("Q3 under the new kill-check outcome",
  "Section 6.6 residualises each of the four premia on its own z_t. Only CL has a z_t, so "
  "Q3 as written is not computable. Whether to redefine it on one conditioned series and "
  "three unconditioned ones is a spec decision, not a session 1b measurement."),
 ("Why gold and silver TRc1 track no nearest-expiry rank",
  "Measured at 0.60 to 0.74 across ranks 1 to 4 and reported. The likely cause - Datastream "
  "tracking an active month rather than the nearest expiry for the metals - was not "
  "confirmed, because it would need volume or open-interest comparisons the pass rule does "
  "not call for."),
 ("Whether a different gold or silver series would pass",
  "Only the TRc1/TRc2 pair named in the session instruction was tested for each class. "
  "CZGC.03 to CZGC.12 and their silver equivalents were inventoried in step 1.3 but not put "
  "through the pass rule."),
 ("The April 2020 robustness row, the PCA, the non-overlapping inference rows",
  "All section 7 work, all in session 2."),
]
for t, why in NM:
    w("- **%s** — %s" % (t, why))
w()
w("### Done differently, or not pinned down")
w()
DV = [
 ("The expiry date used for the reference series is `lasttrddate`",
  "The session instruction says to use whichever date columns exist and report which. "
  "`expirationdate` is null on every contract in all four classes; `lasttrddate` is "
  "non-null on all but six and equals `sttlmntdate` on the large majority. Both facts are "
  "in 1.2."),
 ("The pass rule is evaluated on the dates where both the series and the reference exist",
  "The instruction fixes the thresholds but not the denominator. Coverage against the "
  "4,208-date common window is reported separately and is what the section 9 floor tests, "
  "so no class can pass on a short overlap alone."),
 ("A convention is reported as 'used' only when one convention clears the floor for both legs",
  "For gold and silver neither convention clears it for TRc1, so the convention column "
  "reads 'none clears' rather than naming the better of two failures."),
 ("Unverified series are saved too",
  "The instruction says to save each verified series. The gold, silver and natural gas "
  "files are written as well, each marked verified=False, so session 2 can see what was "
  "rejected without re-pulling."),
 ("`mfiv_one_date` gained a `min_strikes` parameter",
  "A3(b) needs the floor at 2. The estimator's logic is untouched; the floor was a module "
  "constant and is now a defaulted argument. The synthetic Black-Scholes self-test in "
  "`test_mfiv.py` still passes with zero failing checks."),
 ("scipy was installed into the venv",
  "A3(a) calls for a Welch p-value. scipy 1.18.1 was installed with pip, as matplotlib was "
  "in session 1. No other package was added."),
 ("Session 1 artefacts are preserved rather than overwritten",
  "`s1_step4_vix_check_SESSION1.json`, `s1_step5b_premium_SESSION1.json`, "
  "`s1_step6_fig1_SESSION1.json` and `fig1_table_SESSION1.csv` hold the pre-A1 values so "
  "the before-and-after tables in step 2 are read from measurements rather than from the "
  "session 1 prose."),
]
for t, why in DV:
    w("- **%s** — %s" % (t, why))
w()
w("### Corrections to REPORT_s1")
w()
w("- **Session 1 step 2 and step 7 are wrong for crude.** REPORT_s1 concluded that no")
w("  first-and-second nearby pair exists for any of the four commodities and that curve")
w("  state is dropped for all four (null D). Verified against individual-contract data,")
w("  `NCLC.01` and `NCLC.02` are a genuine pair on NYMEX light sweet crude. The cause is")
w("  the one A2 names: `wrds_cseries_info` parses the `XXXX.NN` Reuters continuation")
w("  mnemonics as CS-format codes, so it reports `NCLC.02` as position First with roll")
w("  method 2 when it is in fact the second nearby. Session 1's rule trusted those columns")
w("  and required a `2ND` name marker that the Reuters-style names never carry.")
w("- **Session 1 step 2 and step 7 stand for gold, silver and natural gas**, for reasons it")
w("  did not have: natural gas TRc2 carries no data at all, and the gold and silver TRc")
w("  series stop in 2013 and do not track a stable nearby rank.")
w("- **REPORT_s1 section 3.7's defect is fixed**, not merely measured. A1 removes every")
w("  spliced duplicate and the A4 fallback never fires.")
w()
w("### Wall clock")
w()
table(["stage", "wall clock"],
      [["contract and series pull, four classes", "under 8 s total, against a 20-minute per-class budget"],
       ["opprcd re-pull with the A1 columns, 92 partitions", "%.1f s (%.1f min)"
        % (rp["total_seconds"], rp["total_seconds"] / 60.0)],
       ["construction, A1, floor 3", "%.1f s (%.1f min)" % (b3["seconds"], b3["seconds"] / 60.0)],
       ["construction, A1, floor 2", "%.1f s (%.1f min)" % (b2["seconds"], b2["seconds"] / 60.0)]])
w("---")
w()
w("Generated by `src/item1/build_report_s1b.py` from the JSON and CSV artifacts in")
w("`output/item1/`. Every figure and table above is read back from a measurement; the")
w("connecting prose is written by hand.")

path = opath("REPORT_s1b.md")
with open(path, "w") as f:
    f.write("\n".join(L) + "\n")
print("wrote %s (%d lines, %d bytes)" % (path, len(L), os.path.getsize(path)))
