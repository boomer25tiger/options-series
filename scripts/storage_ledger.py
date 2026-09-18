"""Storage ledger across the quant projects on this machine. It reports and deletes
nothing.

python scripts/storage_ledger.py

Discovery walks ~/Downloads and the home directory to depth 2 and keeps every directory
above 100 MB and every directory holding one of the MARKERS files. Each file counts once,
toward the deepest discovered root that contains it, so nested roots never double count.
Sizes are allocated blocks, the space a deletion would free, and a hard-linked file counts
once.

Within a root, a file's leaf directory is its directory cut to depth 3 below the root,
or the deeper manifest entry that contains it. storage_manifest.yaml in the repository
root classifies each leaf by the longest matching path, and a leaf no entry matches
stays unknown. A leaf holding purchased Databento files, whose names the DATABENTO
pattern matches, is irreplaceable unless an entry names it.

The reclaim table ranks regenerable leaves by megabytes freed per minute of
regeneration, so large leaves that rebuild fast come first, with a running total. Each
run writes the report to scripts/output/storage_ledger.txt, which git ignores, and prints
it.
"""

from __future__ import annotations

import os
import re
import stat
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

HOME = Path.home()
SCAN_ROOTS = (HOME / "Downloads", HOME)
DISCOVERY_DEPTH = 2
SIZE_FLOOR_BYTES = 100 * 1024**2
MARKERS = (".git", "pyproject.toml", "requirements.txt")
# macOS manages these directories, and walking them costs minutes and hits privacy walls.
SKIPPED = (HOME / "Library", HOME / ".Trash")
LEAF_DEPTH = 3
REPOSITORY = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY / "storage_manifest.yaml"
REPORT_PATH = REPOSITORY / "scripts" / "output" / "storage_ledger.txt"
DATABENTO = re.compile(
    r"glbx|\.dbn(\.zst)?$|ohlcv-1s.*\b(es|nq|spy)\b|\b(es|nq|spy)\b.*ohlcv-1s",
    re.IGNORECASE,
)
# A directory whose name marks GLBX data or second bars flags its whole subtree once a
# Databento file sits anywhere below it.
DATABENTO_DIRECTORY = re.compile(r"glbx|\b(es|nq|spy)\b.*\b1s\b", re.IGNORECASE)
ITEM_PARTS = {
    "item 1": "items/item1_commodity_vrp",
    "item 2": "items/item2_correlation_premium",
    "item 3": "items/item3_short_variance",
    "probe": "probe",
}


@dataclass
class Stats:
    """Allocated bytes and file count with the newest modification time."""

    size: int = 0
    files: int = 0
    newest: float = 0.0

    def add(self, size: int, modified: float) -> None:
        self.size += size
        self.files += 1
        self.newest = max(self.newest, modified)

    def merge(self, other: Stats) -> None:
        self.size += other.size
        self.files += other.files
        self.newest = max(self.newest, other.newest)


@dataclass
class Directory:
    """One walked directory with its own files by extension and flags for a marker or a
    Databento file."""

    own: dict[str, Stats] = field(default_factory=lambda: defaultdict(Stats))
    marker: bool = False
    databento: bool = False
    named: bool = False


