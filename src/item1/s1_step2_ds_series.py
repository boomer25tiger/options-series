"""Step 2: Datastream continuous first/second nearby series for GC, SI, CL, NG.

SELECTION RULE - fixed here, applied uniformly to all four commodities, logged in full.

  R1  Selection pool. Continuous series in tr_ds_fut.wrds_cseries_info on the NAMED
      exchange for that commodity, operationalised as `calcseriesname` beginning with
      one of the three prefixes Datastream uses for the NYMEX/COMEX complex - 'NYM-',
      'CMX-', 'NYL-' - together with the commodity word ('CRUDE', 'NATURAL GAS',
      'GOLD', 'SILVER'). The 'NYL-' prefix is included because that is how Datastream
      names the continuous series of the 100-oz gold and 5000-oz silver contracts;
      without it the main metal contracts would be outside the pool. Series on other
      exchanges (ICE-, IPE-, CBT-, CME-, BFE-) are OUTSIDE the selection pool.
  R2  FIRST-nearby leg: the row's name marks it as the continuous front contract -
      it contains 'CONTINUOUS' or 'CONT.' or matches the Reuters continuation form
      'TRc<d>' with one digit - AND the position digit of its two-character mnemonic
      suffix is 0 (mnemonic ends 'CS0<r>' or 'C.0<r>').
  R3  SECOND-nearby leg: the row's name marks it as the continuous second contract -
      it contains '2ND' (Datastream writes 'CONT. 2ND FUT' / 'CONT. 2ND LTDT') or
      matches 'TRc2<d>' - AND the position digit of its mnemonic suffix is 2.
  R4  A pair qualifies only if the two legs carry the SAME roll-convention marker
      (identical trailing roll digit <r> in the mnemonic suffix) AND sit on the SAME
      contract class (`clscode`). The same-class clause is an explicit addition to the
      stated rule: without it a first leg on NYMEX natural gas would pair with a
      second leg on ICE natural gas.
  R5  If more than one pair qualifies, take the pair whose first leg has the earliest
      first date in tr_ds_fut.dsfutcalcserval.
  R6  If no pair qualifies for a commodity, record that and move on.

The mnemonic suffix is read as <position><roll>. That reading is VERIFIED against the
`positionfwdcode` and `rollmethodcode` metadata columns across the whole table rather
than assumed, and the verification is reported.

Four searches are reported per commodity. Only (A) feeds selection. (B), (C) and (D)
are evidence that a qualifying pair on the named contract has not been missed.
"""
import os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import connect, log_to, dump_json, cols_of
import pandas as pd
pd.set_option("display.width", 330); pd.set_option("display.max_rows", 700)
pd.set_option("display.max_colwidth", 48)

log_to("s1_step2_ds_series.log")
db = connect()
out = {}

TABLES = ["wrds_cseries_info", "dsfutcalcserinfo", "dsfutcalcserval",
          "dsfutcalcsermth", "wrds_fut_series"]
out["columns"] = {}
for t in TABLES:
    c = cols_of(db, "tr_ds_fut", t)
    print("\n===== tr_ds_fut.%s =====" % t)
    print(c.to_string(index=False))
    out["columns"]["tr_ds_fut." + t] = c.to_dict("records")

pos = db.raw_sql("""select positionfwdcode, positionfwddesc, count(*) as n
                    from tr_ds_fut.wrds_cseries_info group by 1,2 order by 1""")
roll = db.raw_sql("""select rollmethodcode, rollmethoddesc, count(*) as n
                     from tr_ds_fut.wrds_cseries_info group by 1,2 order by 1""")
print("\n===== positionfwdcode dictionary ====="); print(pos.to_string(index=False))
print("\n===== rollmethodcode dictionary ====="); print(roll.to_string(index=False))
out["positionfwd_dictionary"] = pos.to_dict("records")
out["rollmethod_dictionary"] = roll.to_dict("records")

SEL = ("calcseriescode, clscode, dsmnem, calcseriesname, rollmethodcode, rollmethoddesc, "
       "positionfwdcode, positionfwddesc, calcmthcode")
NYMEX_COMEX = ("(calcseriesname ilike 'NYM-%%' or calcseriesname ilike 'CMX-%%' "
               "or calcseriesname ilike 'NYL-%%')")
