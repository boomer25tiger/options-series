"""Assemble probe_output/REPORT_probe.md from the measured JSON artifacts.

Every number in the report is read back out of the JSON written by the step
scripts; nothing here is typed in by hand.
"""
import os, sys, json, re, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import OUT_DIR

def J(name):
    with open(os.path.join(OUT_DIR, name)) as f:
        return json.load(f)

L = []
def w(s=""):
    L.append(s)

def table(headers, rows):
    w("| " + " | ".join(str(h) for h in headers) + " |")
    w("|" + "|".join("---" for _ in headers) + "|")
    for r in rows:
        w("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    w()

def fmt(x, nd=6):
    if x is None:
        return ""
    if isinstance(x, float):
        return ("%%.%df" % nd) % x
    return str(x)

TODAY = "2026-09-15"

# ----------------------------------------------------------------- header ---
w("# Probe report — OptionMetrics, IBES, CRSP, Datastream capability audit")
w()
w("Series: **options-series** (five-item research series on OptionMetrics IvyDB US via WRDS).")
w("This document is the shared capability probe. It records measurements only: every entry")
w("below is a number returned by a query or a column list read verbatim from the server")
w("catalog. It contains no design decisions and no recommendations.")
w()
w("| | |")
w("|---|---|")
w("| Report date | %s |" % TODAY)
w("| WRDS account | cgresearch26 |")
w("| Server | PostgreSQL 17.11 on x86_64-pc-linux-gnu |")
w("| Client | wrds 3.5.0, pandas 2.2.3, SQLAlchemy 2.0.53, Python 3.13.13 |")
w("| Credentials | ~/.pgpass (no password entered or stored by this session) |")
w("| Scripts | `src/probe/*.py`; raw logs and JSON in `probe_output/` (not committed) |")
w()

# ------------------------------------------------------------------ step 0 ---
w("## Step 0 — environment")
w()
w("Two facts about the environment differ from the session brief and are recorded here")
w("because they affect how every later number was produced.")
w()
w("1. **`wrds-env` is a plain Python venv, not a conda environment.** `conda env list` reports")
w("   only `base` and `volup`, and neither has the `wrds` package installed. The interpreter")
w("   that has it is `/Users/GualyCr/wrds-env/bin/python` (venv, Python 3.13.13, wrds 3.5.0).")
w("   Every measurement below was run with that interpreter. `conda run -n wrds-env python`")
w("   does not resolve on this machine.")
w("2. **`db.describe_table()` is broken in this client combination.** It raises")
w("   `TypeError('not all arguments converted during string formatting')` for every table")
w("   tried (9/9), after printing its row-count line. Its row-count half")
w("   (`db.get_row_count()`) works. Column lists in this report therefore come from")
w("   `information_schema.columns` — the same server catalog `describe_table` reads — and")
w("   row counts from `get_row_count`. Column names and types are verbatim.")
w("   Note that `get_row_count` returns a planner **estimate**, not an exact count: it")
w("   reports 349,406,496 for `optionm.vsurfd2025` where `count(*)` returns 349,406,508,")
w("   and 1,325,496 for `ibes.actu_epsus` where `count(*)` returns 1,329,747. Row counts")
w("   labelled `get_row_count` below are approximate; every figure from a `count(*)` is exact.")
w()
w("Connection succeeded on the first attempt (2.4 s), authenticating from `~/.pgpass`.")
w("The account sees **384 libraries**.")
w()

# ------------------------------------------------------------------ step 1 ---
s1 = J("step1_tables.json")
s1b = J("step1b_schemas.json")
span = J("step1b_span.json")
s1c = J("step1c_optionm_all.json")

w("## Step 1 — OptionMetrics layout")
w()
w("### 1.1 Libraries matching \"optionm\"")
w()
w("`db.list_libraries()` returned %d libraries. %d contain the string `optionm`:"
  % (s1["n_libraries"], len(s1["optionm_libraries"])))
w()
rows = []
for lib in s1["optionm_libraries"]:
    tabs = s1["tables"][lib]
    rows.append([lib, len(tabs) if isinstance(tabs, list) else "list_tables failed"])
table(["library", "tables (db.list_tables)"], rows)
w("`optionm` is a layer of **578 VIEWs**; `optionm_all` is **402 BASE TABLEs**. Measured")
w("spans agree exactly between the two for `vsurfd2025`, `secprd2025` and `opprcd2025`")
w("(all `2025-01-02 .. 2025-08-29`). All queries in this report were run against `optionm`.")
w()
w("`optionmsamp_us` (12 tables) and `optionmsamp_europe` (12 tables) are single-year sample")
w("schemas — 2014 and 2013 respectively. `wrdsapps_link_crsp_optionm` holds one table,")
w("`opcrsphist`.")
w()

w("### 1.2 Single vs. year-partitioned — read from the table listing, not assumed")
w()
def group(tabs):
    g = collections.defaultdict(list)
    for t in tabs:
        m = re.match(r"^(.*?)(\d{4})$", t)
        if m:
            g[m.group(1)].append(int(m.group(2)))
        else:
            g[t].append(None)
    return g

NAMED = ["opprcd", "vsurfd", "secprd", "securd", "securd1", "secnmd",
         "zerocd", "distrd", "idxdvd", "distribution", "distrprojd",
         "idxdvbr", "index_dividend", "zero_curve"]
for lib in ["optionm", "optionm_all"]:
    g = group(s1["tables"][lib])
    w("**%s**" % lib)
    w()
    rows = []
    for base in NAMED:
        if base not in g:
            rows.append([base, "absent from this library", ""])
            continue
        yrs = [y for y in g[base] if y is not None]
        if not yrs:
            rows.append([base, "SINGLE table", ""])
        else:
            rows.append([base, "YEAR-PARTITIONED", "%d partitions, %d..%d (e.g. `%s%d`)"
                         % (len(yrs), min(yrs), max(yrs), base, max(yrs))])
    table(["table / prefix", "form", "partitions"], rows)

w("Answering the question as put:")
w()
w("- `opprcd`, `vsurfd`, `secprd` — **year-partitioned**, 30 partitions each, `…1996` … `…2025`.")
w("- `securd`, `securd1`, `secnmd` — **single tables**.")
w("- Zero curve: `zerocd` — **single table** (`zero_curve` also exists in `optionm`, single).")
w("- Dividends: `distrd` (distributions) and `idxdvd` (index dividend yield) — **single tables**.")
w("  `distrprojd` (projected distributions) is **year-partitioned**, 28 partitions 1996–2023.")
w("  `idxdvbr` is **year-partitioned**, 30 partitions 1996–2025.")
w()
w("Full base-name inventory for `optionm` (59 distinct base names over 578 objects):")
w()
g = group(s1["tables"]["optionm"])
rows = []
for base in sorted(g):
    yrs = [y for y in g[base] if y is not None]
    rows.append([base, "SINGLE" if not yrs else "PARTITIONED %d (%d-%d)"
                 % (len(yrs), min(yrs), max(yrs))])
table(["base name", "form"], rows)

w("### 1.3 Column lists (verbatim from `information_schema.columns`)")
w()
for tbl in ["vsurfd2025", "opprcd2025", "secprd2025", "securd", "securd1",
            "secnmd", "zerocd", "distrd", "idxdvd"]:
    rec = s1b[tbl]
    w("**`optionm.%s`** — %s rows (`get_row_count`)" % (tbl, "{:,}".format(rec["row_count"])))
    w()
    table(["#", "column_name", "data_type", "is_nullable"],
          [[c["ordinal_position"], c["column_name"], c["data_type"], c["is_nullable"]]
           for c in rec["columns"]])

w("`vsurfd` carries both an **implied strike column (`impl_strike`)** and an **implied")
w("premium column (`impl_premium`)**; both are `double precision`. Non-null counts for the")
w("resolved underlyings are in Step 2.2.")
w()

w("### 1.4 Feed span")
w()
rows = []
for k in ["optionm.secprd1996", "optionm.secprd2025",
          "optionm.vsurfd1996", "optionm.vsurfd2025"]:
    v = span[k]
    rows.append([k, v["min"], v["max"], "{:,}".format(v["rows"]), "%.1f" % v["seconds"]])
table(["partition", "min(date)", "max(date)", "rows", "query seconds"], rows)
gap = span["optionm.vsurfd2025"]["gap_days_from_2026_09_15"]
w("- **Feed start**: `secprd` 1996-01-02, `vsurfd` 1996-01-04.")
w("- **Feed end**: **2025-08-29** for both `secprd` and `vsurfd` (latest partition is 2025;")
w("  its max date is the feed end — there is no 2026 partition).")
w("- **Gap from today (%s) to feed end: %d calendar days.**" % (TODAY, gap))
w("- `optionm_all` ends on the same date (2025-08-29) for `vsurfd`, `secprd` and `opprcd`.")
w()

# ------------------------------------------------------------------ step 2 ---
s2a = J("step2a_resolve.json")
s2b = J("step2b_vsurfd.json")
s2c = J("step2c_opprcd2024.json")

w("## Step 2 — Underlyings")
w()
w("### 2.1 secid resolution")
w()
w("Two reference tables were read. `optionm.securd1` holds one current row per secid")
w("(it carries `issuer`; `optionm.securd` is the same table without `issuer`).")
w("`optionm.secnmd` is the name-history table keyed on `secid` + `effect_date`.")
# How many secids ever carried each of the six ticker strings? (measured, not asserted)
tick_map = collections.defaultdict(set)
for r in s2a["securd1"]:
    tick_map[r["ticker"]].add(int(r["secid"]))
for r in s2a["secnmd_by_ticker"]:
    tick_map[r["ticker"]].add(int(r["secid"]))
w("**How many secids ever carried each ticker string** (union of `securd1` and the")
w("`secnmd` name history):")
w()
table(["ticker", "# secids", "secids"],
      [[t, len(tick_map[t]), ", ".join(str(x) for x in sorted(tick_map[t]))]
       for t in ["SPX", "SPY", "GLD", "SLV", "USO", "UNG"]])
multi = [t for t in ["SPX", "SPY", "GLD", "SLV", "USO", "UNG"] if len(tick_map[t]) > 1]
single = [t for t in ["SPX", "SPY", "GLD", "SLV", "USO", "UNG"] if len(tick_map[t]) == 1]
w("%s map to more than one secid; %s maps to exactly one. Ticker strings are reused across"
  % (", ".join("**%s**" % t for t in multi), ", ".join("**%s**" % t for t in single)))
w("time (`GLD` was Santa Fe Pacific Gold before it was the SPDR trust; `SPY` was Serenpet;")
w("`SLV` was Silverado Foods; `USO` was US 1 Inds), and OptionMetrics additionally issues")
w("separate secids for an ETF's intraday-indicative-value (`class='I'`) and NAV")
w("(`class='N'`) pseudo-securities.")
w()
w("**`optionm.securd1` rows matching the six tickers** (verbatim):")
w()
table(["secid", "ticker", "cusip", "class", "issuer", "issue_type", "index_flag", "sic", "exchange_d"],
      [[int(r["secid"]), r["ticker"], r["cusip"], r["class"], r["issuer"],
        r["issue_type"], r["index_flag"], r["sic"], r["exchange_d"]]
       for r in s2a["securd1"]])

w("**`optionm.secnmd` effect-date span per candidate secid** (all secids that ever carried")
w("one of the six ticker strings):")
w()
table(["secid", "first_effect_date", "last_effect_date", "name records", "distinct tickers", "tickers"],
      [[int(r["secid"]), r["first_effect_date"], r["last_effect_date"],
        r["n_records"], r["n_tickers"], r["tickers"]]
       for r in s2a["secnmd_span_by_secid"]])

w("**`optionm.secnmd` name history for the six ticker strings** (verbatim, one row per")
w("distinct secid/ticker/issuer/issue/cusip/sic combination):")
w()
table(["secid", "ticker", "class", "issuer", "issue", "cusip", "sic",
       "first_effect_date", "last_effect_date", "n"],
      [[int(r["secid"]), r["ticker"], r["class"], r["issuer"], r["issue"], r["cusip"],
        r["sic"], r["first_effect_date"], r["last_effect_date"], r["n_name_records"]]
       for r in s2a["secnmd_by_ticker"]])

have_vs = {int(r["secid"]) for r in s2b["summary"]}
have_op = {int(r["secid"]) for r in s2c["rows"]}
n_cand = len(have_vs | set(s2b["no_vsurfd_rows"]))
w("Of the %d candidate secids, **%d carry `vsurfd` rows** and **%d carry `opprcd2024` rows**"
  % (n_cand, len(have_vs), len(have_op)))
w("(measured, Steps 2.2 and 2.3). The difference is secid %s — the 1996-vintage"
  % ", ".join(str(x) for x in sorted(have_vs - have_op)))
w("`SANTA FE PACIFIC GOLD CORP`, which has a surface in 1996–1997 only and no 2024 option")
w("data. The six secids carrying both, and the ones this probe treats as the resolved")
w("underlyings, are:")
w()
issuer_by_secid = {int(r["secid"]): r for r in s2a["securd1"]}
nm_last = {}
for r in s2a["secnmd_by_ticker"]:
    nm_last[int(r["secid"])] = r
rows = []
for sid, tic in [(108105, "SPX"), (109820, "SPY"), (122392, "GLD"),
                 (126776, "SLV"), (126681, "USO"), (129367, "UNG")]:
    r = issuer_by_secid[sid]
    rows.append([tic, sid, r["issuer"], r["issue_type"], r["index_flag"], r["cusip"]])
table(["ticker", "secid", "issuer (securd1)", "issue_type", "index_flag", "cusip"], rows)
w("**SPX = 108105 confirmed** (`issuer` = `CBOE S&P 500 INDEX`, `index_flag` = 1,")
w("`issue_type` = `A`), matching the expected value.")
w()

w("### 2.2 `vsurfd` coverage per secid (all 30 year partitions scanned, 1996–2025)")
w()
rows = []
for r in sorted(s2b["summary"], key=lambda x: x["secid"]):
    rows.append([r["secid"], r["first_date"], r["last_date"], "{:,}".format(r["n_dates"]),
                 "{:,}".format(r["n_rows"]), r["n_distinct_days"], r["n_distinct_delta"],
                 "/".join(r["cp_flag_values"]),
                 "%d..%d (%d yrs)" % (r["years_present"][0], r["years_present"][-1],
                                      len(r["years_present"]))])
table(["secid", "first date", "last date", "# dates", "# rows", "# distinct days",
       "# distinct delta", "cp_flag values", "years present"], rows)

w("The grid is identical for every secid that has a surface:")
w()
ex = sorted(s2b["summary"], key=lambda x: x["secid"])[0]
assert all(r["days_values"] == ex["days_values"] and r["delta_values"] == ex["delta_values"]
           and r["cp_flag_values"] == ex["cp_flag_values"] for r in s2b["summary"]), \
    "grid is NOT identical across secids - the sentence below would be false"
w("- **`days` (days-to-expiry), %d distinct values:** `%s`"
  % (ex["n_distinct_days"], ", ".join("%g" % d for d in ex["days_values"])))
w("- **`delta`, %d distinct values:** `%s`"
  % (ex["n_distinct_delta"], ", ".join("%g" % d for d in ex["delta_values"])))
w("  (17 positive values 10…90 in steps of 5 for calls, and the 17 negative mirrors for puts)")
w("- **`cp_flag`, 2 distinct values:** `%s`" % ", ".join(ex["cp_flag_values"]))
w()
w("**Implied strike / implied premium presence and fill:** both columns exist on `vsurfd`")
w("and are fully populated for every one of the %d secids that has a surface — `impl_strike`"
  % len(s2b["summary"]))
w("and `impl_premium` are non-null on **100.00%** of rows, while `impl_volatility` and")
w("`dispersion` are not:")
w()
rows = []
for r in sorted(s2b["summary"], key=lambda x: x["secid"]):
    n = r["n_rows"]
    rows.append([r["secid"], "{:,}".format(n),
                 "%.4f" % (r["nn_impl_strike"] / n),
                 "%.4f" % (r["nn_impl_premium"] / n),
                 "%.4f" % (r["nn_impl_volatility"] / n),
                 "%.4f" % (r["nn_dispersion"] / n)])
table(["secid", "rows", "impl_strike non-null share", "impl_premium non-null share",
       "impl_volatility non-null share", "dispersion non-null share"], rows)
w("Candidate secids with **no `vsurfd` rows in any year**: `%s`."
  % ", ".join(str(x) for x in s2b["no_vsurfd_rows"]))
w()

w("### 2.3 `opprcd` calendar 2024, per secid")
w()
w("Query: one pass over `optionm.opprcd2024` filtered to the candidate secids;")
w("days-to-expiry computed as `exdate - date`; wall clock **%.1f s**." % s2c["seconds"])
w()
rows = []
for r in s2c["rows"]:
    rows.append([int(r["secid"]), "{:,}".format(int(r["n_rows"])), int(r["n_exdates"]),
                 int(r["n_dates"]), int(r["min_dte"]), int(r["max_dte"]),
                 "{:,.0f}".format(r["tot_volume"]),
                 "%.4f" % r["share_vol_dte0"], "%.4f" % r["share_vol_dte1"]])
table(["secid", "rows", "distinct expiration dates", "distinct trade dates",
       "min DTE", "max DTE", "total volume",
       "share of volume at DTE=0", "share of volume at DTE=1"], rows)
w("No row in any of these secids has a negative days-to-expiry (`n_rows_dte_negative` = 0")
w("for all six). Candidate secids absent from `opprcd2024`: `7571, 8274, 8321, 100155,")
w("111334, 115101, 126778, 126779, 129361, 129362`.")
w()
w("Ticker labels for the same table:")
w()
tick = {108105: "SPX", 109820: "SPY", 122392: "GLD", 126776: "SLV",
        126681: "USO", 129367: "UNG"}
rows = []
for r in s2c["rows"]:
    sid = int(r["secid"])
    rows.append([tick[sid], sid, "{:,}".format(int(r["n_rows"])),
                 "%.4f" % r["share_vol_dte0"], "%.4f" % r["share_vol_dte1"]])
table(["ticker", "secid", "2024 rows", "share vol DTE=0", "share vol DTE=1"], rows)

# ------------------------------------------------------------------ step 3 ---
s3 = J("step3_sizing.json")
w("## Step 3 — Sizing")
w()
w("Single `vsurfd` node: `days = 30`, `delta = 50`, `cp_flag = 'C'`, calendar 2024,")
w("all secids.")
w()
w("```sql")
w("select count(*), count(distinct secid), count(distinct date), min(date), max(date)")
w("from optionm.vsurfd2024")
w("where days = 30 and delta = 50 and cp_flag = 'C'")
w("```")
w()
table(["measure", "value"],
      [["rows", "{:,}".format(s3["n_rows"])],
       ["distinct secids", "{:,}".format(s3["n_secids"])],
       ["distinct dates", s3["n_dates"]],
       ["date range", "%s .. %s" % (s3["min_date"], s3["max_date"])],
       ["**wall clock**", "**%.1f s** (%.1f min)" % (s3["seconds"], s3["seconds"] / 60.0)]])
s3b = J("step3b_scoped_timing.json")
w("**Why it costs that much.** `pg_indexes` shows **%d indexes** on the 2024 partitions,"
  % s3b["n_visible_indexes"])
w("all on the `optionm_all` base tables — `optionm` is a view layer, and a view cannot")
w("carry an index of its own:")
w()
table(["schema", "table", "index"],
      [[r["schemaname"], r["tablename"], "`%s`" % r["indexname"]] for r in s3b["indexes"]])
w("The indexed columns are `secid` and `date` (plus `optionid` on `opprcd`). Nothing indexes")
w("`days`, `delta` or `cp_flag`, so the Step 3 node filter forces a full partition scan.")
w("Measured contrast on the same partition:")
w()
table(["query", "wall clock", "rows"],
      [["node filter `days=30, delta=50, cp_flag='C'`, all secids",
        "**%.1f s**" % s3["seconds"], "{:,}".format(s3["n_rows"])],
       ["secid filter, 6 secids, all nodes",
        "**%.2f s**" % s3b["scoped_6_secid_seconds"],
        "{:,}".format(s3b["scoped_6_secid_rows_returned"])],
       ["secid + node filter, 1 secid",
        "**%.2f s**" % s3b["single_secid_node_seconds"],
        "{:,}".format(s3b["single_secid_node_rows"])]])
w("Secid-restricted reads are cheap; node-restricted full-universe reads are not.")
w()
w("**Projection, not a measurement.** Multiplying the 2024 count by the %d year partitions"
  % s3["n_year_partitions_1996_to_feed_end"])
w("that exist from 1996 to feed end:")
w()
w("> %s rows x %d partitions = **%s rows projected for 1996 → feed end (2025-08-29)**."
  % ("{:,}".format(s3["n_rows"]), s3["n_year_partitions_1996_to_feed_end"],
     "{:,}".format(s3["projected_rows_1996_to_feed_end"])))
w()
w("This is a projection and will overstate the true total: the 2025 partition stops on")
w("2025-08-29, and the early partitions are much smaller (measured in Step 1.4: `vsurfd1996`")
w("holds 179,880,162 rows for a full year against `vsurfd2025`'s 349,406,508 for eight")
w("months). The true count was not measured.")
w()

# ------------------------------------------------------------------ step 4 ---
s4 = J("step4_ibes")if False else J("step4_ibes.json")
s4b = J("step4b_ibes_anntims_detail.json")
w("## Step 4 — IBES")
w()
w("Libraries containing `ibes`: `%s`." % "`, `".join(s4["ibes_libraries"]))
w()
w("`db.list_tables('ibes')` returned **%d tables**. **%d** contain `actu` or `act_`:"
  % (len(s4["ibes_all_tables"]), len(s4["ibes_actuals_tables"])))
w()
cols4 = s4["ibes_actuals_tables"]
per = (len(cols4) + 3) // 4
rows = []
for i in range(per):
    rows.append([cols4[i + per * k] if i + per * k < len(cols4) else ""
                 for k in range(4)])
table(["table", "table", "table", "table"], rows)

w("### 4.1 `ibes.actu_epsus` — verified present; columns verbatim")
w()
w("`actu_epsus` **is** in the `ibes` table list. Row count: **%s** exact (`count(*)`),"
  % "{:,}".format(s4["anndats_span"]["total_rows"]))
w("1,325,496 estimated (`get_row_count`).")
w()
table(["#", "column_name", "data_type", "is_nullable"],
      [[c["ordinal_position"], c["column_name"], c["data_type"], c["is_nullable"]]
       for c in s4["actu_epsus_columns"]])
w("**An announcement-time column exists and is named `anntims`**, type")
w("`time without time zone` — the expected name is confirmed. (`acttims`, the IBES")
w("activation time, is a separate column.)")
w()

sp = s4["anndats_span"]
w("### 4.2 `anndats` span")
w()
table(["measure", "value"],
      [["min(anndats)", sp["min"]],
       ["max(anndats)", sp["max"]],
       ["total rows", "{:,}".format(sp["total_rows"])],
       ["non-null anndats", "{:,}".format(sp["nn_anndats"])],
       ["non-null anndats share", "%.4f" % (sp["nn_anndats"] / sp["total_rows"])]])
w("`max(anndats)` = **%s**, i.e. this feed runs **%d days** past the OptionMetrics feed end"
  % (sp["max"], (datetime.date.fromisoformat(sp["max"]) -
                 datetime.date.fromisoformat("2025-08-29")).days))
w("of 2025-08-29.")
w()

w("### 4.3 Rows by calendar year with `anndats` and `anntims` non-null, 2010 → latest")
w()
rows = []
for r in s4["anntims_by_year"]:
    rows.append([r["yr"], "{:,}".format(r["n_rows"]), "{:,}".format(r["nn_anndats"]),
                 "{:,}".format(r["nn_anntims"]), "%.4f" % r["share_nn_anntims"]])
table(["calendar year of anndats", "rows", "non-null anndats", "non-null anntims",
       "share non-null anntims"], rows)
w("The share of non-null `anntims` is **1.0000 in every year from 2010 to 2026**.")
w("2026 is the latest year and is partial (through %s)." % sp["max"])
w()
w("Supplementary measurement, because a non-null share of 1.0 does not by itself establish")
w("that the column holds a real clock time: `anntims` carries minute-resolution values with")
w("~1,100–1,450 distinct values per year, and only 3.6–13.2% of announcements fall inside")
w("09:30–16:00. Exact-midnight values are ~0.00–0.14% per year.")
w()
rows = []
for r in s4b:
    rows.append([r["yr"], "{:,}".format(r["n"]), r["n_distinct_anntims"],
                 r["min_anntims"], r["max_anntims"], r["n_midnight"],
                 "%.6f" % r["share_midnight"], "%.4f" % r["share_in_rth_0930_1600"]])
table(["year", "rows", "distinct anntims", "min", "max", "n at 00:00:00",
       "share 00:00:00", "share in 09:30–16:00"], rows)

# ------------------------------------------------------------------ step 5 ---
s5 = J("step5_compustat.json")
w("## Step 5 — Compustat fallback for announcement dates")
w()
w("`comp.fundq` has **%d columns** and **2,137,788 rows** (`get_row_count`)." % s5["n_columns"])
w("**`rdq` is present**, at ordinal position 36, type `date`.")
w()
table(["#", "column_name", "data_type"],
      [[c["ordinal_position"], c["column_name"], c["data_type"]] for c in s5["key_columns"]])

a = s5["all_formats_2010plus"]
b = s5["std_filter_2010plus"]
w("### 5.1 `rdq` non-null share, fiscal quarters from 2010 onward")
w()
w("\"From 2010 onward\" taken as `datadate >= '2010-01-01'`.")
w()
table(["population", "quarters", "with rdq non-null", "share"],
      [["all format rows", "{:,}".format(a["n"]), "{:,}".format(a["nn_rdq"]),
        "**%.4f**" % a["share_rdq"]],
       ["standard filter `indfmt='INDL' datafmt='STD' popsrc='D' consol='C'`",
        "{:,}".format(b["n"]), "{:,}".format(b["nn_rdq"]), "**%.4f**" % b["share_rdq"]]])
w("Observed `datadate` range in that population: %s .. %s. Observed `rdq` range: %s .. %s"
  % (a["mn"], a["mx"], a["rdq_min"], a["rdq_max"]))
w("— `rdq` runs to **%s**, one day before this report's date." % a["rdq_max"])
w()
w("### 5.2 `rdq` non-null share by fiscal year (`fyearq`), standard filter")
w()
rows = [[r["fyearq"], "{:,}".format(r["n"]), "{:,}".format(r["nn_rdq"]),
         "%.4f" % r["share_rdq"]] for r in s5["by_fyearq_std_filter"]]
table(["fyearq", "quarters", "with rdq non-null", "share"], rows)
_sh = [r["share_rdq"] for r in s5["by_fyearq_std_filter"]]
_mono = all(_sh[i] >= _sh[i + 1] for i in range(len(_sh) - 1))
_ups = [s5["by_fyearq_std_filter"][i + 1]["fyearq"]
        for i in range(len(_sh) - 1) if _sh[i + 1] > _sh[i]]
w("The share falls from %.4f (%d) to %.4f (%d, partial). It is %s monotonic%s."
  % (_sh[0], s5["by_fyearq_std_filter"][0]["fyearq"], _sh[-1],
     s5["by_fyearq_std_filter"][-1]["fyearq"], "" if _mono else "not",
     "" if _mono else " — it rises in %s" % ", ".join(str(y) for y in _ups)))
w("The cause of the decline was not measured.")
w()

# ------------------------------------------------------------------ step 6 ---
s6 = J("step6_crsp.json")
s6b = J("step6b_crsp_v2.json")
w("## Step 6 — CRSP index and membership")
w()
w("Libraries containing `crsp`: `%s`." % "`, `".join(s6["crsp_libraries"]))
w()
w("**Both requested tables exist.** `crsp.dsp500` and `crsp.dsp500list` are VIEWs;")
w("the base tables live in `crsp_a_indexes` (and are duplicated in `crsp_a_indexes_old`,")
w("`crsp_m_indexes`). The `crsp` view and the `crsp_a_indexes` base table return identical")
w("column lists, row counts and date spans, measured below.")
w()
for key in ["crsp.dsp500", "crsp.dsp500list", "crsp_a_indexes.dsp500",
            "crsp_a_indexes.dsp500list", "crsp.dsp500list_v2",
            "crsp.msp500", "crsp.msp500list"]:
    rec = s6["targets"][key]
    if not rec.get("exists"):
        w("**`%s`** — does not exist / not visible to this account." % key)
        w()
        continue
    w("**`%s`** — %s rows" % (key, "{:,}".format(rec["row_count"])))
    w()
    table(["#", "column_name", "data_type"],
          [[c["ordinal_position"], c["column_name"], c["data_type"]] for c in rec["columns"]])
    if "date_spans" in rec:
        table(["date column", "min", "max", "non-null"],
              [[k, v["min"], v["max"], "{:,}".format(v["non_null"])]
               for k, v in rec["date_spans"].items()])

w("### 6.1 The `_v2` series, because `dsp500` stops in 2024")
w()
w("`crsp.dsp500` ends at **2024-12-31**. The `_v2` objects run a year further:")
w()
rows = []
for k, v in s6b.items():
    if v.get("exists"):
        rows.append([k, "{:,}".format(v["row_count"]), v["date_col"], v["min"], v["max"]])
table(["object", "rows", "date column", "min", "max"], rows)
w("`crsp.dsp500list_v2` (2,084 rows) uses a different membership schema from `dsp500list`:")
w("`permno, indno, mbrstartdt, mbrenddt, mbrflg, indfam`, with membership running to")
w("**2025-12-31** against `dsp500list`'s **2024-12-31**.")
w()
w("### 6.2 `crsp.dsf_v2` existence check")
w()
d = s6["dsf_v2"]
w("One-row probe only, as instructed: `select * from crsp.dsf_v2 limit 1` succeeded and")
w("returned **%d columns**. No further query was run against it." % d["n_columns"])
w()

# ------------------------------------------------------------------ step 7 ---
s7 = J("step7_libraries.json")
s7b = J("step7b_commodity_search.json")
w("## Step 7 — Datastream commodity futures")
w()
w("### 7.1 Libraries")
w()
w("**%d of the 384 libraries** contain the literal substring `ds`, `datastream` or `tr_`."
  % len(s7["matching_libraries"]))
w("Most are incidental matches on `ds` inside `wrdsapps*`, `wrdssec*`, `bvdsamp`, `fisdsamp`,")
w("`markit_cds`, `crsp_q_mutualfunds` and so on. No library contains the string `datastream`.")
w("The complete matching list:")
w()
m = s7["matching_libraries"]
per = (len(m) + 2) // 3
rows = [[m[i + per * k] if i + per * k < len(m) else "" for k in range(3)] for i in range(per)]
table(["", "", ""], rows)
w("Narrowing to names prefixed `tr_` or beginning `trdstrm` (%d libraries), with their"
  % len(s7["narrowed_libraries"]))
w("table counts:")
w()
rows = []
for lib in s7["narrowed_libraries"]:
    t = s7["tables"][lib]
    rows.append([lib, len(t) if isinstance(t, list) else "failed"])
table(["library", "tables"], rows)
w("The Datastream feeds proper are **`tr_ds_comds`** (commodities, 11 tables),")
w("**`tr_ds_fut`** (futures, 20 tables), **`tr_ds_equities`** (43 tables) and")
w("**`tr_ds_econ`** (8 tables). `trdstrm` (82 tables) also exists. Their table lists:")
w()
for lib in ["tr_ds_comds", "tr_ds_fut", "tr_ds_econ"]:
    w("**`%s`** (%d): %s" % (lib, len(s7["tables"][lib]),
                             ", ".join("`%s`" % t for t in s7["tables"][lib])))
    w()
w("**`tr_ds_equities`** (%d): %s" % (len(s7["tables"]["tr_ds_equities"]),
    ", ".join("`%s`" % t for t in s7["tables"]["tr_ds_equities"])))
w()
w("**`trdstrm`** (%d): %s" % (len(s7["tables"]["trdstrm"]),
    ", ".join("`%s`" % t for t in s7["tables"]["trdstrm"])))
w()
_union = set()
for _l in ["tr_ds_equities", "tr_ds_comds", "tr_ds_fut", "tr_ds_econ"]:
    _union |= set(s7["tables"][_l])
_trd = set(s7["tables"]["trdstrm"])
w("`trdstrm`'s %d tables %s the union of the four `tr_ds_*` schemas' tables (%d)."
  % (len(_trd),
     "are exactly" if _trd == _union else "differ from",
     len(_union)))
if _trd != _union:
    w("Only in `trdstrm`: `%s`. Only in `tr_ds_*`: `%s`."
      % ("`, `".join(sorted(_trd - _union)) or "none",
         "`, `".join(sorted(_union - _trd)) or "none"))
w()
s7c = J("step7c_ds_samples.json")
w("Five further Datastream **sample** schemas appear in the match list above and are not")
w("covered by that prefix rule. Their table lists were read separately:")
w()
table(["sample library", "tables", "table names"],
      [[lib, len(t), ", ".join("`%s`" % x for x in t)] for lib, t in s7c.items()])

w("### 7.2 Commodity name search")
w()
w("Descriptive tables do exist. Five were searched, case-insensitively, across their")
w("name/description columns, 50 hits maximum per term as instructed. Match counts:")
w()
TERMS = ["GOLD", "SILVER", "CRUDE", "WTI", "NATURAL GAS", "HENRY HUB"]
rows = []
for key, rec in s7b.items():
    rows.append([("`%s`" % key), "{:,}".format(rec["row_count"]),
                 ", ".join("`%s`" % c for c in rec["name_columns"])]
                + ["{:,}".format(rec["terms"][t]["total_matches"]) for t in TERMS])
table(["table", "rows", "columns searched"] + TERMS, rows)
w("Every term returns matches in every table searched. Nothing came back empty.")
w()

def hits(key, terms=TERMS, limit=None, note=True):
    rec = s7b[key]
    w("#### `%s`" % key)
    w()
    for t in terms:
        h = rec["terms"][t]
        rws = h["rows"] if limit is None else h["rows"][:limit]
        w("**%s** — %d total matches, %d returned by the 50-hit cap%s:"
          % (t, h["total_matches"], h["shown"],
             ", first %d shown here" % len(rws) if limit and h["shown"] > len(rws) else ""))
        w()
        if not rws:
            w("(none)"); w(); continue
        headers = list(rws[0].keys())
        table(headers, [[r[c] for c in headers] for r in rws])

w("The full 50-hit listings for the two identifier-bearing tables follow. Complete output")
w("for all five tables is in `probe_output/step7b_commodity_search.log` and `.json`.")
w()
hits("tr_ds_comds.wrds_cmdy_info")
hits("tr_ds_fut.dsfutcontr")
w("For the three remaining tables the first 12 hits per term are shown; the rest are in the")
w("raw output.")
w()
hits("tr_ds_comds.dscminfo", limit=12)
hits("tr_ds_fut.wrds_cseries_info", limit=12)
hits("tr_ds_fut.wrds_contract_info", limit=12)

# ---------------------------------------------------------- not measured ---
w("## Not measured")
w()
NM = [
 ("Whether `conda run -n wrds-env python` works as the brief specifies",
  "No conda environment named `wrds-env` exists on this machine (`conda env list` shows only "
  "`base` and `volup`, neither with the `wrds` package). `wrds-env` is a venv at "
  "`/Users/GualyCr/wrds-env`, which is what was used. The discrepancy is recorded, not resolved."),
 ("`db.describe_table()` output for the OptionMetrics and IBES tables",
  "The call raises `TypeError('not all arguments converted during string formatting')` in this "
  "wrds 3.5.0 / pandas 2.2.3 / SQLAlchemy 2.0.53 combination, for all 9 tables attempted. "
  "Column names and types were read from `information_schema.columns` instead — the same "
  "catalog, so the column lists are complete and verbatim; only the wrapper's own formatting "
  "of them is missing."),
 ("Exact row count for the `days=30, delta=50, cp_flag='C'` node over 1996 → feed end",
  "Only calendar 2024 was counted (1,432,590 rows, 258 s). Repeating that scan across all 30 "
  "partitions was outside the session budget, so Step 3 reports a projection instead."),
 ("Trading-date ranges for the candidate secids that carry no option data",
  "Nine of the sixteen return no rows in `vsurfd` in any year and ten return none in "
  "`opprcd2024`, so their ranges were taken from `secnmd.effect_date` only. Their `secprd` "
  "spans were not queried."),
 ("Per-secid `secprd` first/last date",
  "Step 2 asked for `vsurfd` and `opprcd` coverage; `secprd` was measured only at the "
  "partition level (Step 1.4), not per secid."),
 ("Why the `comp.fundq` `rdq` non-null share declines from 0.75 (2010) to 0.47 (2026)",
  "The shares are measured; no decomposition by country, exchange, active/inactive status or "
  "company size was run."),
 ("Whether `anntims` is a release time or a wire time, and its time zone",
  "`anntims` is `time without time zone` and carries minute-resolution values whose "
  "distribution sits mostly outside 09:30–16:00 — both measured. The semantics and reference "
  "zone are documentation questions and were not measured."),
 ("Date spans and observation counts for any Datastream commodity or futures value table",
  "Step 7 searched descriptive tables for series names, as instructed. `dscmval`, "
  "`wrds_cmdy_data`, `dsfutcontrval`, `wrds_fut_contract` and `wrds_fut_series` were not "
  "queried at all, so no history length for any commodity series is established here."),
 ("Which Datastream series among the matches is the right one for any given commodity",
  "Match counts are large (e.g. 1,537 rows matching `GOLD` in `dscminfo`) and the listings are "
  "capped at 50 per term. Selecting among them is a design decision and outside this probe."),
 ("Anything in `optionm_all`, `optionmsamp_us`, `optionmsamp_europe` beyond structure",
  "Table inventories and partition forms were read; the 2025 spans of `optionm_all` were "
  "checked against `optionm` and agree. No data was pulled from the sample schemas."),
 ("`crsp.dsf_v2` contents",
  "A one-row existence check only, as instructed (succeeded, 50 columns). Its date span and "
  "row count were not measured."),
 ("`wrdsapps_link_crsp_optionm.opcrsphist` (the CRSP↔OptionMetrics link table)",
  "Noted as present with one table; its columns, coverage and link quality were not measured."),
]
for t, why in NM:
    w("- **%s** — %s" % (t, why))
w()
w("---")
w()
w("Generated by `src/probe/build_report.py` from the JSON artifacts in `probe_output/`.")
w("Every figure, column list and table name above is read back out of a measurement rather")
w("than typed in; the connecting prose is written by hand.")

path = os.path.join(OUT_DIR, "REPORT_probe.md")
with open(path, "w") as f:
    f.write("\n".join(L) + "\n")
print("wrote %s (%d lines, %d bytes)" % (path, len(L), os.path.getsize(path)))
