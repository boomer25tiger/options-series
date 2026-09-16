"""Model-free implied variance, spec section 6.1, steps 1 to 6.

One function, `mfiv_one_date`, takes one date's quote set for one secid and returns
model-free variance at each requested node, or a drop code naming the step that
dropped it.

Implementation choices that section 6.1 does not pin down are marked CHOICE and are
listed in the session report:

CHOICE 1  Expiry identity is (exdate, am_settlement), not exdate alone. SPX carries an
          AM-settled and a PM-settled chain on the same third-Friday exdate; treating
          them as one expiry would put two quotes on every strike. When two chains
          share a dte the one with more rows is used.
CHOICE 2  Residual duplicate rows on (exdate, am_settlement, cp_flag, strike) - which
          occur on the ETFs after share splits, where an adjusted-deliverable chain
          shares the exdate - are collapsed to the row with the largest open_interest,
          then largest volume, then highest best_bid.
CHOICE 3  A quote is usable when best_bid > 0 and best_offer >= best_bid. Section 6.1
          excludes zero-bid options; the best_offer condition additionally drops
          crossed quotes.
CHOICE 4  Q(K0) is the average of the K0 call and put midquotes when both are usable,
          and the single usable one when only one is. Section 6.1 says "the average of
          put and call at K0" and does not say what to do when one leg is missing.
CHOICE 5  "Two consecutive zero-bid strikes" is counted along the rows that exist for
          that side, so a strike with no quoted option at all neither contributes to
          the run nor breaks it.
CHOICE 6  n_strikes_*_put and n_strikes_*_call count strikes strictly below and
          strictly above K0; K0 itself is counted on neither side. The step-6 floor of
          3 is applied to those two counts.
"""
import numpy as np
import pandas as pd

DROP_OK = "OK"
DROP_NO_QUOTES = "NO_QUOTES"
DROP_NO_RATE = "NO_RATE"
DROP_NO_BRACKET = "NO_BRACKET"
DROP_NO_FORWARD_LOW = "NO_FORWARD_LOW"
DROP_NO_FORWARD_HIGH = "NO_FORWARD_HIGH"
DROP_NO_K0_LOW = "NO_K0_LOW"
DROP_NO_K0_HIGH = "NO_K0_HIGH"
DROP_FEW_STRIKES_LOW = "FEW_STRIKES_LOW"
DROP_FEW_STRIKES_HIGH = "FEW_STRIKES_HIGH"
DROP_BAD_VARIANCE = "BAD_VARIANCE"

MIN_DTE = 7          # spec 6.1 step 1
MIN_STRIKES_SIDE = 3  # spec 6.1 step 6
DAYS_YEAR = 365.0     # spec 6.1 step 5


def interp_rate(zdays, zrates, dte):
    """Zero rate in decimal for `dte` calendar days, linear in days (spec 6.1 step 2)."""
    return float(np.interp(dte, zdays, zrates)) / 100.0


def _usable(bid, offer):
    return (bid > 0) & (offer >= bid)


def _sweep(strikes, bids, offers, outward_desc):
    """Return (kept_strikes, kept_mid) for one side.

    Walks outward from K0 along the rows that exist on this side, drops zero-bid
    strikes, and stops after two consecutive zero-bid strikes (CHOICE 5).
    """
    order = np.argsort(strikes)
    if outward_desc:
        order = order[::-1]
    k, b, o = strikes[order], bids[order], offers[order]
    keep_k, keep_m, run = [], [], 0
    for i in range(len(k)):
        if b[i] > 0 and o[i] >= b[i]:
            run = 0
            keep_k.append(k[i]); keep_m.append(0.5 * (b[i] + o[i]))
        else:
            run += 1
            if run >= 2:
                break
    return np.array(keep_k, float), np.array(keep_m, float)


