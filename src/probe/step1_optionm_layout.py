"""Step 1: OptionMetrics library/table layout, schemas, feed span."""
import os, re, sys, json, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json, OUT_DIR

log_to("step1_optionm_layout.log")
db = connect()

libs = db.list_libraries()
optionm_libs = sorted([l for l in libs if "optionm" in l.lower()])
print("TOTAL LIBRARIES VISIBLE: %d" % len(libs))
print("LIBRARIES MATCHING 'optionm': %s" % optionm_libs)

result = {"n_libraries": len(libs), "optionm_libraries": optionm_libs, "tables": {}}

for lib in optionm_libs:
    try:
        tabs = sorted(db.list_tables(library=lib))
    except Exception as e:
        print("  %s: list_tables FAILED: %s" % (lib, e))
        result["tables"][lib] = {"error": str(e)}
        continue
    result["tables"][lib] = tabs
    print("\n=== LIBRARY %s : %d tables ===" % (lib, len(tabs)))
    for t in tabs:
        print("  " + t)

dump_json("step1_tables.json", result)
db.close()
