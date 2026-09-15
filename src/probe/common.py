"""Shared helpers for the capability probe scripts."""
import os
import sys
import time
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(PROJECT_ROOT, "probe_output")
os.makedirs(OUT_DIR, exist_ok=True)

WRDS_USERNAME = "cgresearch26"


def connect():
    import wrds
    return wrds.Connection(wrds_username=WRDS_USERNAME)


class Tee:
    """Write everything to stdout and to a log file under probe_output/."""

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


def timed(db, sql, params=None):
    t0 = time.time()
    df = db.raw_sql(sql, params=params)
    return df, time.time() - t0
