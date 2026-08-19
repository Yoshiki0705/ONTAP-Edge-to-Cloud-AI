#!/usr/bin/env python3
"""Enumerate every place a SQL string is built, and require each to be reviewed.

Why this exists
---------------
A static scanner's silence is not evidence. bandit reports the f-string shape and
says nothing about a module-level template fed to `.format()`, nor about a value
taken straight from an event and executed. Neither does it look at shell scripts,
which is where the injection actually found in this repository lived:
cloud/clickhouse/scripts/export_training_features.sh interpolated `$1` into both
the SQL text and an S3 object path, so
`./export_training_features.sh "2026-01-01' OR 1=1 --"` was a working injection.

So this does not try to decide whether a site is safe. It finds every site where
SQL meets interpolation, and fails on any that is not recorded in
scripts/reviewed_sql_sites.txt with a verdict. The list is the sweep, written
down: adding a query means classifying its inputs as configuration (env vars,
module constants) or data (event fields, object contents, keys), and data has to
be bound as a parameter or validated against a pattern before it is interpolated.

Athena has no bind parameters, so anything added there must literalise on the
caller's side. There are no Athena calls from Python today — the queries live as
static AWS::Athena::NamedQuery resources — which is why no helper exists yet.

Exit codes: 0 every site reviewed, 1 an unreviewed site or a stale entry.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEWED = REPO_ROOT / "scripts" / "reviewed_sql_sites.txt"

SKIP_DIR_PARTS = {".venv", ".aws-sam", "node_modules", "__pycache__", ".git", ".pytest_cache"}

SQL_KEYWORD = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM|CREATE\s+(TABLE|VIEW|DATABASE)|"
    r"ALTER\s+TABLE|DROP\s+(TABLE|VIEW)|MSCK\s+REPAIR)\b",
    re.I,
)

# Interpolation that could carry a value into the statement.
PY_INTERPOLATION = re.compile(r"""\{[^{}\s"']*\}|%s|\+\s*\w""")
SH_INTERPOLATION = re.compile(r"\$\{?\w+")

# Calls that hand a string to an engine. Used to widen the sweep beyond files
# that happen to contain a SQL keyword on the same line.
EXECUTION_CALL = re.compile(
    r"\b(start_query_execution|QueryString|\.query\(|\.command\(|\.execute\(|"
    r"clickhouse-client|awswrangler\.athena|read_sql)"
)


SELF = Path(__file__).resolve()


def iter_source_files() -> list[Path]:
    files = []
    for pattern in ("*.py", "*.sh", "*.yaml", "*.yml"):
        for path in REPO_ROOT.rglob(pattern):
            if SKIP_DIR_PARTS & set(path.parts):
                continue
            # This file's own regex literals contain SQL keywords and the names of
            # the execution calls it looks for, so without this it counts itself
            # as a site and as a file that executes SQL — which made the
            # "sweep went blind" check fire on a tree that has no SQL at all.
            if path.resolve() == SELF:
                continue
            files.append(path)
    return sorted(files)


WINDOW = 8


def find_sites() -> list[tuple[str, int, str]]:
    """Return (relative path, line number, trimmed line) for candidate sites.

    Matching is per-window, not per-line. A first version tested each line for a
    SQL keyword *and* an interpolation and found zero sites, including in the file
    with the injection that prompted this check: there, `INSERT INTO FUNCTION
    s3(` and `'${ONTAP_S3_ENDPOINT}/...'` and `WHERE toDate(...)` are three
    separate lines. A statement spanning several lines is the normal case, so the
    keyword, the interpolation and the execution call are looked for near each
    other rather than together.
    """
    sites = []
    for path in iter_source_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        interpolation = SH_INTERPOLATION if path.suffix == ".sh" else PY_INTERPOLATION
        rel = path.relative_to(REPO_ROOT).as_posix()

        reported_upto = 0
        for index, line in enumerate(lines, start=1):
            if not SQL_KEYWORD.search(line):
                continue
            if index <= reported_upto:
                continue  # same statement already reported
            low = max(0, index - 1 - WINDOW)
            high = min(len(lines), index + WINDOW)
            window = "\n".join(lines[low:high])
            if interpolation.search(window) and EXECUTION_CALL.search(window):
                sites.append((rel, index, line.strip()[:100]))
                reported_upto = high
    return sites


def reviewed_entries() -> dict[str, str]:
    """Map 'path' -> verdict text. Line numbers are deliberately not recorded."""
    if not REVIEWED.is_file():
        return {}
    entries: dict[str, str] = {}
    for raw in REVIEWED.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        path, _, verdict = line.partition("|")
        entries[path.strip()] = verdict.strip()
    return entries


def files_that_execute_sql() -> set[str]:
    """Files containing both a SQL keyword and an execution call, anywhere.

    Used only to notice that the sweep has stopped finding things it should.
    """
    found = set()
    for path in iter_source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SQL_KEYWORD.search(text) and EXECUTION_CALL.search(text):
            found.add(path.relative_to(REPO_ROOT).as_posix())
    return found


def main() -> int:
    sites = find_sites()
    reviewed = reviewed_entries()

    # Guard the guard. A regex that matches nothing reports "all reviewed", which
    # is indistinguishable from a clean repository. This repo executes SQL from
    # several files; if none are visible to the sweep, the sweep is broken.
    candidates = files_that_execute_sql()
    if candidates and not sites:
        print(
            "the sweep found 0 interpolation sites even though these files execute SQL: "
            f"{sorted(candidates)}. Treat this as a broken check, not a clean result.",
            file=sys.stderr,
        )
        return 1

    problems: list[str] = []
    found_paths = {path for path, _, _ in sites}

    for path, line_number, text in sites:
        if path not in reviewed:
            problems.append(
                f"{path}:{line_number} builds SQL with interpolation and is not in "
                f"{REVIEWED.relative_to(REPO_ROOT)}:\n      {text}"
            )

    stale = sorted(set(reviewed) - found_paths)
    if stale:
        problems.append(
            f"{REVIEWED.relative_to(REPO_ROOT)} records files that no longer build SQL "
            f"with interpolation: {stale}. Remove them, or the list stops describing the code."
        )

    if not problems:
        print(f"SQL interpolation sweep: OK ({len(sites)} sites, all reviewed)")
        return 0

    print("SQL construction sites needing review:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    print(
        "\n  Classify each interpolated value as configuration (env var, module constant) "
        "or data (event field, object contents, key). Data must be bound as a parameter, "
        "or validated against a pattern before interpolation. Then record the file and the "
        f"verdict in {REVIEWED.relative_to(REPO_ROOT)}.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