def expiry_variance(sub, T, r):
    """Spec 6.1 steps 2, 3, 4 for one expiry.

    `sub` has columns cp_flag, strike_price, best_bid, best_offer, forward_price.
    Returns (sigma2, F, K0, n_put, n_call, drop) with drop None on success.
    """
    calls = sub[sub.cp_flag == "C"]
    puts = sub[sub.cp_flag == "P"]
    if len(calls) == 0 or len(puts) == 0:
        return None, None, None, 0, 0, "NO_FORWARD"

    # ---- step 2: forward ----
    fwd = sub["forward_price"].dropna()
    if len(fwd):
        F = float(fwd.iloc[0])
    else:
        c = calls[_usable(calls.best_bid, calls.best_offer)][["strike_price", "best_bid", "best_offer"]]
        p = puts[_usable(puts.best_bid, puts.best_offer)][["strike_price", "best_bid", "best_offer"]]
        m = c.merge(p, on="strike_price", suffixes=("_c", "_p"))
        if not len(m):
            return None, None, None, 0, 0, "NO_FORWARD"
        cm = 0.5 * (m.best_bid_c + m.best_offer_c)
        pm = 0.5 * (m.best_bid_p + m.best_offer_p)
        j = int(np.argmin(np.abs((cm - pm).values)))
        K = float(m.strike_price.values[j])
        F = K + np.exp(r * T) * float(cm.values[j] - pm.values[j])

    # ---- step 3: K0 and the OTM ladder ----
    all_k = np.unique(sub.strike_price.values)
    below = all_k[all_k <= F]
    if not len(below):
        return None, F, None, 0, 0, "NO_K0"
    K0 = float(below.max())

    pl = puts[puts.strike_price < K0]
    cl = calls[calls.strike_price > K0]
    kp, mp = _sweep(pl.strike_price.values, pl.best_bid.values, pl.best_offer.values, True)
    kc, mc = _sweep(cl.strike_price.values, cl.best_bid.values, cl.best_offer.values, False)

    c0 = calls[calls.strike_price == K0]
    p0 = puts[puts.strike_price == K0]
    q0 = []
    for leg in (c0, p0):
        if len(leg):
            b, o = float(leg.best_bid.iloc[0]), float(leg.best_offer.iloc[0])
            if b > 0 and o >= b:
                q0.append(0.5 * (b + o))
    if not q0:
        return None, F, K0, len(kp), len(kc), "NO_K0"
    Q0 = float(np.mean(q0))  # CHOICE 4

    # ---- step 4: the sum ----
    K = np.concatenate([kp[::-1], [K0], kc])
    Q = np.concatenate([mp[::-1], [Q0], mc])
    o = np.argsort(K)
    K, Q = K[o], Q[o]
    if len(K) < 2:
        return None, F, K0, len(kp), len(kc), "NO_K0"
    dK = np.empty_like(K)
    dK[1:-1] = (K[2:] - K[:-2]) / 2.0
    dK[0] = K[1] - K[0]
    dK[-1] = K[-1] - K[-2]

    sigma2 = (2.0 / T) * np.sum(dK / K**2 * np.exp(r * T) * Q) - (1.0 / T) * (F / K0 - 1.0) ** 2
    return float(sigma2), float(F), float(K0), int(len(kp)), int(len(kc)), None


