"""Self-test for the section 6.1 estimator against a synthetic Black-Scholes chain.

If the implementation of steps 2 to 5 is right, feeding it a chain priced off a known
constant volatility must return that volatility back, up to discretisation error. This
checks the construction independently of VIX, before any real quote is touched.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from math import log, sqrt, exp, erf
from item1.mfiv import mfiv_one_date, expiry_variance, DAYS_YEAR


def _N(x):
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def bs(S, K, T, r, sig, cp):
    d1 = (log(S / K) + (r + 0.5 * sig * sig) * T) / (sig * sqrt(T))
    d2 = d1 - sig * sqrt(T)
    if cp == "C":
        return S * _N(d1) - K * exp(-r * T) * _N(d2)
    return K * exp(-r * T) * _N(-d2) - S * _N(-d1)


def chain(date, S, r, sig, dtes, strikes):
    rows = []
    for dte in dtes:
        T = dte / DAYS_YEAR
        ex = date + pd.to_timedelta(int(dte), unit="D")
        for K in strikes:
            for cp in ("C", "P"):
                px = bs(S, K, T, r, sig, cp)
                rows.append({"exdate": ex, "cp_flag": cp, "strike_price": float(K),
                             "best_bid": max(px - 0.005, 0.0), "best_offer": px + 0.005,
                             "forward_price": np.nan, "am_settlement": 0.0,
                             "volume": 1.0, "open_interest": 1.0})
    return pd.DataFrame(rows)


def main():
    date = pd.Timestamp("2015-06-15")
    S, r, sig = 100.0, 0.02, 0.25
    zdays = np.array([1.0, 30.0, 91.0, 365.0, 3669.0])
    zrates = np.full(5, r * 100.0)
    strikes = np.arange(40.0, 200.5, 1.0)
    fails = 0

    print("=== A. flat-vol chain, sigma = %.2f, target recovery of sigma^2 = %.6f ==="
          % (sig, sig * sig))
    q = chain(date, S, r, sig, [21, 49, 80, 110], strikes)
    res = mfiv_one_date(date, q, zdays, zrates, nodes=(30, 91))
    for node in (30, 91):
        rec = res[node]
        got = rec["mfiv"]
        err = abs(sqrt(got) - sig) * 100
        ok = rec["drop_code"] == "OK" and err < 0.10
        fails += (not ok)
        print("  node %2d: drop=%s mfiv=%.8f  implied vol=%.6f  error=%.4f vol points  %s"
              % (node, rec["drop_code"], got, sqrt(got), err, "PASS" if ok else "FAIL"))

    print("\n=== B. single expiry, exact BS variance at several vols ===")
    for s in (0.10, 0.25, 0.60):
        dte = 30
        T = dte / DAYS_YEAR
        sub = chain(date, S, r, s, [dte], np.arange(20.0, 400.5, 0.5))
        sub = sub[sub.exdate == date + pd.to_timedelta(int(dte), unit="D")]
        s2, F, K0, npu, nca, drop = expiry_variance(sub, T, r)
        err = abs(sqrt(s2) - s) * 100
        ok = drop is None and err < 0.10
        fails += (not ok)
        print("  sigma=%.2f -> sigma_hat=%.6f  F=%.4f (true fwd %.4f)  K0=%.1f  "
              "puts=%d calls=%d  error=%.4f vol points  %s"
              % (s, sqrt(s2), F, S * exp(r * T), K0, npu, nca, err, "PASS" if ok else "FAIL"))

    print("\n=== C. drop codes fire where section 6.1 says they should ===")
    cases = []
    # too few strikes on a side
    thin = chain(date, S, r, sig, [21, 49], np.array([98.0, 99.0, 100.0, 101.0]))
    cases.append(("thin ladder -> FEW_STRIKES",
                  mfiv_one_date(date, thin, zdays, zrates, (30,))[30]["drop_code"],
                  ("FEW_STRIKES_LOW", "FEW_STRIKES_HIGH")))
    # no expiry above the node
    short = chain(date, S, r, sig, [10, 20], strikes)
    cases.append(("no expiry above node -> NO_BRACKET",
                  mfiv_one_date(date, short, zdays, zrates, (30,))[30]["drop_code"],
                  ("NO_BRACKET",)))
    # every expiry inside the 7-day floor
    near = chain(date, S, r, sig, [2, 5], strikes)
    cases.append(("all expiries under the 7-day floor -> NO_BRACKET",
                  mfiv_one_date(date, near, zdays, zrates, (30,))[30]["drop_code"],
                  ("NO_BRACKET",)))
    cases.append(("empty quote set -> NO_QUOTES",
                  mfiv_one_date(date, pd.DataFrame(), zdays, zrates, (30,))[30]["drop_code"],
                  ("NO_QUOTES",)))
    for label, got, want in cases:
        ok = got in want
        fails += (not ok)
        print("  %-52s got %-18s %s" % (label, got, "PASS" if ok else "FAIL want %s" % (want,)))

    print("\n=== D. the zero-bid sweep stops after two consecutive zero-bid strikes ===")
    # a chain whose quotes are all usable, so the only truncation is the injected one
    q2 = chain(date, S, r, sig, [21, 49], strikes).copy()
    q2["best_bid"] = np.maximum(q2["best_bid"], 0.01)
    q2["best_offer"] = q2["best_bid"] + 0.01
    base = mfiv_one_date(date, q2, zdays, zrates, (30,))[30]
    K0 = 100.0
    q3 = q2.copy()
    hit = (q3.cp_flag == "P") & (q3.strike_price.isin([97.0, 96.0]))
    q3.loc[hit, "best_bid"] = 0.0
    r3 = mfiv_one_date(date, q3, zdays, zrates, (30,))[30]
    # sweeping down from K0=100: 99 and 98 are usable, 97 and 96 are zero-bid -> stop.
    # Two surviving puts is below the step-6 floor of 3, so the date must ALSO drop.
    ok = r3["drop_code"] == "FEW_STRIKES_LOW" and r3["n_strikes_low_put"] == 2
    fails += (not ok)
    print("  full ladder puts below K0=%.0f : %d" % (K0, base["n_strikes_low_put"]))
    print("  zero-bid at 97 and 96 -> puts kept %d (expected 2), drop=%s (expected "
          "FEW_STRIKES_LOW, the step-6 floor)  %s"
          % (r3["n_strikes_low_put"], r3["drop_code"], "PASS" if ok else "FAIL"))

    # the same truncation further out leaves enough strikes, so the date survives
    q5 = q2.copy()
    q5.loc[(q5.cp_flag == "P") & (q5.strike_price.isin([90.0, 89.0])), "best_bid"] = 0.0
    r5 = mfiv_one_date(date, q5, zdays, zrates, (30,))[30]
    ok5 = r5["drop_code"] == "OK" and r5["n_strikes_low_put"] == 9
    fails += (not ok5)
    print("  zero-bid at 90 and 89 -> puts kept %d (expected 9, strikes 99..91), drop=%s  %s"
          % (r5["n_strikes_low_put"], r5["drop_code"], "PASS" if ok5 else "FAIL"))

    # one zero-bid strike alone must NOT stop the sweep
    q4 = q2.copy()
    q4.loc[(q4.cp_flag == "P") & (q4.strike_price == 97.0), "best_bid"] = 0.0
    r4 = mfiv_one_date(date, q4, zdays, zrates, (30,))[30]
    ok2 = r4["n_strikes_low_put"] == base["n_strikes_low_put"] - 1
    fails += (not ok2)
    print("  a single zero-bid strike only drops that strike : %d (expected %d)  %s"
          % (r4["n_strikes_low_put"], base["n_strikes_low_put"] - 1, "PASS" if ok2 else "FAIL"))

    print("\n%s  (%d failing checks)" % ("ALL CHECKS PASS" if fails == 0 else "FAILURES", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
