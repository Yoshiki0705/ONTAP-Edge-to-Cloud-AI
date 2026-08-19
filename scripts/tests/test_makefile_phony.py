"""Every Makefile target must be declared .PHONY.

Why this test exists
--------------------
`make <target>` treats the target name as a filename. When a directory of the
same name exists, make finds it, decides it is already up to date, prints
"make: 'security' is up to date." and exits 0 without running the recipe. The
gate looks green and has executed nothing.

This repo is exposed to exactly that: it has directories named docs/, scripts/,
tests/, shared/, cloud/, edge/, usecases/, infrastructure/ and params/, all of
which are plausible target names. In a sibling project `make security` was a
silent no-op for this reason; its first real run reported 9 findings at Medium
or above.

Declaring .PHONY is the fix. This test is what keeps it declared.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"

# A target line: name at column 0, then ':' but not ':=' (that is a variable).
TARGET_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*:(?!=)")
PHONY_RE = re.compile(r"^\.PHONY\s*:\s*(.*)$")

# Targets make defines itself; they are not recipes we own.
SPECIAL = {".PHONY", ".DEFAULT_GOAL", ".SUFFIXES", ".SILENT", ".NOTPARALLEL"}


def _logical_lines(text: str) -> list[str]:
    """Join backslash continuations so multi-line .PHONY is read as one line."""
    joined = re.sub(r"\\\n\s*", " ", text)
    return joined.splitlines()


@pytest.fixture(scope="module")
def makefile_text() -> str:
    assert MAKEFILE.is_file(), f"Makefile not found at {MAKEFILE}"
    return MAKEFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def declared_targets(makefile_text: str) -> set[str]:
    targets = set()
    for line in _logical_lines(makefile_text):
        if line.startswith("\t") or line.lstrip().startswith("#"):
            continue
        if PHONY_RE.match(line):
            continue
        match = TARGET_RE.match(line)
        if match and match.group(1) not in SPECIAL:
            targets.add(match.group(1))
    return targets


@pytest.fixture(scope="module")
def phony_targets(makefile_text: str) -> set[str]:
    phony: set[str] = set()
    for line in _logical_lines(makefile_text):
        match = PHONY_RE.match(line)
        if match:
            phony.update(match.group(1).split())
    return phony


def test_makefile_declares_at_least_one_target(declared_targets):
    """Guard the guard: a parser that finds nothing would pass every assertion."""
    assert len(declared_targets) >= 5, (
        f"only found {sorted(declared_targets)} — the target parser is probably broken, "
        "which would make the .PHONY assertion below vacuous"
    )


def test_every_target_is_phony(declared_targets, phony_targets):
    missing = sorted(declared_targets - phony_targets)
    assert not missing, (
        "these Makefile targets are not in .PHONY, so make will skip their recipe "
        f"whenever a file or directory of the same name exists: {missing}"
    )


def test_no_phony_entry_without_a_target(declared_targets, phony_targets):
    """A stale .PHONY name usually means a target was renamed and left unprotected."""
    orphans = sorted(phony_targets - declared_targets)
    assert not orphans, f".PHONY lists names with no matching target: {orphans}"


def test_targets_colliding_with_real_paths_are_phony(declared_targets, phony_targets):
    """The subset that would fail today, reported separately for a clearer message."""
    colliding = sorted(
        name for name in declared_targets if (REPO_ROOT / name).exists()
    )
    unprotected = [name for name in colliding if name not in phony_targets]
    assert not unprotected, (
        "these target names match an existing path and are not .PHONY, so "
        f"`make <name>` is already a silent no-op: {unprotected}"
    )


def test_ci_invokes_makefile_targets_not_bare_tools():
    """CI must go through the Makefile so both sides check the same paths."""
    workflows = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows, "no workflows found — this test would otherwise be vacuous"
    text = "\n".join(path.read_text(encoding="utf-8") for path in workflows)
    assert "make " in text, (
        "no workflow invokes a Makefile target; CI is running tools directly and "
        "can diverge from local runs"
    )