COMMODITIES = {
    "CL": {"label": "NYM crude light sweet", "ticker": "CL", "word": "%%CRUDE%%",
           "main": "%%LIGHT CRUDE%%"},
    "NG": {"label": "NYM natural gas", "ticker": "NG", "word": "%%NATURAL GAS%%",
           "main": "%%NATURAL GAS%%"},
    "GC": {"label": "CMX gold", "ticker": "GC", "word": "%%GOLD%%",
           "main": "%%GOLD 100%%"},
    "SI": {"label": "CMX silver", "ticker": "SI", "word": "%%SILVER%%",
           "main": "%%SILVER 5000%%"},
}

out["candidates"] = {}
for code, spec in COMMODITIES.items():
    where_a = "%s and calcseriesname ilike '%s'" % (NYMEX_COMEX, spec["word"])
    A = db.raw_sql("select %s from tr_ds_fut.wrds_cseries_info where %s order by dsmnem limit 100"
                   % (SEL, where_a))
    B = db.raw_sql("""select distinct i.calcseriescode, i.clscode, i.dsmnem, i.calcseriesname,
                             i.rollmethodcode, i.rollmethoddesc, i.positionfwdcode,
                             i.positionfwddesc, i.calcmthcode, d.contrname, d.dscontrid
                      from tr_ds_fut.wrds_cseries_info i
                      join tr_ds_fut.dsfutclass f on f.clscode = i.clscode
                      join tr_ds_fut.dsfutcontr d on d.contrcode = f.contrcode
                      where d.exchtickersymb = %(t)s order by i.dsmnem limit 100""",
                   params={"t": spec["ticker"]})
    C = db.raw_sql("select %s from tr_ds_fut.wrds_cseries_info where positionfwdcode = 2 "
                   "and calcseriesname ilike '%s' order by dsmnem limit 100" % (SEL, spec["word"]))
    D = db.raw_sql("select %s from tr_ds_fut.wrds_cseries_info where calcseriesname ilike '%s' "
                   "order by dsmnem limit 100" % (SEL, spec["main"]))

    print("\n\n########## %s - %s ##########" % (code, spec["label"]))
    print("(A) SELECTION POOL  where: %s   -> %d rows (cap 100)" % (where_a, len(A)))
    print(A.to_string(index=False) if len(A) else "(no rows)")
    print("\n(B) evidence: exchtickersymb='%s' via dsfutcontr/dsfutclass -> %d rows (cap 100)"
          % (spec["ticker"], len(B)))
    print(B.to_string(index=False) if len(B) else "(no rows)")
    print("\n(C) evidence: EVERY second-nearby series on ANY exchange whose name matches '%s'"
          " -> %d rows (cap 100)" % (spec["word"].replace("%%", "%"), len(C)))
    print(C.to_string(index=False) if len(C) else "(no rows)")
    print("\n(D) evidence: standard contract by name '%s', ANY exchange prefix -> %d rows (cap 100)"
          % (spec["main"].replace("%%", "%"), len(D)))
    print(D.to_string(index=False) if len(D) else "(no rows)")

    out["candidates"][code] = {
        "label": spec["label"],
        "A_selection_pool": {"where": where_a, "n": len(A), "rows": A.to_dict("records")},
        "B_by_exchange_ticker": {"n": len(B), "rows": B.to_dict("records")},
        "C_second_leg_sweep_all_exchanges": {"n": len(C), "rows": C.to_dict("records")},
        "D_main_contract_any_prefix": {"n": len(D), "rows": D.to_dict("records")}}

ver = db.raw_sql("""select positionfwdcode,
                           substring(dsmnem from '([0-9])[0-9]$') as suffix_position_digit,
                           count(*) as n
                    from tr_ds_fut.wrds_cseries_info
                    where dsmnem ~ '(CS|C\\.)[0-9][0-9]$' group by 1,2 order by 1,2""")
ver2 = db.raw_sql("""select rollmethodcode,
                            substring(dsmnem from '[0-9]([0-9])$') as suffix_roll_digit,
                            count(*) as n
                     from tr_ds_fut.wrds_cseries_info
                     where dsmnem ~ '(CS|C\\.)[0-9][0-9]$' group by 1,2 order by 1,2""")
print("\n\n===== verification: mnemonic suffix POSITION digit vs positionfwdcode =====")
print(ver.to_string(index=False))
print("\n===== verification: mnemonic suffix ROLL digit vs rollmethodcode =====")
print(ver2.to_string(index=False))
out["suffix_position_check"] = ver.to_dict("records")
out["suffix_roll_check"] = ver2.to_dict("records")

