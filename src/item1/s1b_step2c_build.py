"""Step 2c: run the section 6.1 construction, with or without the A1 filter, at a
chosen strike floor.

The estimator in mfiv.py is unchanged apart from the floor being a parameter (A3b).
A1 is applied here, as a filter on the quote set before the estimator sees it.
A4: the open-interest duplicate collapse inside mfiv.py is retained as the fallback;
duplicates surviving the A1 filter are counted here and reported.

usage: s1b_step2c_build.py --out NAME [--nofilter] [--floor N]
"""
import os, sys, time, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath, SECIDS, PULL_SPAN, NODES
from item1.mfiv import mfiv_one_date
import numpy as np
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)

# A1 encoding, read from the data in step 2b and recorded here.
SS_FLAG_STANDARD = "0"
CONTRACT_SIZE_STANDARD = 100.0


def a1_filter(q):
    """A1: only standard-settlement contracts enter the strike set."""
    return q[(q.ss_flag == SS_FLAG_STANDARD) & (q.contract_size == CONTRACT_SIZE_STANDARD)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--nofilter", action="store_true")
    ap.add_argument("--floor", type=int, default=3)
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    log_to(args.log or ("s1b_build_%s.log" % args.out.replace(".parquet", "")))
    print("output          : %s" % args.out)
    print("A1 filter       : %s" % ("OFF" if args.nofilter else
                                    "ON (ss_flag == %r and contract_size == %g)"
                                    % (SS_FLAG_STANDARD, CONTRACT_SIZE_STANDARD)))
    print("strike floor    : %d" % args.floor)

    z = pd.read_parquet(dpath("zerocd.parquet"))
    z["date"] = pd.to_datetime(z["date"])
    zg = {d: (g.days.values.astype(float), g.rate.values.astype(float))
          for d, g in z.sort_values(["date", "days"]).groupby("date")}
    zdates = np.array(sorted(zg))

    def rate_curve(d):
        if d in zg:
            return zg[d], False
        i = np.searchsorted(zdates, d) - 1
        return (zg[zdates[i]], True) if i >= 0 else ((None, None), True)

    rows, timing = [], []
    n_fallback = n_dupe_dates = n_dupe_rows = 0
    rows_before = rows_after = 0
    t_all = time.time()

    for tic in ["SPX", "GLD", "SLV", "USO", "UNG"]:
        sid = SECIDS[tic]
        a, b = PULL_SPAN[tic]
        for yr in range(int(a[:4]), int(b[:4]) + 1):
            fn = dpath("opprcd_%s_%d.parquet" % (tic, yr))
            if not os.path.exists(fn):
                print("%-4s %d  NOT PULLED, skipped" % (tic, yr)); continue
            t0 = time.time()
            df = pd.read_parquet(fn)
            rows_before += len(df)
            if not args.nofilter:
                df = a1_filter(df)
            rows_after += len(df)
            ndates = 0
            for d, q in df.groupby("date", sort=True):
                ndates += 1
                dup = q.duplicated(["exdate", "am_settlement", "cp_flag", "strike_price"],
                                   keep=False)
                if dup.any():
                    n_dupe_dates += 1
                    n_dupe_rows += int(dup.sum())
                (zd, zr), fell = rate_curve(d)
                n_fallback += fell
                res = mfiv_one_date(d, q, zd, zr, nodes=NODES, min_strikes=args.floor)
                for node, rec in res.items():
                    rows.append({"secid": sid, "ticker": tic, "date": d, "node": node,
                                 "mfiv": rec["mfiv"],
                                 "expiry_low": rec["expiry_low"],
                                 "expiry_high": rec["expiry_high"],
                                 "n_strikes_low_put": rec["n_strikes_low_put"],
                                 "n_strikes_low_call": rec["n_strikes_low_call"],
                                 "n_strikes_high_put": rec["n_strikes_high_put"],
                                 "n_strikes_high_call": rec["n_strikes_high_call"],
                                 "drop_code": rec["drop_code"]})
            el = time.time() - t0
            timing.append({"ticker": tic, "year": yr, "dates": ndates, "seconds": round(el, 2)})
            print("%-4s %d  dates=%4d  rows=%9d  %6.1f s" % (tic, yr, ndates, len(df), el))
            del df

    mf = pd.DataFrame(rows)
    mf["year"] = mf.date.dt.year
    total = time.time() - t_all
    print("\nconstruction wall clock: %.1f s (%.1f min), %d records"
          % (total, total / 60.0, len(mf)))
    print("quote rows before filter : %s" % "{:,}".format(rows_before))
    print("quote rows after  filter : %s  (kept %.4f)"
          % ("{:,}".format(rows_after), rows_after / max(rows_before, 1)))
    print("A4 fallback: secid-dates with duplicates surviving the filter : %d" % n_dupe_dates)
    print("A4 fallback: duplicate rows surviving the filter              : %d" % n_dupe_rows)
    print("zerocd nearest-earlier-date fallbacks                         : %d" % n_fallback)

    mf.to_parquet(dpath(args.out), index=False)
    print("wrote %s (%.1f MB)" % (dpath(args.out), os.path.getsize(dpath(args.out)) / 1e6))

    print("\n===== drop codes =====")
    print(mf.groupby(["ticker", "node", "drop_code"]).size().unstack(fill_value=0).to_string())
    print("\n===== retention =====")
    ret = (mf.assign(ok=(mf.drop_code == "OK")).groupby(["ticker", "node"])
             .agg(dates=("date", "size"), ok=("ok", "sum")))
    ret["share_ok"] = (ret.ok / ret.dates).round(4)
    print(ret.to_string())

    built = mf[mf.expiry_low.notna()]
    med = (built.groupby(["ticker", "node", "year"])[
        ["n_strikes_low_put", "n_strikes_low_call",
         "n_strikes_high_put", "n_strikes_high_call"]].median().astype(int))
    med["n_dates"] = built.groupby(["ticker", "node", "year"]).size()
    tag = args.out.replace(".parquet", "")
    med.reset_index().to_csv(opath("s1b_median_strikes_%s.csv" % tag), index=False)
    per = (mf[mf.drop_code != "OK"].groupby(["ticker", "node", "year", "drop_code"])
           .size().unstack(fill_value=0))
    per.reset_index().to_csv(opath("s1b_drops_%s.csv" % tag), index=False)
    print("\n===== median OTM strikes per side, per secid and node (whole span) =====")
    m2 = med.groupby(["ticker", "node"])[["n_strikes_low_put", "n_strikes_low_call",
                                          "n_strikes_high_put", "n_strikes_high_call"]].median()
    print(m2.to_string())

    dump_json("s1b_build_%s.json" % tag, {
        "out": args.out, "filter": not args.nofilter, "floor": args.floor,
        "seconds": round(total, 1), "records": len(mf),
        "rows_before_filter": rows_before, "rows_after_filter": rows_after,
        "dupe_dates_surviving": n_dupe_dates, "dupe_rows_surviving": n_dupe_rows,
        "zerocd_fallbacks": int(n_fallback),
        "retention": ret.reset_index().to_dict("records"),
        "drop_codes": mf.groupby(["ticker", "node", "drop_code"]).size()
                        .rename("n").reset_index().to_dict("records"),
        "median_strikes": m2.reset_index().to_dict("records"),
        "timing": timing,
    })


if __name__ == "__main__":
    main()