def read_manifest(path: Path) -> list[dict[str, str]]:
    """Entries of the manifest, a top-level `entries:` list of flat mappings in which
    each `- key: value` line opens an entry and each indented `key: value` line continues
    it. The parser skips comments and blank lines and strips quotes from values."""
    entries: list[dict[str, str]] = []
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split(" #")[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line or line == "entries:":
            continue
        match = re.fullmatch(r"\s*(- )?([a-z_]+):\s*(.*)", line)
        if not match:
            raise ValueError(f"{path.name} line {number}: cannot read {raw!r}")
        opens, key, value = match.groups()
        if opens:
            entries.append({})
        if not entries:
            raise ValueError(f"{path.name} line {number}: key outside an entry")
        entries[-1][key] = value.strip().strip("'\"")
    for entry in entries:
        entry["resolved"] = str(Path(os.path.expanduser(entry["path"])))
        if entry.get("classification") not in (
            "regenerable",
            "irreplaceable",
            "unknown",
        ):
            raise ValueError(f"bad classification in manifest entry {entry['path']}")
        if entry["classification"] == "regenerable" and not (
            entry.get("command") and entry.get("regeneration_minutes")
        ):
            raise ValueError(
                f"regenerable entry {entry['path']} needs a command and time"
            )
    return entries


def walk(file_leaves: set[str]) -> dict[Path, Directory]:
    """Every directory under the home directory with its own files, skipping symlinks
    and the macOS-managed directories, counting a hard-linked file once. The walk records
    a file that a manifest entry names under its own path, so the file forms its own
    leaf."""
    directories: dict[Path, Directory] = {}
    seen_inodes: set[tuple[int, int]] = set()
    pending = [HOME]
    while pending:
        current = pending.pop()
        if current in SKIPPED or current in directories:
            continue
        record = directories.setdefault(current, Directory())
        record.named = bool(DATABENTO_DIRECTORY.search(current.name))
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if entry.name in MARKERS:
                record.marker = True
            if stat.S_ISLNK(info.st_mode):
                continue
            if stat.S_ISDIR(info.st_mode):
                pending.append(Path(entry.path))
                continue
            if info.st_nlink > 1:
                inode = (info.st_dev, info.st_ino)
                if inode in seen_inodes:
                    continue
                seen_inodes.add(inode)
            holder = record
            if entry.path in file_leaves:
                holder = directories.setdefault(Path(entry.path), Directory())
            if DATABENTO.search(entry.name):
                holder.databento = True
            suffix = "".join(Path(entry.name).suffixes[-2:]).lower() or "(none)"
            holder.own[suffix].add(info.st_blocks * 512, info.st_mtime)
    return directories


def flag_databento_trees(directories: dict[Path, Directory]) -> None:
    """Extend the Databento flag from each directory holding a Databento file to the
    whole subtree of every Databento-named directory above it."""
    holding = set()
    for path, record in directories.items():
        if record.databento:
            for ancestor in (path, *path.parents):
                holding.add(ancestor)
                if ancestor == HOME:
                    break
    trees = {
        path for path, record in directories.items() if record.named and path in holding
    }
    for path, record in directories.items():
        if any(ancestor in trees for ancestor in (path, *path.parents)):
            record.databento = True


def subtree_sizes(directories: dict[Path, Directory]) -> dict[Path, int]:
    """Allocated bytes under every walked directory."""
    totals: dict[Path, int] = defaultdict(int)
    for path, record in directories.items():
        own = sum(stats.size for stats in record.own.values())
        for ancestor in (path, *path.parents):
            totals[ancestor] += own
            if ancestor == HOME:
                break
    return totals


def discover(
    directories: dict[Path, Directory], totals: dict[Path, int], file_leaves: set[str]
) -> list[Path]:
    """Directories within the discovery depth of a scan root that pass the size floor or
    hold a marker. A directory without a marker inside a directory with one belongs to
    that project and is not a root of its own."""
    found = set()
    for scan_root in SCAN_ROOTS:
        for path, record in directories.items():
            if str(path) in file_leaves:
                continue
            try:
                depth = len(path.relative_to(scan_root).parts)
            except ValueError:
                continue
            if 1 <= depth <= DISCOVERY_DEPTH and (
                totals[path] > SIZE_FLOOR_BYTES or record.marker
            ):
                found.add(path)
    return sorted(
        path
        for path in found
        if directories[path].marker
        or not any(
            parent in found and directories[parent].marker for parent in path.parents
        )
    )


def owning_root(path: Path, roots: set[Path]) -> Path | None:
    """Deepest discovered root containing the path."""
    for candidate in (path, *path.parents):
        if candidate in roots:
            return candidate
    return None


def leaf_of(path: Path, root: Path, manifest: list[dict[str, str]]) -> Path:
    """The leaf of a file's directory, which is the directory cut to LEAF_DEPTH below the
    root or the deeper manifest entry that contains it."""
    relative = path.relative_to(root).parts
    leaf = root.joinpath(*relative[:LEAF_DEPTH])
    for entry in manifest:
        resolved = Path(entry["resolved"])
        if len(resolved.parts) > len(leaf.parts) and path.is_relative_to(resolved):
            leaf = max(leaf, resolved, key=lambda candidate: len(candidate.parts))
    return leaf


def classify(
    leaf: Path, databento: bool, manifest: list[dict[str, str]]
) -> dict[str, str]:
    """Manifest entry with the longest path containing the leaf; Databento leaves no
    entry names default to irreplaceable, everything else to unknown."""
    matches = [
        entry for entry in manifest if leaf.is_relative_to(Path(entry["resolved"]))
    ]
    exact = [entry for entry in matches if Path(entry["resolved"]) == leaf]
    if databento and not exact:
        return {
            "classification": "irreplaceable",
            "command": "",
            "regeneration_minutes": "",
            "basis": "holds purchased Databento files",
        }
    if matches:
        return max(matches, key=lambda entry: len(entry["resolved"]))
    return {"classification": "unknown", "command": "", "regeneration_minutes": ""}


def megabytes(size: int) -> str:
    """Size in MB with thousands separators."""
    return f"{size / 1024**2:,.1f}"


def stamp(seconds: float) -> str:
    """Local date of a modification time."""
    return time.strftime("%Y-%m-%d", time.localtime(seconds)) if seconds else ""


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Fixed-width text table."""
    widths = [max(len(str(cell)) for cell in column) for column in zip(headers, *rows)]
    line = "  ".join(f"{{:<{width}}}" for width in widths)
    return [line.format(*headers), line.format(*("-" * width for width in widths))] + [
        line.format(*map(str, row)) for row in rows
    ]


def main() -> None:
    """Walk, discover, aggregate, classify and report."""
    started = time.time()
    manifest = read_manifest(MANIFEST_PATH)
    file_leaves = {
        entry["resolved"] for entry in manifest if entry.get("kind") == "file"
    }
    directories = walk(file_leaves)
    flag_databento_trees(directories)
    totals = subtree_sizes(directories)
    roots = discover(directories, totals, file_leaves)
    root_set = set(roots)
    lines = [
        "Storage ledger, reports only, deletes nothing",
        (
            f"Walked {len(directories):,} directories under {HOME} in "
            f"{time.time() - started:.0f} s, skipping {', '.join(map(str, SKIPPED))}"
        ),
        "",
        f"Discovered roots ({len(roots)}): depth 1 to {DISCOVERY_DEPTH} under "
        + " and ".join(map(str, SCAN_ROOTS))
        + f", above {SIZE_FLOOR_BYTES // 1024**2} MB or holding "
        + ", ".join(MARKERS),
    ]
    lines += [
        f"  {path}  {megabytes(totals[path])} MB"
        + ("  marker" if directories[path].marker else "")
        for path in roots
    ]

    subdirectories: dict[Path, dict[Path, Stats]] = defaultdict(
        lambda: defaultdict(Stats)
    )
    extensions: dict[Path, dict[str, Stats]] = defaultdict(lambda: defaultdict(Stats))
    leaves: dict[tuple[Path, Path], Stats] = defaultdict(Stats)
    databento_leaves: set[Path] = set()
    for path, record in directories.items():
        root = owning_root(path, root_set)
        if root is None or not record.own:
            continue
        leaf = leaf_of(path, root, manifest)
        relative = path.relative_to(root).parts
        for suffix, stats in record.own.items():
            for depth in range(min(len(relative), LEAF_DEPTH) + 1):
                subdirectories[root][root.joinpath(*relative[:depth])].merge(stats)
            extensions[root][suffix].merge(stats)
            leaves[(root, leaf)].merge(stats)
        if record.databento:
            databento_leaves.add(leaf)

    reclaim, irreplaceable, unknown = [], [], []
    by_root: dict[Path, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (root, leaf), stats in leaves.items():
        entry = classify(leaf, leaf in databento_leaves, manifest)
        kind = entry["classification"]
        by_root[root][kind] += stats.size
        row = (root, leaf, stats, entry)
        {"regenerable": reclaim, "irreplaceable": irreplaceable, "unknown": unknown}[
            kind
        ].append(row)

    for root in roots:
        lines += [
            "",
            f"== {root}  {megabytes(totals.get(root, 0))} MB",
        ]
        own = subdirectories[root]
        lines += table(
            ["subdirectory", "MB", "files", "newest"],
            [
                [
                    str(path.relative_to(root)) or ".",
                    megabytes(stats.size),
                    f"{stats.files:,}",
                    stamp(stats.newest),
                ]
                for path, stats in sorted(own.items(), key=lambda item: -item[1].size)
                if stats.size >= 1024**2 or path == root
            ][:40],
        )
        lines += [""] + table(
            ["extension", "MB", "files"],
            [
                [suffix, megabytes(stats.size), f"{stats.files:,}"]
                for suffix, stats in sorted(
                    extensions[root].items(), key=lambda item: -item[1].size
                )[:15]
            ],
        )

    def minutes(entry: dict[str, str]) -> float:
        return float(entry.get("regeneration_minutes") or "nan")

    grouped: dict[str, tuple[Stats, dict[str, str], int]] = {}
    for _, _, stats, entry in reclaim:
        total, _, leaf_count = grouped.get(entry["resolved"], (Stats(), entry, 0))
        total.merge(stats)
        grouped[entry["resolved"]] = (total, entry, leaf_count + 1)
    ranked = sorted(
        grouped.values(),
        key=lambda item: -(item[0].size / 1024**2) / max(minutes(item[1]), 0.1),
    )
    running = 0
    reclaim_rows = []
    for stats, entry, leaf_count in ranked:
        running += stats.size
        reclaim_rows.append(
            [
                entry["path"],
                megabytes(stats.size),
                f"{leaf_count}",
                f"{minutes(entry):g}",
                f"{stats.size / 1024**2 / max(minutes(entry), 0.1):,.1f}",
                megabytes(running),
                entry["command"],
            ]
        )
    lines += [
        "",
        (
            "Reclaim table: regenerable manifest entries, most MB freed per "
            "regeneration minute first"
        ),
    ]
    lines += table(
        [
            "manifest entry",
            "MB",
            "leaves",
            "regen min",
            "MB per min",
            "cumulative MB",
            "regenerate with",
        ],
        reclaim_rows,
    )
    lines += ["", "Irreplaceable, no reclaim suggestion"]
    lines += table(
        ["leaf", "MB", "reason"],
        [
            [str(leaf), megabytes(stats.size), entry.get("basis", "")]
            for _, leaf, stats, entry in sorted(
                irreplaceable, key=lambda row: -row[2].size
            )
        ],
    )
    lines += ["", "Unknown, largest 25"]
    lines += table(
        ["leaf", "MB"],
        [
            [str(leaf), megabytes(stats.size)]
            for _, leaf, stats, _ in sorted(unknown, key=lambda row: -row[2].size)[:25]
        ],
    )

    parent_of = {
        root: next((parent for parent in root.parents if parent in root_set), None)
        for root in roots
    }
    with_nested: dict[Path, int] = defaultdict(int)
    for root in roots:
        for ancestor in (root, *root.parents):
            if ancestor in root_set:
                with_nested[ancestor] += sum(by_root[root].values())
    lines += [
        "",
        "Totals by root, each file counted once in the deepest root holding it",
    ]
    lines += table(
        [
            "root",
            "inside root",
            "own MB",
            "with nested MB",
            "regenerable MB",
            "irreplaceable MB",
            "unknown MB",
        ],
        [
            [
                str(root),
                str(parent_of[root] or ""),
                megabytes(sum(by_root[root].values())),
                megabytes(with_nested[root]),
                megabytes(by_root[root]["regenerable"]),
                megabytes(by_root[root]["irreplaceable"]),
                megabytes(by_root[root]["unknown"]),
            ]
            for root in roots
        ],
    )
    if REPOSITORY in root_set:
        parts = []
        for label, relative in ITEM_PARTS.items():
            part = REPOSITORY / relative
            kinds: dict[str, int] = defaultdict(int)
            for (root, leaf), stats in leaves.items():
                if root == REPOSITORY and leaf.is_relative_to(part):
                    kinds[
                        classify(leaf, leaf in databento_leaves, manifest)[
                            "classification"
                        ]
                    ] += stats.size
            parts.append(
                [
                    label,
                    megabytes(sum(kinds.values())),
                    megabytes(kinds["regenerable"]),
                    megabytes(kinds["irreplaceable"]),
                    megabytes(kinds["unknown"]),
                ]
            )
        lines += ["", f"{REPOSITORY.name} by part"]
        lines += table(
            ["part", "total MB", "regenerable MB", "irreplaceable MB", "unknown MB"],
            parts,
        )
    everything = defaultdict(int)
    for root in roots:
        for kind, size in by_root[root].items():
            everything[kind] += size
    lines += [
        "",
        (
            f"All roots: regenerable {megabytes(everything['regenerable'])} MB, "
            f"irreplaceable {megabytes(everything['irreplaceable'])} MB, "
            f"unknown {megabytes(everything['unknown'])} MB"
        ),
    ]

    report = "\n".join(lines) + "\n"
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report)
    sys.stdout.write(report)


if __name__ == "__main__":
    main()
