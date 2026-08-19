#!/usr/bin/env python3
"""Fail when a test directory exists but nothing runs it.

Why this exists
---------------
Three inventories in this repository list test directories: TEST_DIRS in the
Makefile, testpaths in pyproject.toml, and the `usecase` matrix in
.github/workflows/test.yml. Nothing kept them in agreement. Measured before this
guard: scripts/tests/ was in none of them, and a bare `pytest` collected a
different set than CI did.

The matrix is the part that drifts silently. It names use cases literally, so a
new usecases/<name>/tests/ directory is simply never run — no error, no skipped
job, just absence. A sibling project accumulated 422 tests that way, executed
only when somebody remembered a command from a document.

It also reports test files that exist under two paths with the same basename.
tests/ and usecases/*/tests/ hold three such pairs here, and they have already
drifted: the tests/ copies use `ontap.test.invalid` after a gitleaks fix that the
usecases/ copies never received. Known pairs are recorded in
scripts/known_duplicate_tests.txt so the guard blocks new ones without pretending
the existing debt is resolved.

Exit codes: 0 consistent, 1 a directory or file is unreachable from some runner.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # fixed argv, never a shell string
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = REPO_ROOT / "Makefile"
PYPROJECT = REPO_ROOT / "pyproject.toml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test.yml"
KNOWN_DUPLICATES = REPO_ROOT / "scripts" / "known_duplicate_tests.txt"

SKIP_DIR_PARTS = {".venv", ".aws-sam", "node_modules", "__pycache__", ".git"}


def discover_test_dirs() -> set[str]:
    """Directories that hold at least one file pytest would collect."""
    found = set()
    for path in REPO_ROOT.rglob("test_*.py"):
        if SKIP_DIR_PARTS & set(path.parts):
            continue
        # A file named test_*.py with no test functions is a CLI script, not a
        # suite; counting it would demand coverage that does not exist.
        if not re.search(r"^\s*(?:async\s+)?def test_|^class Test", path.read_text(encoding="utf-8"), re.M):
            continue
        found.add(path.parent.relative_to(REPO_ROOT).as_posix())
    return found


def makefile_test_dirs() -> set[str]:
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^TEST_DIRS\s*:=\s*(.*?)(?=\n[A-Za-z#.]|\n\n)", text, re.S | re.M)
    if not match:
        return set()
    return set(re.sub(r"\\\s*\n\s*", " ", match.group(1)).split())


def pyproject_testpaths() -> set[str]:
    if not PYPROJECT.is_file():
        return set()
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    paths = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("testpaths", [])
    return set(paths)


def workflow_test_invocation() -> tuple[bool, set[str]]:
    """Return (calls a make target, literal usecase names in a matrix)."""
    if not WORKFLOW.is_file():
        return False, set()
    text = WORKFLOW.read_text(encoding="utf-8")
    uses_make = bool(re.search(r"run:\s*.*\bmake\s", text))
    matrix = set()
    match = re.search(r"usecase:\s*\[([^\]]*)\]", text)
    if match:
        matrix = {name.strip() for name in match.group(1).split(",") if name.strip()}
    return uses_make, matrix


def known_duplicates() -> set[str]:
    if not KNOWN_DUPLICATES.is_file():
        return set()
    return {
        line.strip()
        for line in KNOWN_DUPLICATES.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def untracked_tests() -> list[str]:
    """Test files git does not track.

    The sharpest version of "runs nowhere": CI checks out the repository, so a
    test file that is not committed cannot run there no matter what the workflow
    or the Makefile says. Measured here: tests/test_iot_ingestion_lambda.py (12
    tests) and tests/test_s3ap_client.py (13 tests) pass locally and have never
    executed in CI, alongside their untracked source under cloud/iot_ingestion/
    and edge/greengrass/. Locally everything looks covered.
    """
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return sorted(
        path
        for path in result.stdout.split()
        if re.search(r"(^|/)test_[^/]*\.py$", path)
        and not (SKIP_DIR_PARTS & set(Path(path).parts))
    )


def duplicate_basenames() -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}
    for path in REPO_ROOT.rglob("test_*.py"):
        if SKIP_DIR_PARTS & set(path.parts):
            continue
        seen.setdefault(path.name, []).append(path.relative_to(REPO_ROOT).as_posix())
    return {name: paths for name, paths in seen.items() if len(paths) > 1}


def main() -> int:
    problems: list[str] = []
    actual = discover_test_dirs()

    if not actual:
        print(
            "no test directories discovered — the walker is probably broken, which "
            "would make every check below vacuous",
            file=sys.stderr,
        )
        return 1

    declared = makefile_test_dirs()
    missing_from_make = sorted(actual - declared)
    if missing_from_make:
        problems.append(
            f"test directories that exist but are not in Makefile TEST_DIRS, so "
            f"`make test` never runs them: {missing_from_make}"
        )

    stale_in_make = sorted(declared - actual)
    if stale_in_make:
        problems.append(
            f"Makefile TEST_DIRS names directories with no collectable tests: {stale_in_make}"
        )

    testpaths = pyproject_testpaths()
    if testpaths and testpaths != declared:
        problems.append(
            "pyproject.toml testpaths and Makefile TEST_DIRS disagree, so a bare "
            f"`pytest` checks a different set than `make test`: "
            f"only in testpaths={sorted(testpaths - declared)}, "
            f"only in TEST_DIRS={sorted(declared - testpaths)}"
        )

    uses_make, matrix = workflow_test_invocation()
    if not uses_make:
        problems.append(
            ".github/workflows/test.yml does not invoke a make target. CI and local runs "
            "then maintain separate path lists and drift apart; route CI through `make test`."
        )
    if matrix:
        usecase_dirs = {
            path.name for path in (REPO_ROOT / "usecases").iterdir()
            if path.is_dir() and (path / "tests").is_dir()
        } if (REPO_ROOT / "usecases").is_dir() else set()
        unlisted = sorted(usecase_dirs - matrix)
        if unlisted:
            problems.append(
                f"use cases with a tests/ directory that the CI matrix does not name, so "
                f"their tests never run in CI: {unlisted}"
            )

    untracked = untracked_tests()
    if untracked:
        problems.append(
            f"test files git does not track, so CI can never run them however the workflow "
            f"is configured: {untracked}"
        )

    duplicates = duplicate_basenames()
    known = known_duplicates()
    for name, paths in sorted(duplicates.items()):
        if name in known:
            continue
        problems.append(
            f"test file basename '{name}' exists at {paths}. Two copies drift apart and "
            f"pytest's default import mode cannot load both. Either share the module or "
            f"record it in {KNOWN_DUPLICATES.relative_to(REPO_ROOT)} with a reason."
        )

    resolved = sorted(known - set(duplicates))
    if resolved:
        problems.append(
            f"{KNOWN_DUPLICATES.relative_to(REPO_ROOT)} lists basenames that are no longer "
            f"duplicated: {resolved}. Remove them so the file keeps meaning something."
        )

    if not problems:
        print(f"test coverage drift: OK ({len(actual)} test directories, all reachable)")
        return 0

    print("Test inventories disagree:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
