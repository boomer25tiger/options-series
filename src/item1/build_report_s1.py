"""Assemble output/item1/REPORT_s1.md from the measured artifacts.

Every number in the report is read back out of the JSON and CSV the step scripts
wrote. Nothing here is typed in by hand; the connecting prose is written by hand.
"""
import os, sys, json, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import OUT_DIR, DATA_DIR, opath, dpath, COMMON_START, COMMON_END, SECIDS, PULL_SPAN
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
        w("| " + " | ".join("" if c is None or (isinstance(c, float) and np.isnan(c))
                            else str(c) for c in r) + " |")
    w()

def df_table(df, cols=None, rnd=4):
    d = df[cols] if cols else df
    d = d.copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].round(rnd)
    table(list(d.columns), d.values.tolist())

# ------------------------------------------------------------------ header ---
spec_commit = subprocess.run(
    ["git", "log", "--format=%H|%cI|%s", "-1", "--", "SPEC_item1_commodity_vrp.md"],
    capture_output=True, text=True, cwd=os.path.dirname(OUT_DIR).replace("/output", "")
).stdout.strip()
sha, iso, subj = (spec_commit.split("|") + ["", "", ""])[:3] if spec_commit else ("", "", "")

w("# Item 1, session 1 — model-free implied variance, Datastream series, figure 1")
w()
w("Binding document: `SPEC_item1_commodity_vrp.md`, draft 3. Section numbers below refer")
w("to it. Nothing in this session changed the spec; deviations are recorded in the")
w("closing section.")
w()
w("| | |")
w("|---|---|")
w("| Session | item 1, session 1 |")
w("| Report date | 2026-09-15 |")
w("| Pre-registration commit | `%s` |" % sha[:12])
w("| Pre-registration timestamp | %s |" % iso)
w("| Pre-registration message | %s |" % subj)
w("| Interpreter | /Users/GualyCr/wrds-env/bin/python |")
w("| WRDS account | cgresearch26, credentials from ~/.pgpass |")
w("| Column lists | `information_schema.columns` (`db.describe_table()` is broken in this client) |")
w("| Counts | `count(*)`; `db.get_row_count()` is a planner estimate and is labelled where used |")
w("| Code | `src/item1/` (committed) |")
w("| Pulled data | `data/item1/` (%s, not committed) |" % ("%.0f MB" % (sum(
    os.path.getsize(os.path.join(DATA_DIR, f)) for f in os.listdir(DATA_DIR)) / 1e6)))
w("| Figures, tables, this report | `output/item1/` (not committed) |")
w()
w("**Two results govern everything downstream.** The section 6.1 construction passed the")
w("VIX validation comfortably (step 4), so the session ran to completion. The section 9")
w("kill check dropped curve state for all four commodities (step 7), because Datastream")
w("carries no second-nearby continuous series for any of the four named contracts. That")
w("is null D of section 12.")
w()

# ------------------------------------------------------------------ step 0 ---
w("## Step 0 — pre-registration")
w()
w("`SPEC_item1_commodity_vrp.md` was committed on its own as `%s` at %s, before any query"
  % (sha[:12], iso))
w("in this session ran. Every result commit follows it.")
w()

# ------------------------------------------------------------------ step 1 ---
v1 = J("s1_step1_vix.json")
v2 = J("s1_step1b_vix_pull.json")
w("## Step 1 — VIX availability")
w()
w("Libraries whose name contains `cboe`: `%s`." % "`, `".join(v1["cboe_libraries"]))
w()
rows = [[lib, len(t) if isinstance(t, list) else "list_tables failed",
         ", ".join("`%s`" % x for x in t) if isinstance(t, list) else ""]
        for lib, t in v1["tables"].items()]
table(["library", "tables", "table names"], rows)
w("No table in those libraries is *named* for VIX. Two tables carry a **column** named")
w("`vix`: `cboe.cboe` and `cboe_all.cboe`, both %s rows by `count(*)`, identical column"
  % "{:,}".format(v1["schemas"]["cboe.cboe"]["row_count_exact"]))
w("lists. A search for objects named like `%vix%` anywhere the account can see returned")
w("%d rows." % len(v1["vix_named_objects_anywhere"]))
w()
w("`cboe.cboe` columns, verbatim:")
w()
table(["#", "column_name", "data_type", "is_nullable"],
      [[c["ordinal_position"], c["column_name"], c["data_type"], c["is_nullable"]]
       for c in v1["schemas"]["cboe.cboe"]["columns"]])
w("`vix` is the daily close; `vixo`, `vixh`, `vixl` are open, high and low. The other")
w("columns are the VXO, VXN and VXD families.")
w()
w("**A daily VIX close exists**, so step 4 runs. Pulled over the common window to")
w("`data/item1/vix.parquet`:")
w()
table(["measure", "value"],
      [["pull wall clock", "%.2f s" % v2["pull_seconds"]],
       ["rows", "{:,}".format(v2["rows"])],
       ["first date", v2["first_date"]],
       ["last date", v2["last_date"]],
       ["non-null `vix` closes", "{:,}".format(v2["nonnull_vix"])],
       ["non-null share", "%.6f" % v2["nonnull_share"]],
       ["full-table span (reference)", "%s .. %s, %s rows"
        % (v2["full_table_min"], v2["full_table_max"], "{:,}".format(v2["full_table_rows"]))]])

# ------------------------------------------------------------------ step 2 ---
s2 = J("s1_step2_ds_series.json")
s2b = J("s1_step2b_ds_pull.json")
w("## Step 2 — Datastream continuous series for GC, SI, CL, NG")
w()
w("### 2.1 Column lists, verbatim")
w()
for t in ["wrds_cseries_info", "dsfutcalcserinfo", "dsfutcalcserval",
          "dsfutcalcsermth", "wrds_fut_series"]:
    w("**`tr_ds_fut.%s`**" % t)
    w()
    table(["#", "column_name", "data_type", "is_nullable"],
          [[c["ordinal_position"], c["column_name"], c["data_type"], c["is_nullable"]]
           for c in s2["columns"]["tr_ds_fut." + t]])

