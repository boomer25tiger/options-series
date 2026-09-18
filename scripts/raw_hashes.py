"""Hashes of pulled data, recorded in storage_manifest.yaml so a later re-pull can be
checked against the data behind the published results.

python scripts/raw_hashes.py record DIRECTORY   print the files block for DIRECTORY
python scripts/raw_hashes.py verify DIRECTORY   compare DIRECTORY with its manifest entry

Every file carries sha256 over its bytes, its size and its modification time. A parquet
file also carries its row count and content_sha256, the SHA-256 of its table in a
canonical form. The canonical form keeps the stored column order and types, decodes
dictionary-encoded columns to their value type, drops schema and field metadata, sorts rows ascending on every column in stored order with nulls last,
combines chunks and serializes the result as one uncompressed Arrow IPC stream. A
database returns rows in no fixed order and a writer version stamps its own metadata, so
a faithful re-pull can differ in bytes and still match in content. A content mismatch
means the vendor data differ from the data behind the published results.
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from storage_ledger import MANIFEST_PATH, REPOSITORY, read_manifest

CHUNK_BYTES = 1 << 20
FILES_INDENT = 8


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(CHUNK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def content_sha256(path: Path) -> tuple[int, str]:
    """Row count and SHA-256 of a parquet table in the canonical form."""
    table = pq.read_table(path)
    columns, fields = [], []
    for field, column in zip(table.schema, table.columns):
        kind = (
            field.type.value_type if pa.types.is_dictionary(field.type) else field.type
        )
        columns.append(column.cast(kind))
        fields.append(pa.field(field.name, kind, field.nullable))
    table = pa.Table.from_arrays(columns, schema=pa.schema(fields))
    if table.num_rows:
        order = pc.sort_indices(
            table,
            sort_keys=[(name, "ascending", "at_end") for name in table.column_names],
        )
        table = table.take(order)
    table = table.combine_chunks()
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return table.num_rows, hashlib.sha256(sink.getvalue()).hexdigest()


def describe(path: Path) -> dict[str, str]:
    """Hashes, size, modification time and, for parquet, row count of one file."""
    record = {
        "sha256": file_sha256(path),
        "bytes": str(path.stat().st_size),
        "modified": time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(path.stat().st_mtime)
        ),
    }
    if path.suffix == ".parquet":
        rows, digest = content_sha256(path)
        record["rows"] = str(rows)
        record["content_sha256"] = digest
    return record


def files_of(directory: Path) -> list[Path]:
    """Every regular file under a directory, sorted, hidden files skipped, along with
    files under a deeper manifest entry that keeps its own reproducibility record."""
    target = directory.resolve()
    nested = [
        Path(entry["resolved"])
        for entry in read_manifest(MANIFEST_PATH)
        if "reproducibility" in entry
        and Path(entry["resolved"]) != target
        and Path(entry["resolved"]).is_relative_to(target)
    ]
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file()
        and not path.name.startswith(".")
        and not any(path.resolve().is_relative_to(inner) for inner in nested)
    )


def record(directory: Path) -> None:
    """Print the manifest files block for a directory."""
    for path in files_of(directory):
        fields = ", ".join(f"{key}: {value}" for key, value in describe(path).items())
        relative = path.relative_to(directory).as_posix()
        print(f"{' ' * FILES_INDENT}{relative}: {{{fields}}}")


def verify(directory: Path) -> int:
    """Compare a directory with the files block of its manifest entry; the return code
    is 1 when any content hash differs or any recorded file is missing."""
    target = str(directory.resolve())
    entries = [
        entry for entry in read_manifest(MANIFEST_PATH) if entry["resolved"] == target
    ]
    if not entries or "files" not in entries[0].get("reproducibility", {}):
        print(f"no recorded files for {directory}")
        return 1
    recorded = entries[0]["reproducibility"]["files"]
    present = {
        path.relative_to(directory).as_posix(): path for path in files_of(directory)
    }
    failures = 0
    for relative, expected in sorted(recorded.items()):
        path = present.pop(relative, None)
        if path is None:
            print(f"missing  {relative}")
            failures += 1
            continue
        actual = describe(path)
        if actual["sha256"] == expected["sha256"]:
            status = "same bytes"
        elif (
            "content_sha256" in expected
            and actual.get("content_sha256") == expected["content_sha256"]
        ):
            status = "same content, different bytes"
        else:
            status = "DIFFERENT CONTENT"
            failures += 1
        print(f"{status:30s} {relative}")
    for relative in sorted(present):
        print(f"{'not recorded':30s} {relative}")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    """Dispatch the record and verify commands."""
    if len(argv) != 2 or argv[0] not in ("record", "verify"):
        print(__doc__)
        return 2
    directory = Path(argv[1])
    if not directory.is_absolute():
        directory = REPOSITORY / directory
    if argv[0] == "record":
        record(directory)
        return 0
    return verify(directory)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
