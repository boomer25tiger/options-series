"""Step 2b: read the ss_flag and contract_size encodings out of the data.

A1 says "rows are kept only where ss_flag marks standard settlement and contract_size
equals 100; the exact ss_flag encoding is read from the data and recorded". This script
reads it. It is run and reported BEFORE the filter encoding is chosen.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from item1.common import log_to, dump_json, dpath, opath, SECIDS, PULL_SPAN
import numpy as np
import pandas as pd
pd.set_option("display.width", 300); pd.set_option("display.max_rows", 300)

log_to("s1b_step2b_encoding.log")

frames = []
for tic in ["SPX", "GLD", "SLV", "USO", "UNG"]:
    a, b = PULL_SPAN[tic]
    for yr in range(int(a[:4]), int(b[:4]) + 1):
        fn = dpath("opprcd_%s_%d.parquet" % (tic, yr))
        if not os.path.exists(fn):
            continue
        d = pd.read_parquet(fn, columns=["date", "ss_flag", "contract_size", "root",
                                         "suffix", "exdate", "cp_flag", "strike_price",
                                         "open_interest"])
        d["ticker"] = tic
        frames.append(d)
q = pd.concat(frames, ignore_index=True)
print("rows read: %s" % "{:,}".format(len(q)))

print("\n===== distinct ss_flag per secid, with row counts =====")
a = q.groupby(["ticker", "ss_flag"], dropna=False).size().rename("rows").reset_index()
a["share"] = a.rows / a.groupby("ticker").rows.transform("sum")
print(a.to_string(index=False))

print("\n===== distinct contract_size per secid, with row counts =====")
b = q.groupby(["ticker", "contract_size"], dropna=False).size().rename("rows").reset_index()
b["share"] = b.rows / b.groupby("ticker").rows.transform("sum")
print(b.to_string(index=False))

print("\n===== ss_flag x contract_size joint, per secid =====")
c = q.groupby(["ticker", "ss_flag", "contract_size"], dropna=False).size().rename("rows").reset_index()
c["share"] = c.rows / c.groupby("ticker").rows.transform("sum")
print(c.to_string(index=False))

print("\n===== root and suffix: how the chains are labelled =====")
d = q.groupby(["ticker", "root"], dropna=False).size().rename("rows").reset_index()
print(d.to_string(index=False))
e = q.groupby(["ticker", "suffix"], dropna=False).size().rename("rows").reset_index()
print("\nsuffix:")
print(e.to_string(index=False))

print("\n===== cross-tab of ss_flag against root, for the ETFs that carry two chains =====")
for tic in ["GLD", "USO", "UNG"]:
    sub = q[q.ticker == tic]
    ct = sub.groupby(["root", "ss_flag"], dropna=False).size().unstack(fill_value=0)
    print("\n%s:" % tic)
    print(ct.to_string())

print("\n===== does ss_flag separate the duplicated strikes? =====")
rows = []
for tic, g in q.groupby("ticker"):
    dup_all = g.duplicated(["date", "exdate", "cp_flag", "strike_price"], keep=False).sum()
    dup_std = 0
    std = g[(g.ss_flag == "0") & (g.contract_size == 100)]
    if len(std):
        dup_std = std.duplicated(["date", "exdate", "cp_flag", "strike_price"], keep=False).sum()
    rows.append({"ticker": tic, "rows": len(g), "dup_rows_all": int(dup_all),
                 "rows_ssflag0_size100": len(std), "dup_rows_after_filter": int(dup_std)})
f = pd.DataFrame(rows)
print(f.to_string(index=False))

dump_json("s1b_step2b_encoding.json", {
    "rows": len(q),
    "ss_flag": a.to_dict("records"),
    "contract_size": b.to_dict("records"),
    "joint": c.to_dict("records"),
    "root": d.to_dict("records"),
    "suffix": e.to_dict("records"),
    "dup_before_after": f.to_dict("records"),
})