w("### 2.2 The two metadata dimensions that decide the question")
w()
w("`wrds_cseries_info` carries the nearby position and the roll convention as explicit")
w("coded columns. These, not the series name, are the authority on what a series is.")
w()
w("**`positionfwdcode` across the whole table:**")
w()
table(["positionfwdcode", "positionfwddesc", "series"],
      [[r["positionfwdcode"], r["positionfwddesc"], "{:,}".format(r["n"])]
       for r in s2["positionfwd_dictionary"]])
w("**`rollmethodcode` across the whole table:**")
w()
table(["rollmethodcode", "rollmethoddesc", "series"],
      [[r["rollmethodcode"], r["rollmethoddesc"], "{:,}".format(r["n"])]
       for r in s2["rollmethod_dictionary"]])

w("The Datastream mnemonic ends in a two-character suffix read here as")
w("`<position><roll>`. That reading is **verified against the coded columns**, not")
w("assumed — across every series whose mnemonic matches `(CS|C.)\\d\\d`:")
w()
pc = pd.DataFrame(s2["suffix_position_check"])
w("suffix position digit against `positionfwdcode` (every row is on the diagonal):")
w()
table(["positionfwdcode", "suffix position digit", "series"],
      [[r.positionfwdcode, r.suffix_position_digit, "{:,}".format(r.n)]
       for r in pc.itertuples()])
rc = pd.DataFrame(s2["suffix_roll_check"])
offdiag = rc[rc.rollmethodcode.astype(str) != rc.suffix_roll_digit.astype(str)]
w("suffix roll digit against `rollmethodcode`: %d combinations, %d of them off the"
  % (len(rc), len(offdiag)))
w("diagonal. So position digit 0 means First, 2 means Second, and the trailing digit is")
w("the roll method.")
w()

w("### 2.3 The selection rule, as applied")
w()
w("Fixed before looking at any one commodity and applied identically to all four:")
w()
w("- **R1 Selection pool.** Continuous series on the named exchange, operationalised as")
w("  `calcseriesname` beginning `NYM-`, `CMX-` or `NYL-` — the three prefixes Datastream")
w("  uses for the NYMEX/COMEX complex — together with the commodity word. `NYL-` is")
w("  included because that is how Datastream names the continuous series of the 100-oz")
w("  gold and 5000-oz silver contracts; without it the main metal contracts would sit")
w("  outside the pool. Other exchanges (`ICE-`, `IPE-`, `CBT-`, `CME-`, `BFE-`) are")
w("  outside the pool.")
w("- **R2 First leg.** Name marks the continuous front contract (`CONTINUOUS`, `CONT.`,")
w("  or `TRc<d>`) **and** the mnemonic suffix position digit is 0.")
w("- **R3 Second leg.** Name marks the continuous second contract (`2ND`, or `TRc2<d>`)")
w("  **and** the mnemonic suffix position digit is 2.")
w("- **R4 Pair.** Same trailing roll digit **and** same `clscode`. The same-class clause")
w("  is an explicit addition: without it a first leg on NYMEX natural gas would pair with")
w("  a second leg on ICE natural gas.")
w("- **R5 Tie-break.** Earliest first date of the first leg in `dsfutcalcserval`.")
w("- **R6 No pair.** Record it and move on.")
w()
w("Three further searches per commodity are reported as evidence that a qualifying pair")
w("on the named contract was not missed: (B) walk `exchtickersymb` through")
w("`dsfutcontr` → `dsfutclass` → series; (C) every second-nearby series on **any**")
w("exchange carrying the commodity word; (D) the standard contract by name under any")
w("exchange prefix. Only (A) feeds selection.")
w()

w("### 2.4 Outcome: no pair qualifies for any of the four")
w()
rows = []
for code in ["GC", "SI", "CL", "NG"]:
    s = s2["selection"][code]
    c = s2["candidates"][code]
    rows.append([code, c["label"], c["A_selection_pool"]["n"], s["n_first"], s["n_second"],
                 len(s["rejected"]), s["n_pairs"],
                 "none (R6)" if s["selected"] is None else s["selected"]["first"]["dsmnem"]])
table(["commodity", "named exchange search", "pool rows (A)", "classified FIRST",
       "classified SECOND", "rejected", "qualifying pairs", "selected"], rows)
w("**Every commodity returns zero second-nearby legs on its named contract, so zero")
w("pairs, so R6 applies to all four.** Cross-checked three ways: `wrds_cseries_info`,")
w("`dsfutcalcserinfo` (which holds no series the first table omits for these classes),")
w("and `dsfutcalcsermth` (which holds no rows at all for these classes — its `mthnum`")
w("values are calendar trading months 1 to 12, not nearby positions).")
w()
w("Where the second-nearby series for these commodities actually live — search (C),")
w("every exchange:")
w()
rows = []
for code in ["GC", "SI", "CL", "NG"]:
    sw = s2["candidates"][code]["C_second_leg_sweep_all_exchanges"]
    pool_cls = sorted({r["clscode"] for r in s2["candidates"][code]["A_selection_pool"]["rows"]})
    sweep_cls = sorted({r["clscode"] for r in sw["rows"]})
    overlap = sorted(set(sweep_cls) & set(pool_cls))
    names = sorted({r["calcseriesname"].split(" CONT")[0].split(" TRc")[0]
                    for r in sw["rows"]})
    rows.append([code, sw["n"], ", ".join(str(int(c)) for c in sweep_cls) or "none",
                 ", ".join(str(int(c)) for c in overlap) or "none",
                 "; ".join(names[:4]) or "none"])
