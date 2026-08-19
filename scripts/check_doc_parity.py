#!/usr/bin/env python3
"""Fail when a bilingual document pair has drifted apart structurally.

Why this exists
---------------
AGENTS.md requires `docs/ja/` and `docs/en/` to keep matching `## ` structure and
to change in the same commit. Nothing enforced it. Measured when this guard was
written: the pairs agreed at the `## ` level but not below it — the English
iot-greengrass-flexcache-integration.md was missing a `###` subsection its
Japanese counterpart has, and s3ap-service-gap-analysis-and-feature-request.md
had a different `###` breakdown in each language with two subsections in the
reverse order. Section counts alone would have called both of those fine.

What is compared, and why not more
----------------------------------
The sequence of heading *levels* — [2, 3, 3, 2, ...] — not the heading text.
Translated headings never match as strings, so text equality would fail on every
file and text similarity would need a translation memory to mean anything. The
level sequence is language-independent and still catches the defect that matters:
a section or subsection present in one language and absent in the other.

Three naming conventions exist here and all are checked:
  docs/ja/X.md  <-> docs/en/X.md      (the reference documents)
  Y.md          <-> Y_en.md           (root README/TESTING, docs/agent/)
  Y.md          <-> Y_ja.md           (edge/soracom/, where English is primary)

The third was found after the first version shipped: edge/soracom/README.md pairs
with README_ja.md, the opposite suffix direction, and went unchecked. A guard is
only as wide as the paths it walks, and that is not visible in its output.

Existing drift is recorded in scripts/known_doc_parity_gaps.txt rather than
waived in code, so the guard blocks new drift without asserting that the current
debt is repaired. An entry that no longer drifts is reported too — a stale
allowlist is how a guard quietly stops guarding.

Exit codes: 0 pairs agree, 1 a pair drifted or is missing a side.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
KNOWN_GAPS = REPO_ROOT / "scripts" / "known_doc_parity_gaps.txt"

# docs/demo-guides/ is English-only. It is a set of step-by-step runbooks whose
# role overlaps usecases/*/demo-guide.md, and consolidating the three demo
# families is deferred; translating them before deciding which survives would be
# work thrown away. Excluded until that decision is made, not because
# English-only is acceptable in general.
EXCLUDED = ("docs/demo-guides/",)

SKIP_DIR_PARTS = {".venv", ".aws-sam", "node_modules", "__pycache__", ".git", ".kiro", ".private"}

HEADING = re.compile(r"^(#{1,6})\s+\S")
FENCE = re.compile(r"^\s*(```|~~~)")


def heading_levels(path: Path) -> list[int]:
    """Heading levels in document order, ignoring anything inside a code fence.

    A fenced block can contain '### ' as shell output or as an example, and
    counting those would make the comparison depend on how the examples were
    written rather than on the document's structure.
    """
    levels: list[int] = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING.match(line)
        if match:
            levels.append(len(match.group(1)))
    return levels


def is_excluded(relative: str) -> bool:
    return any(relative.startswith(prefix) for prefix in EXCLUDED)


def discover_pairs() -> tuple[list[tuple[str, Path, Path]], list[str]]:
    """Return (pairs, one-sided) for both bilingual conventions."""
    pairs: list[tuple[str, Path, Path]] = []
    one_sided: list[str] = []

    ja_dir, en_dir = DOCS / "ja", DOCS / "en"
    if ja_dir.is_dir() and en_dir.is_dir():
        for source, mirror in ((ja_dir, en_dir), (en_dir, ja_dir)):
            for path in sorted(source.rglob("*.md")):
                relative = path.relative_to(REPO_ROOT).as_posix()
                if is_excluded(relative):
                    continue
                counterpart = mirror / path.relative_to(source)
                if not counterpart.is_file():
                    one_sided.append(
                        f"{relative} has no counterpart at "
                        f"{counterpart.relative_to(REPO_ROOT).as_posix()}"
                    )
                elif source is ja_dir:
                    pairs.append((relative, path, counterpart))

    for suffix in ("_en.md", "_ja.md"):
        for path in sorted(REPO_ROOT.rglob(f"*{suffix}")):
            if SKIP_DIR_PARTS & set(path.parts):
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            if is_excluded(relative) or relative.startswith(("docs/en/", "docs/ja/")):
                continue
            primary = path.with_name(path.name.removesuffix(suffix) + ".md")
            if not primary.is_file():
                one_sided.append(
                    f"{relative} has no primary-language counterpart at "
                    f"{primary.relative_to(REPO_ROOT).as_posix()}"
                )
            else:
                pairs.append((primary.relative_to(REPO_ROOT).as_posix(), primary, path))

    return pairs, one_sided


def known_gaps() -> set[str]:
    if not KNOWN_GAPS.is_file():
        return set()
    return {
        line.split("#", 1)[0].strip()
        for line in KNOWN_GAPS.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    }


def describe(primary: list[int], mirror: list[int]) -> str:
    """Where the two sequences first diverge, in terms a reader can act on."""
    # strict=False is deliberate: the sequences differ in length whenever a section
    # is missing, which is the case this function exists to describe.
    for index, (left, right) in enumerate(zip(primary, mirror, strict=False)):
        if left != right:
            return (
                f"level sequences diverge at heading {index + 1}: "
                f"primary has h{left}, translation has h{right}"
            )
    longer, side = (
        (primary, "primary") if len(primary) > len(mirror) else (mirror, "translation")
    )
    extra = longer[min(len(primary), len(mirror)) :]
    return f"{side} has {len(extra)} extra trailing heading(s) at level(s) {extra}"


def main() -> int:
    pairs, one_sided = discover_pairs()

    if not pairs:
        print(
            "no bilingual document pairs discovered — the walker is probably broken, "
            "which would make this check vacuous",
            file=sys.stderr,
        )
        return 1

    known = known_gaps()
    problems = list(one_sided)
    drifted: set[str] = set()

    for relative, primary_path, mirror_path in pairs:
        primary = heading_levels(primary_path)
        mirror = heading_levels(mirror_path)
        if primary == mirror:
            continue
        drifted.add(relative)
        if relative in known:
            continue
        counts = (
            f"primary {len(primary)} headings, translation {len(mirror)}"
            if len(primary) != len(mirror)
            else f"{len(primary)} headings each"
        )
        problems.append(
            f"{relative}: {counts}; {describe(primary, mirror)}. Add or remove the "
            f"section so both languages carry the same structure, or record the pair "
            f"in {KNOWN_GAPS.relative_to(REPO_ROOT)} with a reason."
        )

    resolved = sorted(known - drifted)
    if resolved:
        problems.append(
            f"{KNOWN_GAPS.relative_to(REPO_ROOT)} lists pairs that no longer drift: "
            f"{resolved}. Remove them so the file keeps meaning something."
        )

    if not problems:
        print(f"doc parity: OK ({len(pairs)} bilingual pairs, {len(known)} known gaps)")
        return 0

    print("Bilingual document pairs disagree:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
