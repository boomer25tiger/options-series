"""Step 7c: the Datastream sample schemas the Step 7 narrowing filter dropped."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, log_to, dump_json

log_to("step7c_ds_samples.log")
db = connect()
LIBS = ["trdssamp", "trsamp_ds_eq", "trsamp_dscom", "trsamp_dsecon", "trsamp_dsfut"]
out = {}
for lib in LIBS:
    try:
        tabs = sorted(db.list_tables(library=lib))
    except Exception as e:
        print("%s: FAILED %r" % (lib, e)); out[lib] = {"error": str(e)}; continue
    out[lib] = tabs
    print("\n=== %s : %d tables ===" % (lib, len(tabs)))
    for t in tabs:
        print("   " + t)
dump_json("step7c_ds_samples.json", out)
db.close()