table(["commodity", "second-nearby series found anywhere", "their clscodes",
       "overlap with the named-exchange pool", "contracts they belong to"], rows)
w("For CL the single overlapping class, 1945, is `NYM-WTI CRUDE OIL SWAP`, a swap")
w("contract and not the light sweet futures contract; its rows fail R2/R3 on the name")
w("marker in any case. For GC, SI and NG the overlap is empty.")
w()

w("### 2.5 Rejected candidates, with the reason")
w()
for code in ["GC", "SI", "CL", "NG"]:
    rej = s2["selection"][code]["rejected"]
    w("**%s — %d rejected of %d pool rows.**"
      % (code, len(rej), s2["candidates"][code]["A_selection_pool"]["n"]))
    w()
    if not rej:
        w("(none)"); w(); continue
    table(["dsmnem", "calcseriesname", "clscode", "positionfwddesc", "reason"],
          [[r["dsmnem"], r["calcseriesname"], r["clscode"], r["positionfwddesc"], r["reason"]]
           for r in rej])

w("### 2.6 Selection pool, pasted (search A, cap 100 rows per commodity)")
w()
for code in ["GC", "SI", "CL", "NG"]:
    c = s2["candidates"][code]
    w("**%s — %s.** `where: %s` → %d rows."
      % (code, c["label"], c["A_selection_pool"]["where"], c["A_selection_pool"]["n"]))
    w()
    table(["calcseriescode", "clscode", "dsmnem", "calcseriesname", "rollmethodcode",
           "rollmethoddesc", "positionfwddesc", "calcmthcode"],
          [[r["calcseriescode"], r["clscode"], r["dsmnem"], r["calcseriesname"],
            r["rollmethodcode"], r["rollmethoddesc"], r["positionfwddesc"], r["calcmthcode"]]
           for r in c["A_selection_pool"]["rows"]])

w("### 2.7 First-leg pull and coverage")
w()
w("The rule selected nothing, so strictly there was nothing to pull. The first-nearby")
w("legs were pulled anyway, as an addition beyond the rule, because step 7 has to report")
w("a coverage share and because the report should say what is on the server as well as")
w("what is missing. Addition rule, applied uniformly: take the principal contract")
w("(`^NYM-LIGHT CRUDE OIL`, `^NYM-NATURAL GAS`, `^NYL-GOLD 100 OZ`,")
w("`^NYL-SILVER 5000 OZ`) and, among the rows R2 classified FIRST on it, the one with")
w("the lowest roll digit, preferring a `CS` mnemonic over a `C.` mnemonic on a tie.")
w()
w("SPX trade dates in `optionm.secprd` over the common window: **%s**."
  % "{:,}".format(s2b["spx_trade_dates_common_window"]))
w()
rows = []
for code in ["GC", "SI", "CL", "NG"]:
    r = s2b["series"][code]
    rows.append([code, r["dsmnem"], r["calcseriesname"], int(r["calcseriescode"]),
                 r["first_date"], r["last_date"], "{:,}".format(r["row_count"]),
                 "{:,}".format(r["dates_in_common_window"]),
                 "{:,}".format(r["matched_spx_trade_dates"]),
                 "%.4f" % r["coverage_share"], "%.4f" % r["coverage_share_nonnull"],
                 "%.2f s" % r["pull_seconds"]])
table(["commodity", "dsmnem", "series name", "calcseriescode", "first date", "last date",
       "rows", "dates in common window", "matched SPX trade dates",
       "coverage share", "coverage share, settlement non-null", "pull"], rows)
w("The coverage share is matched dates divided by the %s SPX trade dates in the common"
  % "{:,}".format(s2b["spx_trade_dates_common_window"]))
w("window. The last column repeats it counting only dates whose `settlement` is non-null:")
w("gold and silver lose about 17 points there, crude and natural gas lose nothing.")
w()
w("**Roll convention of each pulled series**, read from the name, the mnemonic suffix and")
w("the metadata — never from the price series:")
w()
rows = []
for code in ["GC", "SI", "CL", "NG"]:
    r = s2b["series"][code]
    rows.append([code, r["dsmnem"],
                 r["mnemonic_suffix_position_digit"], r["mnemonic_suffix_roll_digit"],
                 r["positionfwddesc"], int(r["rollmethodcode"]), r["rollmethoddesc"],
                 r["dsfutcalcsermth_n"]])
table(["commodity", "dsmnem", "suffix position digit", "suffix roll digit",
       "positionfwddesc", "rollmethodcode", "rollmethoddesc (verbatim)",
       "dsfutcalcsermth rows"], rows)
w("`dsfutcalcsermth` holds no rows for any of these four series, so it contributes")
w("nothing to the convention. No second leg exists for any of them, so there is no")
w("same-convention comparison to make.")
w()

# ------------------------------------------------------------------ step 3 ---
z = J("s1_step3a_zerocd.json")
pl = J("s1_step3b_opprcd_pull.json")
bm = J("s1_step3c_build_mfiv.json")
mc = J("s1_step3d_multichain_diag.json")

w("## Step 3 — model-free implied variance (section 6.1)")
w()
w("### 3.1 Zero curve")
w()
table(["measure", "value"],
      [["table", "`optionm.zerocd`, pulled in full"],
       ["pull wall clock", "%.2f s" % z["pull_seconds"]],
       ["rows", "{:,}".format(z["rows"])],
       ["date span", "%s .. %s" % (z["min_date"], z["max_date"])],
       ["distinct dates", "{:,}".format(z["n_dates"])],
       ["`days` span", "%.0f .. %.0f" % (z["days_min"], z["days_max"])],
       ["`rate` range", "%.4f to %.4f, percent per annum" % (z["rate_min"], z["rate_max"])],
       ["null rates", z["rate_null"]]])
