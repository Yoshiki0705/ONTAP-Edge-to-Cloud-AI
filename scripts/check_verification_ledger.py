#!/usr/bin/env python3
"""Fail when the verification ledger stops describing what the repository ships.

Why this exists
---------------
docs/{ja,en}/verification-status.md is the only place that separates what ran on real AWS
from what merely passes unit tests. Its value depends entirely on staying true, and every
way it can quietly stop being true is invisible:

  1. **A model changes underneath the measurement.** The ledger records that the two-stage
     Bedrock figures were obtained with specific inference profiles. Bump the default in
     `handler.py` or a template and those numbers no longer describe the shipped
     configuration — but they keep reading as current, because nothing connects the two.
     This is the check that matters most: the Bedrock run is the repository's only
     measured evidence, and the `jp.` prefix is a cross-Region inference profile, so a
     changed prefix is a different path and different billing, not a cosmetic edit.
  2. **A basis link rots.** A row claiming `tests/` as its evidence is worthless once that
     path is gone, and a moved file makes every row above it look supported.
  3. **The two languages drift by rows, not by headings.** check_doc_parity.py compares
     heading levels, so a stage added to one language's table and not the other passes it.
  4. **A tier gets invented.** A fifth tier name defeats the point of borrowing published
     vocabulary, and reads as though it were part of it.

What it cannot check: whether a row's tier is honest. Nothing here can tell that a stage
marked "real hardware" never ran. That is a claim about the world, and the only defence is
the promotion rule in the ledger itself.

Exit codes: 0 the ledger is consistent with the tree, 1 something drifted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGERS = {
    "ja": REPO_ROOT / "docs" / "ja" / "verification-status.md",
    "en": REPO_ROOT / "docs" / "en" / "verification-status.md",
}

# Where a model ID may legitimately live: what ships, or what deploys.
CODE_GLOBS = ("cloud/**/*.py", "edge/**/*.py", "usecases/**/template.yaml",
              "cloud/**/template.yaml")

# A Bedrock model ID or inference profile, e.g. jp.anthropic.claude-haiku-4-5-20251001-v1:0
MODEL_ID = re.compile(r"\b((?:[a-z]{2}\.)?(?:anthropic|amazon|meta|mistral)\.[a-z0-9.-]+-v\d+:\d+)")

# The tiers the ledger is allowed to use, per the two published vocabularies it borrows.
CODE_TIERS = {
    "実機 E2E", "実機 単体", "自動テストのみ", "ローカルのみ", "未実行",
    "Real hardware, end-to-end", "Real hardware, single stage", "Unit tests only",
    "Local only", "Not run",
}
EVIDENCE_TIERS = {"verified", "documented", "field-observation", "hypothesis"}

LINK = re.compile(r"\[[^\]]*\]\(([^)#]+)(?:#[^)]*)?\)")
TABLE_ROW = re.compile(r"^\|(?!\s*[-: ]+\|)(.+)\|\s*$")


def table_rows(text: str) -> list[str]:
    """Body rows of every markdown table, excluding header separators."""
    return [m.group(1) for line in text.splitlines() if (m := TABLE_ROW.match(line))]


def main() -> int:
    problems: list[str] = []

    for path in LEDGERS.values():
        if not path.is_file():
            problems.append(f"{path.relative_to(REPO_ROOT)}: missing")
    if problems:
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    texts = {lang: p.read_text(encoding="utf-8") for lang, p in LEDGERS.items()}

    # 3. Row-count parity, which the heading-level guard cannot see.
    counts = {lang: len(table_rows(text)) for lang, text in texts.items()}
    if counts["ja"] != counts["en"]:
        problems.append(
            f"table rows differ: ja has {counts['ja']}, en has {counts['en']}. "
            f"A stage or claim was added to one language only."
        )

    # 2. Every basis link resolves.
    for language, path in LEDGERS.items():
        for match in LINK.finditer(texts[language]):
            href = match.group(1)
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            if not (path.parent / href).resolve().exists():
                problems.append(
                    f"{path.relative_to(REPO_ROOT)}: basis link does not resolve: {href}"
                )

    # 1. Every model ID cited as measured still appears in what ships.
    shipped: set[str] = set()
    for pattern in CODE_GLOBS:
        for source in REPO_ROOT.glob(pattern):
            if ".venv" in source.parts or ".aws-sam" in source.parts:
                continue
            shipped.update(MODEL_ID.findall(source.read_text(encoding="utf-8")))

    cited = {model for text in texts.values() for model in MODEL_ID.findall(text)}
    if not cited:
        problems.append(
            "no model ID is cited in the ledger. The Bedrock measurement is the only "
            "measured evidence here; recording it without the profile it used makes the "
            "numbers uncheckable."
        )
    for model in sorted(cited - shipped):
        problems.append(
            f"{model} is cited as measured but no longer appears in the code or templates. "
            f"Either re-measure against what ships, or demote the row."
        )

    # 4. No invented tier.
    allowed = CODE_TIERS | EVIDENCE_TIERS
    for language, text in texts.items():
        for row in table_rows(text):
            cells = [cell.strip().strip("*`") for cell in row.split("|")]
            for cell in cells:
                bare = cell.strip("*` ")
                if bare in allowed or not bare:
                    continue
                # Only judge cells that look like a tier: short, and in a tier-ish shape.
                if bare in {"—", "-"} or len(bare) > 32:
                    continue
                if re.fullmatch(r"[a-z-]+", bare) and bare not in EVIDENCE_TIERS:
                    if bare in {"ja", "en", "verified-on"}:
                        continue
                    problems.append(
                        f"docs/{language}/verification-status.md: '{bare}' is not one of "
                        f"the borrowed tiers. Do not add a fifth."
                    )

    if problems:
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(f"verification ledger: {len(problems)} problem(s)", file=sys.stderr)
        return 1

    print(
        f"verification ledger: OK ({counts['ja']} rows in each language, "
        f"{len(cited)} model ID(s) cited, all present in the tree)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
