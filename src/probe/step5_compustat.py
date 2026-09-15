"""Step 5: Compustat comp.fundq rdq (report date of quarterly earnings) coverage."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json, OUT_DIR
import pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)

log_to("step5_compustat.log")
db = connect()
out = {}

cols = db.raw_sql(
    "select ordinal_position, column_name, data_type from information_schema.columns "
    "where table_schema='comp' and table_name='fundq' order by ordinal_position")
print("comp.fundq has %d columns" % len(cols))
names = list(cols.column_name)
out["n_columns"] = len(names)
out["rdq_present"] = "rdq" in names
print("rdq present: %s" % ("rdq" in names))
print(cols[cols.column_name.isin(
    ["gvkey", "datadate", "fyearq", "fqtr", "rdq", "datacqtr", "datafqtr",
     "indfmt", "datafmt", "popsrc", "consol", "epsfxq", "epspxq"])].to_string(index=False))
out["key_columns"] = cols[cols.column_name.isin(
    ["gvkey", "datadate", "fyearq", "fqtr", "rdq", "datacqtr", "datafqtr",
     "indfmt", "datafmt", "popsrc", "consol"])].to_dict("records")

try:
    print("\nrow count comp.fundq: %s" % db.get_row_count("comp", "fundq"))
except Exception as e:
    print("row count FAILED: %r" % (e,))

print("\n===== rdq non-null share, datadate >= 2010-01-01, ALL format rows =====")
a = db.raw_sql("""select count(*) as n, count(rdq) as nn_rdq,
                         min(datadate) as mn, max(datadate) as mx,
                         min(rdq) as rdq_min, max(rdq) as rdq_max
                  from comp.fundq where datadate >= '2010-01-01'""")
a["share_rdq"] = a.nn_rdq / a.n
print(a.to_string(index=False))
out["all_formats_2010plus"] = a.to_dict("records")[0]

print("\n===== rdq non-null share, datadate >= 2010-01-01, standard filter"
      " indfmt='INDL' datafmt='STD' popsrc='D' consol='C' =====")
b = db.raw_sql("""select count(*) as n, count(rdq) as nn_rdq
                  from comp.fundq where datadate >= '2010-01-01'
                    and indfmt='INDL' and datafmt='STD' and popsrc='D' and consol='C'""")
b["share_rdq"] = b.nn_rdq / b.n
print(b.to_string(index=False))
out["std_filter_2010plus"] = b.to_dict("records")[0]

print("\n===== by fiscal year (fyearq), standard filter =====")
c = db.raw_sql("""select fyearq::int as fyearq, count(*) as n, count(rdq) as nn_rdq
                  from comp.fundq
                  where fyearq >= 2010 and indfmt='INDL' and datafmt='STD'
                    and popsrc='D' and consol='C'
                  group by 1 order by 1""")
c["share_rdq"] = c.nn_rdq / c.n
print(c.to_string(index=False))
c.to_csv(os.path.join(OUT_DIR, "step5_fundq_rdq_by_fyearq.csv"), index=False)
out["by_fyearq_std_filter"] = c.to_dict("records")

dump_json("step5_compustat.json", out)
db.close()