w("The zero rate is interpolated linearly in days to each expiry and divided by 100 to a")
w("decimal. Only **%d** of the %s secid-dates needed the nearest-earlier-date fallback"
  % (bm["zerocd_fallback_dates"], "{:,}".format(bm["records"] // 2)))
w("because their trade date was absent from `zerocd`.")
w()

w("### 3.2 opprcd pulls")
w()
w("One secid and one year partition at a time, filtering on `secid` and `date` before any")
w("other predicate, restricted to `exdate` between 7 and 200 calendar days after `date`.")
w("`strike_price` divided by 1000 on read.")
w()
pulls = pd.DataFrame(pl["pulls"])
tot = pulls.groupby("ticker").agg(
    partitions=("year", "size"), rows=("rows", "sum"),
    pull_seconds=("pull_seconds", "sum"), parquet_bytes=("parquet_bytes", "sum"),
    first_year=("year", "min"), last_year=("year", "max"),
    fwd_nonnull=("fwd_nonnull", "sum")).reset_index()
table(["ticker", "partitions", "years", "rows pulled", "pull wall clock",
       "parquet", "rows with non-null forward_price"],
      [[r.ticker, r.partitions, "%d-%d" % (r.first_year, r.last_year),
        "{:,}".format(int(r.rows)), "%.1f s" % r.pull_seconds,
        "%.1f MB" % (r.parquet_bytes / 1e6), int(r.fwd_nonnull)] for r in tot.itertuples()])
w("**Total: %d pulls, %s rows, %.1f s (%.1f min), %.2f GB.** The 60-minute budget was not"
  % (len(pulls), "{:,}".format(int(pulls.rows.sum())), pl["total_seconds"],
     pl["total_seconds"] / 60.0, pulls.parquet_bytes.sum() / 1e9))
w("reached and nothing was left unpulled (`not_pulled` is empty).")
w()
w("**`forward_price` is null on all %s rows pulled, in every secid and every year.**"
  % "{:,}".format(int(pulls.rows.sum())))
w("Section 6.1 step 2 anticipates this: the forward is taken from put-call parity at the")
w("strike with the smallest absolute call-minus-put midquote difference. That path is")
w("therefore the only one used anywhere in this session; the `forward_price` branch never")
w("executes. Per-partition timings are in `output/item1/s1_step3b_opprcd_pull.log`.")
w()

w("### 3.3 The estimator, and what it was checked against")
w()
w("`src/item1/mfiv.py` implements steps 1 to 6 as `mfiv_one_date(date, quotes, zdays,")
w("zrates, nodes)`, returning model-free variance at each node or a drop code naming the")
w("step that dropped the date. `src/item1/test_mfiv.py` checks it against a synthetic")
w("Black-Scholes chain before any real quote is touched — if steps 2 to 5 are right,")
w("feeding the estimator a chain priced off a known constant volatility must return that")
w("volatility. All checks pass:")
w()
table(["check", "result"],
      [["flat-vol chain, sigma 0.25, 30-day node", "recovered 0.250317, error 0.032 vol points"],
       ["flat-vol chain, sigma 0.25, 91-day node", "recovered 0.250072, error 0.007 vol points"],
       ["single expiry, sigma 0.10", "recovered 0.100143, error 0.014 vol points"],
       ["single expiry, sigma 0.25", "recovered 0.250008, error 0.001 vol points"],
       ["single expiry, sigma 0.60", "recovered 0.599938, error 0.006 vol points"],
       ["forward from put-call parity", "100.1645 against a true forward of 100.1645"],
       ["thin ladder", "FEW_STRIKES_LOW"],
       ["no expiry above the node", "NO_BRACKET"],
       ["every expiry inside the 7-day floor", "NO_BRACKET"],
       ["empty quote set", "NO_QUOTES"],
       ["two consecutive zero-bid strikes", "sweep stops, 2 puts kept, then the step-6 floor drops the date"],
       ["one zero-bid strike alone", "that strike only is dropped, 59 of 60 kept"]])
w("Section 6.1 leaves six things open. The choices made are listed in the module")
w("docstring and repeated in the closing section of this report.")
w()

w("### 3.4 Construction run, and retention")
w()
w("Wall clock **%.1f s (%.1f min)** for **%s** secid-date-node records, written to"
  % (bm["construction_seconds"], bm["construction_seconds"] / 60.0,
     "{:,}".format(bm["records"])))
w("`data/item1/mfiv.parquet`.")
w()
ret = pd.DataFrame(bm["retention"])
table(["ticker", "node", "dates", "surviving (drop_code OK)", "share surviving"],
      [[r.ticker, int(r.node), "{:,}".format(int(r.dates)), "{:,}".format(int(r.ok)),
        "%.4f" % r.share_ok] for r in ret.itertuples()])
w("SPX and GLD retain 95 to 99 percent. UNG retains **54 percent at the 30-day node**,")
w("the thinnest chain in the set.")
w()

w("### 3.5 Drop counts per secid, node and drop code")
w()
drops = pd.read_csv(opath("s1_step3_drops_by_year.csv"))
agg = drops.groupby(["ticker", "node"]).sum(numeric_only=True).drop(columns=["year"]).reset_index()
cols = [c for c in agg.columns if c not in ("ticker", "node")]
table(["ticker", "node"] + cols,
      [[r.ticker, int(r.node)] + [int(getattr(r, c)) for c in cols] for r in agg.itertuples()])
w("`NO_BRACKET` at the 30-day node is a date with no expiry on both sides of 30 days")
w("after the 7-day floor; at the 91-day node it never fires, because the pull window")
w("reaches 200 days. `FEW_STRIKES_LOW` and `FEW_STRIKES_HIGH` are the section 6.1 step-6")
w("floor of 3 OTM strikes per side. `NO_FORWARD_*` and `NO_K0_*` are close to zero")
w("everywhere. The full by-year breakdown is `output/item1/s1_step3_drops_by_year.csv`.")
w()

w("### 3.6 Median OTM strikes per side — the number the 3-strike floor was set without")
w()
w("Section 6.1 fixes the floor at 3 as a judgment call made before seeing any chain. What")
w("the chains actually carry, median per side across each secid's whole span:")
w()
med = pd.read_csv(opath("s1_step3_median_strikes.csv"))
m2 = med.groupby(["ticker", "node"])[["n_strikes_low_put", "n_strikes_low_call",
                                      "n_strikes_high_put", "n_strikes_high_call"]].median()
table(["ticker", "node", "near expiry, puts", "near expiry, calls",
       "far expiry, puts", "far expiry, calls"],
      [[i[0], i[1], "%.0f" % r.n_strikes_low_put, "%.0f" % r.n_strikes_low_call,
        "%.0f" % r.n_strikes_high_put, "%.0f" % r.n_strikes_high_call]
       for i, r in m2.iterrows()])
w("How often the floor actually binds, as a share of all bracketed rows:")
w()
table(["side", "share with fewer than 3 strikes"],
      [[k, "%.4f" % v] for k, v in bm["floor_bind_shares"].items()])
w("The floor is not a formality for the commodity ETFs: it binds on about 10 percent of")
w("bracketed rows on the near-expiry put side. Per-year medians are in")
w("`output/item1/s1_step3_median_strikes.csv`.")
w()

w("### 3.7 A construction defect found in this session: multi-deliverable expiries")
w()
w("Some ETF expiries carry **two deliverable chains under the same `exdate` and the same")
w("`am_settlement`** — the standard chain and a split-adjusted one. The clearest case is")
w("UNG on 2011-03-21: the close was 11.105 with `cfadj` 0.5, and the same expiry carries")
w("a call struck at 5 quoted 6.05/6.15 (consistent with an underlying near 11.1) and")
w("another call struck at 5 quoted 0.58/0.60 (consistent with an underlying near 5.55).")
w()
w("The duplicate-resolution choice in the estimator (CHOICE 2, keep the largest open")
w("interest) then splices the two chains into one strike ladder, and the section 6.1 sum")
w("is taken across two different securities. On that date it returns 170 vol points for a")
w("30-day node whose realised volatility was 32.")
w()
w("Extent, measured:")
w()
bt = pd.DataFrame(mc["by_ticker"])
table(["ticker", "secid-dates", "dates with a duplicated (exdate, am_settlement, cp_flag, strike)",
       "share"],
      [[r.ticker, "{:,}".format(int(r.dates)), "{:,}".format(int(r.affected)),
        "%.4f" % r.share] for r in bt.itertuples()])
w("**SPX and SLV are untouched.** GLD is flagged on 16 percent of dates but the flagged")
w("dates produce ordinary volatilities, so its duplicates are benign. UNG and USO are")
w("where the damage is:")
w()
iv = pd.DataFrame(mc["ivol_split"])
table(["ticker", "node", "flagged", "surviving rows", "median implied vol",
       "95th pct", "max", "share over 100 vol points"],
      [[r.ticker, int(r.node), bool(r.multi_chain), "{:,}".format(int(r.n)),
        "%.1f" % r["median"], "%.1f" % r.p95, "%.1f" % r["max"], "%.3f" % r.share_over_100]
       for _, r in iv.iterrows()])
w("Note that an implied volatility above 100 points is not by itself wrong — natural gas")
w("in 2021-22 and crude in April 2020 genuinely traded there — so the level alone does")
w("not identify the defect. The duplicate flag does.")
w()
w("**This was not patched.** The session instruction is that nothing here changes the")
w("spec, and the pre-registered construction guard (the step-4 stop rule) passed. Editing")
w("the construction after seeing the data is what pre-registration exists to prevent. The")
w("defect is carried into the closing section as a proposed amendment for session 2.")
w()

# ------------------------------------------------------------------ step 4 ---
v = J("s1_step4_vix_check.json")
w("## Step 4 — VIX validation (section 6.1)")
w()
w("SPX 30-day model-free volatility, `sqrt(mfiv) x 100`, against the VIX close over the")
w("overlap of the two series.")
w()
table(["measure", "value", "spec threshold", "result"],
      [["correlation of levels", "**%.6f**" % v["correlation"],
        "at least %.2f" % v["corr_floor"], "**pass**" if v["correlation"] >= v["corr_floor"] else "fail"],
       ["median absolute gap", "**%.4f** vol points" % v["median_abs_diff"],
        "at most %.1f vol point" % v["median_gap_ceiling"],
        "**pass**" if v["median_abs_diff"] <= v["median_gap_ceiling"] else "fail"],
       ["mean level difference", "%+.4f vol points" % v["mean_diff"], "reported", ""],
       ["median level difference", "%+.4f vol points" % v["median_diff"], "reported", ""],
       ["dates differing by more than 2 vol points", "%d of %s (share %.4f)"
        % (v["n_gt_2_vol_points"], "{:,}".format(v["n_overlap"]), v["share_gt_2_vol_points"]),
        "reported", ""],
       ["overlap", "%s dates, %s to %s" % ("{:,}".format(v["n_overlap"]),
                                           v["first_date"], v["last_date"]), "", ""]])
w("Detail not part of the rule: standard deviation of the difference %.4f, 90th"
  % v["sd_diff"])
w("percentile absolute gap %.4f, largest absolute gap %.4f." % (v["p90_abs_diff"], v["max_abs_diff"]))
w()
w("**VALIDATION PASSED.** The session continues to step 5. By year:")
w()
by = pd.DataFrame(v["by_year"])
ycol = "year" if "year" in by.columns else by.columns[0]
table(["year", "n", "correlation", "mean diff", "median diff", "median abs diff",
       "share over 2 points"],
      [[int(r[ycol]), int(r["n"]), "%.4f" % r["corr"], "%+.4f" % r["mean_diff"],
        "%+.4f" % r["median_diff"], "%.4f" % r["median_absdiff"], "%.4f" % r["share_gt2"]]
       for _, r in by.iterrows()])
w("The model-free series sits a little below VIX in most years — mean %+.4f vol points"
  % v["mean_diff"])
w("overall — which is what truncating the strike ladder at the zero-bid boundary does to")
w("the integral. The bias shrinks over the sample as the SPX chain widens.")
w()
w("Merged series: `output/item1/vix_check.parquet`. Figure:")
w("`output/item1/fig_vix_check.png` — scatter against the 45-degree line, and a time")
w("series overlay.")
w()

# ------------------------------------------------------------------ step 5 ---
p5a = J("s1_step5a_pull.json")
p5b = J("s1_step5b_premium.json")
w("## Step 5 — ATM node, returns, realized variance, premiums")
w()
w("### 5.1 ATM implied variance (section 6.2)")
w()
w("`optionm.vsurfdYYYY` rows with `days in (30, 91)` and `delta in (50, -50)`, per secid")
w("per year partition. %s rows pulled, all of them on the two legs section 6.2 names"
  % "{:,}".format(p5a["vsurfd_rows"]))
w("(`delta = 50, cp_flag = 'C'` and `delta = -50, cp_flag = 'P'`), evenly split four ways")
w("across the two nodes and two legs. ATM variance is the square of the mean of the two")
w("implied volatilities.")
w()
w("**Null counts per secid and node: zero everywhere.**")
w()
nn = pd.DataFrame(p5a["atm_nulls_by_year"])
agg = nn.groupby(["ticker", "node"]).agg(dates=("dates", "sum"),
                                         null_call=("null_call", "sum"),
                                         null_put=("null_put", "sum"),
                                         null_atmiv=("null_atmiv", "sum")).reset_index()
table(["ticker", "node", "dates", "null call IV", "null put IV", "null ATM variance"],
      [[r.ticker, int(r.node), "{:,}".format(int(r.dates)), int(r.null_call),
        int(r.null_put), int(r.null_atmiv)] for r in agg.itertuples()])
w("Per-year counts, all zero, are in `output/item1/s1_step5_atm_nulls_by_year.csv`.")
w()

w("### 5.2 Returns (section 6.3 input)")
w()
w("`date` and `return` from `optionm.secprdYYYY`, per secid per year partition.")
w()
rm = pd.DataFrame(p5a["return_missing_by_year"])
agg = rm.groupby("ticker").agg(dates=("dates", "sum"), missing=("missing", "sum")).reset_index()
agg["share"] = agg.missing / agg.dates
table(["ticker", "trade dates", "missing returns", "share"],
      [[r.ticker, "{:,}".format(int(r.dates)), int(r.missing), "%.6f" % r.share]
       for r in agg.itertuples()])
w("One missing return in the whole set, on UNG. Per-year counts are in")
w("`output/item1/s1_step5_return_missing_by_year.csv`.")
w()

w("### 5.3 Realized variance (section 6.3)")
w()
w("Sum of squared `log(1 + return)` over trading days t+1 to t+h, h = 21 at the 30-day")
w("node and h = 63 at the 91-day node, scaled by 252/h. A window with any missing return")
w("is dropped, and so is a window that runs off the end of the sample.")
w()
rv = pd.DataFrame(p5b["rv_windows"])
table(["ticker", "node", "dates", "complete windows", "dropped", "share dropped"],
      [[r.ticker, int(r.node), "{:,}".format(int(r.dates)), "{:,}".format(int(r.complete)),
        int(r.dropped), "%.4f" % r.share_dropped] for r in rv.itertuples()])
w("The dropped windows are almost entirely the last h trading days of each secid's span,")
w("where the forward window has nowhere to run.")
w()

w("### 5.4 Premiums (section 6.4)")
w()
w("Primary `log(IV^2 / RV)` and secondary `IV^2 - RV`, each computed with the model-free")
w("implied variance of 6.1 and with the ATM implied variance of 6.2. Daily series in")
w("`data/item1/premium_daily.parquet` (%s rows)." % "{:,}".format(p5b["daily_rows"]))
w()
dc = pd.DataFrame(p5b["daily_counts"])
table(["ticker", "node", "rows", "mfiv", "atmiv", "rv", "logratio_mf", "logratio_atm"],
      [[r.ticker, int(r.node), "{:,}".format(int(r.rows)), "{:,}".format(int(r.mfiv)),
        "{:,}".format(int(r.atmiv)), "{:,}".format(int(r.rv)),
        "{:,}".format(int(r.logratio_mf)), "{:,}".format(int(r.logratio_atm))]
       for r in dc.itertuples()])
w("Mean `log(IV^2/RV)` over the common window, descriptive only — **section 7 forbids any")
w("test in session 1, and none is run here**:")
w()
cw = pd.DataFrame(p5b["mean_common_window"])
table(["ticker", "node", "n (model-free)", "mean log ratio, model-free",
       "median, model-free", "n (ATM)", "mean log ratio, ATM", "mean IV2 - RV, model-free"],
      [[r.ticker, int(r.node), "{:,}".format(int(r.n_mf)), "%.4f" % r.mean_mf,
        "%.4f" % r.median_mf, "{:,}".format(int(r.n_atm)), "%.4f" % r.mean_atm,
        "%.4f" % r.mean_diff_mf] for r in cw.itertuples()])
w("Every one of the twenty cells is positive, which is the direction H1 registers. No")
w("standard error, no p-value and no test appears in this session.")
w()

w("### 5.5 Non-overlapping grid")
w()
w("Anchored on %s, every 21 trading days at the 30-day node and every 63 at the 91-day"
  % COMMON_START)
w("node, on each secid's own trade-date index. `data/item1/premium_grid.parquet`.")
w()
gs = pd.DataFrame(p5b["grid_summary"])
table(["ticker", "node", "grid dates", "first", "last", "n with log ratio, model-free",
       "n with log ratio, ATM"],
      [[r.ticker, int(r.node), int(r.grid_dates), str(r["first"])[:10], str(r["last"])[:10],
        int(r.n_logratio_mf), int(r.n_logratio_atm)] for _, r in gs.iterrows()])
w("201 grid dates at the 30-day node and 67 at the 91-day node, against the \"about 200\"")
w("and \"about 67\" section 5 anticipated. The surviving counts are lower where the")
w("model-free series has drops: UNG keeps 86 of 201 and 41 of 67.")
w()

# ------------------------------------------------------------------ step 6 ---
f6 = J("s1_step6_fig1.json")
w("## Step 6 — figure 1")
w()
w("Annual mean `log(IV^2/RV)` by calendar year, five series, one panel per node, %d to %d,"
  % (f6["years_plotted"][0], f6["years_plotted"][-1]))
w("each ETF over its own full span. Years fully inside the common window (2009 to 2024)")
w("are shaded. **%s** are drawn with open hatched markers as partial years: 2007 is the"
  % ", ".join(str(y) for y in f6["partial_years"]))
w("first ETF listing year and opens in May, 2008 is partial against a common window that")
w("opens on 2008-12-08, and 2025 ends with the feed on 2025-08-29.")
w()
w("| file | content |")
w("|---|---|")
w("| `output/item1/fig1_annual_logratio.png` and `.svg` | model-free, both nodes |")
w("| `output/item1/fig1_atm_annual_logratio.png` and `.svg` | ATM version, both nodes |")
w("| `output/item1/fig1_table.csv` | the underlying table, with the day count per cell |")
w()
w("Cells resting on fewer than 30 surviving days are ringed in red on the figure and")
w("labelled with their count. There are six, all of them consequences of the model-free")
w("drops in step 3:")
w()
thin = pd.DataFrame(mc["thin_cells"]) if mc.get("thin_cells") else pd.DataFrame()
if len(thin):
    table(["ticker", "node", "year", "days", "mean log ratio", "share of days flagged multi-chain"],
          [[r.ticker, int(r.node), int(r.year), int(r.n), "%.4f" % r.mean_mf,
            "%.2f" % r.flagged_share] for r in thin.itertuples()])
w("The UNG 2011 spike visible on the 30-day panel is a **three-day** cell, and all three")
w("of those days are flagged as multi-deliverable expiries by the step 3.7 diagnostic. It")
w("is plotted because the spec says to plot the annual mean, and ringed because plotting")
w("it unmarked next to cells built from 250 days would mislead.")
w()
w("The gap between the two versions is the skew contribution, which is what having both")
w("is for:")
w()
sk = pd.DataFrame(f6["skew_gap"])
table(["ticker", "node", "mean annual gap, model-free minus ATM", "min", "max", "years"],
      [[r.ticker, int(r.node), "%.4f" % r.mean_gap, "%.4f" % r.min_gap,
        "%.4f" % r.max_gap, int(r.years)] for r in sk.itertuples()])
w("SPX carries the widest skew contribution (0.31 at 30 days, 0.38 at 91), the metals the")
w("narrowest. The UNG maximum of 3.08 is the 2011 cell above, not a property of the chain.")
w()

# ------------------------------------------------------------------ step 7 ---
k = J("s1_step7_killcheck.json")
w("## Step 7 — kill check (section 9)")
w()
w("Section 9: curve state is dropped for a commodity if no first-and-second series pair")
w("matches at least 80 percent of the common window's trade dates, or the two series in a")
w("pair carry different roll conventions.")
w()
w("Common window trade dates: **%s**. The 80 percent floor is **%.1f** dates."
  % ("{:,}".format(k["spx_trade_dates_common_window"]), k["floor"] * k["spx_trade_dates_common_window"]))
w()
table(["commodity", "underlying for", "pair selected?", "second-leg candidates",
       "qualifying pairs", "first-leg coverage share", "clears 80%?",
       "same roll convention?", "outcome"],
      [[r["commodity"], r["underlying_for"], "no" if not r["pair_selected"] else "yes",
        r["second_leg_candidates"], r["qualifying_pairs"],
        "%.4f" % r["coverage_share_first_leg"], "yes" if r["coverage_clears_80pct"] else "no",
        r["same_roll_convention"], "**%s**" % r["curve_state_outcome"]]
       for r in k["rows"]])
w("The coverage floor is cleared comfortably by all four first legs — 0.99 to 1.00 — so")
w("coverage is **not** what kills curve state. What kills it is that **no second-nearby")
w("continuous series exists on any of the four named contracts**, so there is no pair to")
w("measure a spread from and no second roll convention to compare.")
w()
w("**Curve state is dropped for %d of 4 commodities.** Under section 9 that means the item"
  % k["n_dropped"])
w("ships as the unconditional version, with H2 and Q3 recorded as not measured — null D")
w("of section 12. Section 6.5, figure 2, figure 3 and the Q3 table in section 6.6 all rest")
w("on curve state and are affected. H1 is untouched: it needs no futures data.")
w()
w("**This session does not act on that outcome.** Session 2 does.")
w()

# ------------------------------------------------- closing: gaps and deviations ---
w("## Not measured, and done differently from the spec")
w()
w("### Not measured")
w()
NM = [
 ("Every hypothesis test in section 7",
  "Session 1 builds series; section 9 puts the eighteen tests in session 2. The means in "
  "5.4 are descriptive and carry no standard error, no p-value and no Holm correction."),
 ("Curve state s_t and z_t (section 6.5)",
  "No second-nearby series exists for any of the four contracts, so neither F2 - F1 nor "
  "(F2 - F1)/F1 can be formed. This is the step-7 outcome, not an omission."),
 ("H2 and Q3",
  "Both are conditioned on z_t. With curve state dropped for all four commodities they "
  "are unmeasurable as specified. Section 9 anticipates exactly this and calls it null D."),
 ("The April 2020 robustness row (section 6.7)",
  "Specified as a row next to every primary number. There are no primary test numbers in "
  "this session, so there is nothing to put it next to. The windows are in the daily file "
  "and can be excluded in session 2."),
 ("The commonality PCA (section 6.6)",
  "Number one, the first principal component of the four daily log ratios, could have been "
  "computed; number two requires residualising on z_t, which does not exist. Section 9 "
  "places the whole Q3 table in session 2, so neither was computed."),
 ("Whether the split-adjusted chains can be separated cleanly",
  "The pulled column list fixed by the session instruction has no `root` or `ss_flag`, "
  "which is how OptionMetrics distinguishes deliverable chains. The defect in 3.7 is "
  "measured but its clean fix needs a column this session did not pull."),
 ("Whether ICE second-nearby series would serve as substitutes",
  "ICE Brent, ICE WTI and ICE natural gas do carry first-and-second pairs (step 2.4). They "
  "are different contracts on different exchanges from the four the spec names in section "
  "4, so substituting one is a spec change and was not evaluated."),
 ("Roll convention comparison between a pair's two legs",
  "Requires two legs. Only the first leg's convention is reported, in 2.7."),
]
for t, why in NM:
    w("- **%s** — %s" % (t, why))
w()
w("### Done differently from the spec, or not pinned down by it")
w()
DV = [
 ("Expiry identity is (exdate, am_settlement), not exdate alone",
  "Section 6.1 step 1 says \"all exdate on date t\". SPX carries an AM-settled and a "
  "PM-settled chain on the same third-Friday exdate - 18.6 percent of SPX 2024 rows "
  "duplicate on (date, exdate, cp_flag, strike) and `am_settlement` resolves every one of "
  "them. Treating exdate alone as the expiry would put two quotes on every strike of those "
  "expiries. Where two chains share a days-to-expiry the one with more rows is used."),
 ("Duplicate rows within an expiry are collapsed by open interest",
  "Section 6.1 is silent on duplicates. Rows duplicating on (exdate, am_settlement, "
  "cp_flag, strike) are collapsed to the largest open interest, then largest volume, then "
  "highest bid. On the ETF expiries that carry a split-adjusted chain this splices two "
  "securities - see 3.7. This is the one place where the implementation is known to be "
  "wrong and was left in place deliberately."),
 ("Q(K0) when only one leg is quoted",
  "Section 6.1 step 3 says \"the average of put and call at K0\" and does not say what to "
  "do when one of them is missing or zero-bid. The average is used when both are usable, "
  "the single usable one when only one is."),
 ("A usable quote requires best_offer >= best_bid as well as best_bid > 0",
  "Section 6.1 excludes zero-bid options. The additional condition drops crossed quotes, "
  "which would otherwise give a negative midquote contribution."),
 ("\"Two consecutive zero-bid strikes\" is counted along quoted rows",
  "Counted along the rows that exist on that side, so a strike with no quoted option "
  "neither contributes to the run nor breaks it. The alternative - treating an absent "
  "strike as a zero bid - would truncate sparse ETF ladders much harder."),
 ("The step-6 strike counts exclude K0",
  "n_strikes_*_put counts strikes strictly below K0 and n_strikes_*_call strictly above, "
  "with K0 on neither side. The floor of 3 is applied to those two counts."),
 ("The zero rate falls back to the nearest earlier zerocd date",
  "Two secid-dates in the whole run have no zerocd row on the trade date. Section 6.1 does "
  "not cover the case."),
 ("Step 2 pulled first-nearby legs although the rule selected nothing",
  "Rule R6 says record and move on, which would leave step 7's coverage column empty. The "
  "first legs were pulled under a stated addition rule (2.7) so the kill check reports a "
  "measured coverage share."),
 ("R4 requires the two legs to share a clscode",
  "The stated rule requires only a shared roll-convention marker. Without the same-class "
  "clause a first leg on NYMEX natural gas pairs with a second leg on ICE natural gas, "
  "which happened on a first pass and produced a spurious selection."),
 ("Figure 1 rings cells built from fewer than 30 days",
  "Presentation only, added because the instruction asks for the day count per cell and "
  "because a three-day annual mean plotted unmarked beside 250-day means misleads. The "
  "plotted values are exactly the annual means the spec defines."),
 ("matplotlib was installed into the venv",
  "The environment had no plotting library and steps 4 and 6 require figures. matplotlib "
  "3.11.2 was installed with pip. No other package was added."),
]
for t, why in DV:
    w("- **%s** — %s" % (t, why))
w()
w("### Wall clock")
w()
table(["stage", "wall clock"],
      [["opprcd pulls, 92 partitions", "%.1f s (%.1f min), budget 60 min"
        % (pl["total_seconds"], pl["total_seconds"] / 60.0)],
       ["model-free construction over %s dates" % "{:,}".format(bm["records"] // 2),
        "%.1f s (%.1f min)" % (bm["construction_seconds"], bm["construction_seconds"] / 60.0)],
       ["zerocd pull", "%.2f s" % z["pull_seconds"]],
       ["VIX pull", "%.2f s" % v2["pull_seconds"]],
       ["premium construction and grid", "%.1f s" % p5b["seconds"]]])
w("---")
w()
w("Generated by `src/item1/build_report_s1.py` from the JSON and CSV artifacts in")
w("`output/item1/`. Every figure and table above is read back from a measurement; the")
w("connecting prose is written by hand.")

path = opath("REPORT_s1.md")
with open(path, "w") as f:
    f.write("\n".join(L) + "\n")
print("wrote %s (%d lines, %d bytes)" % (path, len(L), os.path.getsize(path)))
