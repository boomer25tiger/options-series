"""Shared helpers for item 1. Reuses the connection helper from src/probe/."""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from probe.common import connect, WRDS_USERNAME  # noqa: F401  (reused per handling rules)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "item1")
OUT_DIR = os.path.join(PROJECT_ROOT, "output", "item1")
for _d in (DATA_DIR, OUT_DIR):
    os.makedirs(_d, exist_ok=True)

# Section 4 of the spec. Fixed here, never re-resolved at query time.
SECIDS = {"SPX": 108105, "GLD": 122392, "SLV": 126776, "USO": 126681, "UNG": 129367}

# Pull spans, per the session instruction.
PULL_SPAN = {
    "SPX": ("2008-01-01", "2025-08-29"),
    "GLD": ("2008-01-01", "2025-08-29"),
    "SLV": ("2008-01-01", "2025-08-29"),
    "USO": ("2007-01-01", "2025-08-29"),
    "UNG": ("2007-01-01", "2025-08-29"),
}

# Section 5 of the spec.
COMMON_START = "2008-12-08"
COMMON_END = "2025-08-29"

NODES = (30, 91)


class Tee:
    def __init__(self, path):
        self.f = open(path, "w")

    def write(self, s):
        sys.__stdout__.write(s)
        self.f.write(s)

    def flush(self):
        sys.__stdout__.flush()
        self.f.flush()


def log_to(name):
    t = Tee(os.path.join(OUT_DIR, name))
    sys.stdout = t
    return t


def dump_json(name, obj):
    with open(os.path.join(OUT_DIR, name), "w") as f:
        json.dump(obj, f, indent=2, default=str)


def load_json(name):
    with open(os.path.join(OUT_DIR, name)) as f:
        return json.load(f)


def cols_of(db, schema, table):
    """Column list from information_schema (db.describe_table is broken in this client)."""
    return db.raw_sql(
        "select ordinal_position, column_name, data_type, is_nullable "
        "from information_schema.columns "
        "where table_schema=%(s)s and table_name=%(t)s order by ordinal_position",
        params={"s": schema, "t": table})


def timed(db, sql, params=None):
    t0 = time.time()
    df = db.raw_sql(sql, params=params)
    return df, time.time() - t0


def dpath(name):
    return os.path.join(DATA_DIR, name)


def opath(name):
    return os.path.join(OUT_DIR, name)
