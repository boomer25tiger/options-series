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


def table_columns(connection: wrds.Connection, schema: str, table: str) -> pd.DataFrame:
    """Column names and types of a table, in order, from information_schema.columns."""
    return query(
        connection,
        "select column_name, data_type from information_schema.columns "
        "where table_schema = %(schema)s and table_name = %(table)s "
        "order by ordinal_position",
        {"schema": schema, "table": table},
    )


def copy_query_to_csv(
    connection: wrds.Connection, sql: str, params: dict | None, path: Path
) -> None:
    """Stream the result of a parameterised query to a CSV file with a header through
    COPY, so a large result is never held in memory."""
    with connection.connection.connection.cursor() as cursor:
        statement = cursor.mogrify(sql, params).decode()
        with open(path, "wb") as handle:
            cursor.copy_expert(
                f"COPY ({statement}) TO STDOUT WITH (FORMAT csv, HEADER true)", handle
            )
