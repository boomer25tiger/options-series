"""Step 7: Datastream / Refinitiv libraries and commodity series search."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json
import pandas as pd
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 400)
pd.set_option("display.max_colwidth", 70)

log_to("step7_datastream.log")
db = connect()
out = {}

libs = sorted(db.list_libraries())
match = [l for l in libs if ("ds" in l.lower() or "datastream" in l.lower() or "tr_" in l.lower())]
print("TOTAL LIBRARIES: %d" % len(libs))
print("LIBRARIES MATCHING 'ds' OR 'datastream' OR 'tr_': %d" % len(match))
for l in match:
    print("  " + l)
out["matching_libraries"] = match

# The literal substring 'ds' also matches unrelated names (wrdsapps*, funds, ...).
# Narrow to the ones that are plausibly Datastream/Refinitiv feeds.
narrow = [l for l in match if l.startswith("tr_") or l.startswith("trws")
          or "datastream" in l.lower() or l.startswith("ds")
          or l.startswith("trdstrm")]
print("\nNARROWED (prefix tr_/trws/ds or contains 'datastream'): %d" % len(narrow))
for l in narrow:
    print("  " + l)
out["narrowed_libraries"] = narrow

out["tables"] = {}
for lib in narrow:
    try:
        tabs = sorted(db.list_tables(library=lib))
    except Exception as e:
        print("\n=== %s : list_tables FAILED %r" % (lib, e))
        out["tables"][lib] = {"error": str(e)}
        continue
    out["tables"][lib] = tabs
    print("\n=== %s : %d tables ===" % (lib, len(tabs)))
    for t in tabs:
        print("   " + t)

dump_json("step7_libraries.json", out)
db.close()
