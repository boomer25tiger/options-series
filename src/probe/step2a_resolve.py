"""Step 2a: resolve secid for SPX, SPY, GLD, SLV, USO, UNG."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json
import pandas as pd
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 50)
pd.set_option("display.max_rows", 500)

log_to("step2a_resolve.log")
db = connect()
TICKERS = ["SPX", "SPY", "GLD", "SLV", "USO", "UNG"]
out = {}

print("========== optionm.securd1 (has issuer) matched on ticker ==========")
s1 = db.raw_sql(
    "select secid, ticker, cusip, class, issuer, issue_type, index_flag, sic, "
    "exchange_d, industry_group from optionm.securd1 "
    "where ticker = any(%(t)s) order by ticker, secid", params={"t": TICKERS})
print(s1.to_string(index=False))
out["securd1"] = s1.to_dict("records")

print("\n========== optionm.securd (no issuer) matched on ticker ==========")
s0 = db.raw_sql(
    "select secid, ticker, cusip, class, issue_type, index_flag, sic "
    "from optionm.securd where ticker = any(%(t)s) order by ticker, secid",
    params={"t": TICKERS})
print(s0.to_string(index=False))
out["securd"] = s0.to_dict("records")

print("\n========== optionm.secnmd name history for those tickers ==========")
nm = db.raw_sql(
    "select secid, ticker, class, issuer, issue, cusip, sic, "
    "min(effect_date) as first_effect_date, max(effect_date) as last_effect_date, "
    "count(*) as n_name_records "
    "from optionm.secnmd where ticker = any(%(t)s) "
    "group by secid, ticker, class, issuer, issue, cusip, sic "
    "order by ticker, secid, first_effect_date", params={"t": TICKERS})
print(nm.to_string(index=False))
out["secnmd_by_ticker"] = nm.to_dict("records")

print("\n========== secnmd: full effect_date span per secid found above ==========")
secids = sorted(set(s1.secid.tolist()) | set(s0.secid.tolist()) | set(nm.secid.tolist()))
print("candidate secids: %s" % secids)
sp = db.raw_sql(
    "select secid, min(effect_date) as first_effect_date, max(effect_date) as last_effect_date, "
    "count(*) as n_records, count(distinct ticker) as n_tickers, "
    "array_agg(distinct ticker) as tickers "
    "from optionm.secnmd where secid = any(%(s)s) group by secid order by secid",
    params={"s": [float(x) for x in secids]})
print(sp.to_string(index=False))
out["secnmd_span_by_secid"] = sp.to_dict("records")

dump_json("step2a_resolve.json", out)
db.close()
