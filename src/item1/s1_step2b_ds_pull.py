"""Step 2b: pull the available first-nearby legs and measure coverage.

The step-2 rule selected NO pair for any of the four commodities (R6), so strictly
there is nothing to pull. This script is an ADDITION beyond the rule, done because the
step-7 kill check has to report a coverage share per commodity and because the report
should say what IS on the server, not only what is missing.

Addition rule, applied uniformly and logged: for each commodity take the PRINCIPAL
contract - the standard-size contract on the named exchange, fixed here as

    CL  ^NYM-LIGHT CRUDE OIL     NG  ^NYM-NATURAL GAS
    GC  ^NYL-GOLD 100 OZ         SI  ^NYL-SILVER 5000 OZ

- and among the rows the step-2 rule classified FIRST on that contract, take the one
with the lowest roll digit, preferring a 'CS' mnemonic over a 'C.' mnemonic on a tie.
No second leg is pulled because none exists.
"""
import os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import (connect, log_to, dump_json, load_json, dpath,
                          COMMON_START, COMMON_END, SECIDS)
import pandas as pd
pd.set_option("display.width", 300); pd.set_option("display.max_rows", 200)

log_to("s1_step2b_ds_pull.log")
db = connect()
step2 = load_json("s1_step2_ds_series.json")

PRINCIPAL = {"CL": r"^NYM-LIGHT CRUDE OIL", "NG": r"^NYM-NATURAL GAS",
             "GC": r"^NYL-GOLD 100 OZ",     "SI": r"^NYL-SILVER 5000 OZ"}
SUFFIX = re.compile(r"(?:CS|C\.)([0-9])([0-9])$")

# ---------------------------------------------- SPX trade dates, common window ---
t0 = time.time()
frames = []
for yr in range(2008, 2026):
    frames.append(db.raw_sql(
        "select date from optionm.secprd%d where secid = %%(s)s "
        "and date between %%(a)s and %%(b)s" % yr,
        params={"s": float(SECIDS["SPX"]), "a": COMMON_START, "b": COMMON_END}))
spx = pd.concat(frames, ignore_index=True)
spx["date"] = pd.to_datetime(spx["date"])
spx_dates = set(spx.date)
print("SPX (secid %d) trade dates in optionm.secprd over %s..%s : %d  (%.1f s)"
      % (SECIDS["SPX"], COMMON_START, COMMON_END, len(spx_dates), time.time() - t0))

out = {"spx_trade_dates_common_window": len(spx_dates), "series": {}}

for code, pat in PRINCIPAL.items():
    firsts = [r for r in step2["selection"][code]["first_leg_rows"]
              if re.match(pat, r["calcseriesname"] or "")]
    print("\n\n########## %s : principal contract %s ##########" % (code, pat))
    if not firsts:
        print("no FIRST-classified row on the principal contract; nothing pulled")
        out["series"][code] = {"pulled": False,
                               "reason": "no FIRST-classified row matching %s" % pat}
        continue
    for r in firsts:
        m = SUFFIX.search(r["dsmnem"]); r["_roll_digit"] = int(m.group(2)) if m else 99
        r["_prefer_cs"] = 0 if "CS" in r["dsmnem"] else 1
    firsts.sort(key=lambda r: (r["_roll_digit"], r["_prefer_cs"], r["calcseriescode"]))
    print("FIRST-classified rows on the principal contract, in rule order:")
    print(pd.DataFrame(firsts)[["dsmnem", "calcseriesname", "calcseriescode", "clscode",
                                "rollmethodcode", "rollmethoddesc", "positionfwddesc"]]
          .to_string(index=False))
    pick = firsts[0]
    print("\nPICKED: %s (%s), calcseriescode %s"
          % (pick["dsmnem"], pick["calcseriesname"], pick["calcseriescode"]))

    # roll convention from metadata, not from the price series
    info = db.raw_sql("""select calcseriescode, clscode, dsmnem, calcseriesname, isocurrcode,
                                rollmethodcode, positionfwdcode, calcmthcode
                         from tr_ds_fut.dsfutcalcserinfo where calcseriescode = %(c)s""",
                      params={"c": pick["calcseriescode"]})
    mth = db.raw_sql("select calcseriescode, mthnum from tr_ds_fut.dsfutcalcsermth "
                     "where calcseriescode = %(c)s order by mthnum",
                     params={"c": pick["calcseriescode"]})
    print("\ndsfutcalcserinfo row:"); print(info.to_string(index=False))
    print("dsfutcalcsermth rows: %d %s"
          % (len(mth), sorted(mth.mthnum.tolist()) if len(mth) else "(none)"))

    t0 = time.time()
    v = db.raw_sql("""select date_ as date, open_, high, low, volume, settlement, openinterest
                      from tr_ds_fut.dsfutcalcserval
                      where calcseriescode = %(c)s order by date_""",
                   params={"c": pick["calcseriescode"]})
    el = time.time() - t0
    v["date"] = pd.to_datetime(v["date"])
    fn = dpath("ds_%s_first.parquet" % code.lower())
    v.to_parquet(fn, index=False)

    inwin = v[(v.date >= pd.Timestamp(COMMON_START)) & (v.date <= pd.Timestamp(COMMON_END))]
    matched = inwin[inwin.date.isin(spx_dates)]
    nn = inwin[inwin.settlement.notna()]
    nn_matched = nn[nn.date.isin(spx_dates)]
    cov = len(matched) / len(spx_dates)
    cov_nn = len(nn_matched) / len(spx_dates)
    print("\npull wall clock %.2f s -> %s" % (el, os.path.basename(fn)))
    print("first date      : %s" % v.date.min().date())
    print("last  date      : %s" % v.date.max().date())
    print("row count       : %d" % len(v))
    print("dates in common window        : %d" % len(inwin))
    print("of those matching an SPX trade date : %d" % len(matched))
    print("COVERAGE SHARE (matched / %d SPX trade dates) : %.4f" % (len(spx_dates), cov))
    print("settlement non-null in window : %d ; matched & non-null : %d ; share %.4f"
          % (len(nn), len(nn_matched), cov_nn))

    out["series"][code] = {
        "pulled": True, "principal_pattern": pat,
        "dsmnem": pick["dsmnem"], "calcseriesname": pick["calcseriesname"],
        "calcseriescode": pick["calcseriescode"], "clscode": pick["clscode"],
        "rollmethodcode": pick["rollmethodcode"], "rollmethoddesc": pick["rollmethoddesc"],
        "positionfwddesc": pick["positionfwddesc"],
        "mnemonic_suffix_position_digit": SUFFIX.search(pick["dsmnem"]).group(1),
        "mnemonic_suffix_roll_digit": SUFFIX.search(pick["dsmnem"]).group(2),
        "dsfutcalcserinfo": info.to_dict("records"),
        "dsfutcalcsermth_n": len(mth),
        "dsfutcalcsermth": mth.mthnum.tolist() if len(mth) else [],
        "pull_seconds": round(el, 2), "file": os.path.basename(fn),
        "first_date": str(v.date.min().date()), "last_date": str(v.date.max().date()),
        "row_count": len(v),
        "dates_in_common_window": len(inwin),
        "matched_spx_trade_dates": len(matched),
        "coverage_share": round(cov, 4),
        "settlement_nonnull_in_window": len(nn),
        "matched_and_nonnull": len(nn_matched),
        "coverage_share_nonnull": round(cov_nn, 4),
        "second_leg": None,
        "second_leg_note": "no second-nearby continuous series exists on this contract",
    }

dump_json("s1_step2b_ds_pull.json", out)
db.close()
