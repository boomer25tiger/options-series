"""Connection to WRDS."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import wrds

PGPASS_PATH = Path.home() / ".pgpass"


def wrds_username() -> str | None:
    """WRDS username from WRDS_USERNAME, else from the WRDS entry in ~/.pgpass."""
    if os.environ.get("WRDS_USERNAME"):
        return os.environ["WRDS_USERNAME"]
    if not PGPASS_PATH.exists():
        return None
    for line in PGPASS_PATH.read_text().splitlines():
        fields = line.split(":")
        if len(fields) >= 5 and "wrds" in fields[0]:
            return fields[3]
    return None


def connect() -> wrds.Connection:
    """Open a WRDS connection authenticated from ~/.pgpass."""
    return wrds.Connection(wrds_username=wrds_username())


def query(
    connection: wrds.Connection, sql: str, params: dict | None = None
) -> pd.DataFrame:
    """Run a parameterised SQL query and return the result as a data frame."""
    return connection.raw_sql(sql, params=params)