def mfiv_one_date(date, quotes, zdays, zrates, nodes=(30, 91),
                  min_strikes=MIN_STRIKES_SIDE):
    """Spec 6.1 for one secid and one date. Returns {node: record}.

    `min_strikes` is the section 6.1 step-6 floor. It defaults to the spec value of
    3 and is exposed only so amendment A3(b) can run the floor-of-2 robustness
    series. No other behaviour changes with it.
    """
    blank = {"mfiv": np.nan, "expiry_low": pd.NaT, "expiry_high": pd.NaT,
             "n_strikes_low_put": 0, "n_strikes_low_call": 0,
             "n_strikes_high_put": 0, "n_strikes_high_call": 0}

    if quotes is None or not len(quotes):
        return {d: dict(blank, drop_code=DROP_NO_QUOTES) for d in nodes}
    if zdays is None or not len(zdays):
        return {d: dict(blank, drop_code=DROP_NO_RATE) for d in nodes}

    q = quotes
    # CHOICE 2: collapse residual duplicates
    if q.duplicated(["exdate", "am_settlement", "cp_flag", "strike_price"]).any():
        q = (q.sort_values(["open_interest", "volume", "best_bid"],
                           ascending=False, na_position="last")
               .drop_duplicates(["exdate", "am_settlement", "cp_flag", "strike_price"]))

    q = q.assign(dte=(q.exdate - date).dt.days)
    q = q[q.dte >= MIN_DTE]
    if not len(q):
        return {d: dict(blank, drop_code=DROP_NO_BRACKET) for d in nodes}

    # CHOICE 1: expiry identity, with the larger chain winning a dte tie
    grp = (q.groupby(["exdate", "am_settlement"], dropna=False)
             .agg(dte=("dte", "first"), n=("strike_price", "size")).reset_index())
    grp = grp.sort_values(["dte", "n"], ascending=[True, False]).drop_duplicates("dte")

    cache = {}

    def variance_for(row):
        key = (row.exdate, row.am_settlement)
        if key not in cache:
            sub = q[(q.exdate == row.exdate) & (q.am_settlement.eq(row.am_settlement)
                                                | (q.am_settlement.isna() & pd.isna(row.am_settlement)))]
            T = row.dte / DAYS_YEAR
            r = interp_rate(zdays, zrates, row.dte)
            cache[key] = expiry_variance(sub, T, r) + (T,)
        return cache[key]

    out = {}
    for d in nodes:
        lo = grp[grp.dte <= d]
        hi = grp[grp.dte > d]
        if not len(lo) or not len(hi):
            out[d] = dict(blank, drop_code=DROP_NO_BRACKET)
            continue
        rlo = lo.iloc[lo.dte.values.argmax()]
        rhi = hi.iloc[hi.dte.values.argmin()]

        s2lo, Flo, K0lo, nplo, nclo, dlo, Tlo = variance_for(rlo)
        s2hi, Fhi, K0hi, nphi, nchi, dhi, Thi = variance_for(rhi)

        rec = {"mfiv": np.nan, "expiry_low": rlo.exdate, "expiry_high": rhi.exdate,
               "n_strikes_low_put": nplo, "n_strikes_low_call": nclo,
               "n_strikes_high_put": nphi, "n_strikes_high_call": nchi}

        if dlo == "NO_FORWARD":
            out[d] = dict(rec, drop_code=DROP_NO_FORWARD_LOW); continue
        if dlo == "NO_K0":
            out[d] = dict(rec, drop_code=DROP_NO_K0_LOW); continue
        if dhi == "NO_FORWARD":
            out[d] = dict(rec, drop_code=DROP_NO_FORWARD_HIGH); continue
        if dhi == "NO_K0":
            out[d] = dict(rec, drop_code=DROP_NO_K0_HIGH); continue
        # ---- step 6 ----
        if nplo < min_strikes or nclo < min_strikes:
            out[d] = dict(rec, drop_code=DROP_FEW_STRIKES_LOW); continue
        if nphi < min_strikes or nchi < min_strikes:
            out[d] = dict(rec, drop_code=DROP_FEW_STRIKES_HIGH); continue
        # ---- step 5 ----
        Td = d / DAYS_YEAR
        if Thi <= Tlo:
            out[d] = dict(rec, drop_code=DROP_NO_BRACKET); continue
        w = (Thi - Td) / (Thi - Tlo)
        tv = w * s2lo * Tlo + (1.0 - w) * s2hi * Thi
        mfiv = tv / Td
        if not np.isfinite(mfiv) or mfiv <= 0:
            out[d] = dict(rec, drop_code=DROP_BAD_VARIANCE); continue
        out[d] = dict(rec, mfiv=float(mfiv), drop_code=DROP_OK)
    return out