SUFFIX = re.compile(r"(?:CS|C\.)([0-9])([0-9])$")
FIRST_NAME = re.compile(r"CONTINUOUS|CONT\.|TRc[0-9]$", re.I)
SECOND_NAME = re.compile(r"2ND|TRc2[0-9]$", re.I)

def classify(r):
    m = SUFFIX.search(r["dsmnem"] or "")
    name = r["calcseriesname"] or ""
    if not m:
        return None, "R2/R3 fail: mnemonic has no two-digit <position><roll> suffix"
    p, rd = m.group(1), m.group(2)
    if p == "0":
        if not FIRST_NAME.search(name):
            return None, "R2 fail: suffix position 0 but name has no continuous-front marker"
        return ("FIRST", rd), None
    if p == "2":
        if not SECOND_NAME.search(name):
            return None, "R3 fail: suffix position 2 but name has no second-contract marker"
        return ("SECOND", rd), None
    return None, "R2/R3 fail: suffix position digit %s is neither front (0) nor second (2)" % p

out["selection"] = {}
for code, spec in COMMODITIES.items():
    rows = out["candidates"][code]["A_selection_pool"]["rows"]
    firsts, seconds, rejected = {}, {}, []
    for r in rows:
        cls, why = classify(r)
        if cls is None:
            rejected.append({"dsmnem": r["dsmnem"], "calcseriesname": r["calcseriesname"],
                             "calcseriescode": r["calcseriescode"], "clscode": r["clscode"],
                             "positionfwddesc": r["positionfwddesc"], "reason": why})
            continue
        leg, rd = cls
        (firsts if leg == "FIRST" else seconds).setdefault(rd, []).append(r)

    pairs = []
    for rd in sorted(set(firsts) & set(seconds)):
        for f in firsts[rd]:
            for s in seconds[rd]:
                if f["clscode"] == s["clscode"]:
                    pairs.append({"roll_digit": rd, "first": f, "second": s})

    print("\n\n===== %s (%s): RULE APPLIED =====" % (code, spec["label"]))
    print("selection pool rows (A): %d" % len(rows))
    print("classified FIRST : %d  (roll digits %s)"
          % (sum(len(v) for v in firsts.values()), sorted(firsts)))
    print("classified SECOND: %d  (roll digits %s)"
          % (sum(len(v) for v in seconds.values()), sorted(seconds)))
    print("rejected         : %d" % len(rejected))
    for rj in rejected:
        print("   REJECT %-10s %-44s clscode=%s : %s"
              % (rj["dsmnem"], rj["calcseriesname"], rj["clscode"], rj["reason"]))
    print("qualifying pairs (R4): %d" % len(pairs))

    selected = None
    if pairs:
        for p in pairs:
            d = db.raw_sql("select min(date_) as mn from tr_ds_fut.dsfutcalcserval "
                           "where calcseriescode = %(c)s",
                           params={"c": p["first"]["calcseriescode"]})
            p["first_leg_min_date"] = str(d.mn[0])
        pairs.sort(key=lambda p: p["first_leg_min_date"])
        selected = pairs[0]
        print("SELECTED (R5): first=%s  second=%s  roll digit %s"
              % (selected["first"]["dsmnem"], selected["second"]["dsmnem"], selected["roll_digit"]))
    else:
        print("NO PAIR QUALIFIES. R6 applies: recorded, moved on.")
        # evidence line: where do second legs for this commodity live?
        ev = out["candidates"][code]["C_second_leg_sweep_all_exchanges"]["rows"]
        cls_in_pool = {r["clscode"] for r in rows}
        print("   second-nearby series for this commodity anywhere: %d, on clscodes %s"
              % (len(ev), sorted({r["clscode"] for r in ev})))
        print("   clscodes in the named-exchange pool: %s" % sorted(cls_in_pool))
        print("   overlap: %s" % sorted({r["clscode"] for r in ev} & cls_in_pool))

    out["selection"][code] = {
        "n_pool": len(rows),
        "n_first": sum(len(v) for v in firsts.values()),
        "n_second": sum(len(v) for v in seconds.values()),
        "first_roll_digits": sorted(firsts), "second_roll_digits": sorted(seconds),
        "rejected": rejected, "n_pairs": len(pairs), "selected": selected,
        "first_leg_rows": [r for v in firsts.values() for r in v]}

dump_json("s1_step2_ds_series.json", out)
db.close()
