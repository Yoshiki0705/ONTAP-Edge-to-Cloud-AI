#!/usr/bin/env python3
"""Fail when the committed architecture diagrams have drifted from their build.

Why this exists
---------------
scripts/build_diagrams.py already refuses to finish on a missing icon, an untranslated
label or unparseable XML. None of that runs in CI: the build needs the AWS icon package,
which is deliberately not in this repository, and the draw.io desktop app to export. So
every one of those guarantees holds only on the machine that last ran the build, and
nothing notices when the committed artifacts stop matching it.

What is checked here is the subset that needs no icons and no renderer:

  1. No icon-library file has been committed. AWS licenses the assets for use in a
     diagram, not for redistribution, so `Arch_*`, `Res_*` and the package directory
     must never appear in the tree.
  2. Every figure has all six artifacts. Editing the build and rerunning it without
     --export leaves the `.drawio` newer than the `.svg` and `.png` that the documents
     actually embed, and the documents keep rendering the stale picture.
  3. No Japanese character survives in an English artifact. This is the one failure the
     build's own residue gate cannot catch retroactively: a label added to LABELS
     incorrectly, or a `.drawio` hand-edited after generation, shows up here.

What it cannot check: whether the `.svg` was exported from the `.drawio` beside it. Git
stores no timestamps and there is no renderer available, so a `.drawio` change committed
without a re-export passes item 2 as long as the old files exist. Look at the PNG.

Exit codes: 0 the artifacts are consistent, 1 something drifted.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET  # nosec B405  # noqa: S405  parsing our own output
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DIAGRAM_DIR = REPO_ROOT / "docs" / "diagrams"
IMAGE_DIR = REPO_ROOT / "docs" / "images"
PNG_DIR = IMAGE_DIR / "png"

FIGURES = (
    "architecture-overview",
    "pattern-01-edge-ai-bedrock",
    "pattern-05-agentic-rag",
)

SKIP_DIR_PARTS = {".venv", ".aws-sam", "node_modules", "__pycache__", ".git", ".private"}
ICON_LIBRARY = re.compile(r"^(Arch_|Res_|Icon-package)")
# U+203B (※) is outside every CJK block and would otherwise pass unnoticed.
CJK = re.compile(r"[\u203b\u3000-\u303f\u3040-\u30ff\u4e00-\u9fff\uff00-\uffef]")


def committed_icon_library() -> list[str]:
    found = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or SKIP_DIR_PARTS & set(path.parts):
            continue
        if ICON_LIBRARY.match(path.name):
            found.append(path.relative_to(REPO_ROOT).as_posix())
    return sorted(found)


def expected_artifacts(figure: str) -> list[Path]:
    return [
        DIAGRAM_DIR / f"{figure}.drawio",
        DIAGRAM_DIR / f"{figure}-en.drawio",
        IMAGE_DIR / f"{figure}.svg",
        IMAGE_DIR / f"{figure}-en.svg",
        PNG_DIR / f"{figure}@2x.png",
        PNG_DIR / f"{figure}-en@2x.png",
    ]


def main() -> int:
    problems: list[str] = []

    for relative in committed_icon_library():
        problems.append(
            f"{relative}: icon-library file committed. The AWS icon package is licensed "
            f"for use in diagrams, not for redistribution; keep it outside the repo."
        )

    checked = 0
    for figure in FIGURES:
        for path in expected_artifacts(figure):
            relative = path.relative_to(REPO_ROOT).as_posix()
            if not path.is_file():
                problems.append(f"{relative}: missing. Rebuild with --export.")
                continue
            if path.stat().st_size == 0:
                problems.append(f"{relative}: empty.")
                continue
            checked += 1

            if path.suffix == ".drawio":
                try:
                    ET.parse(path)  # nosec B314  # noqa: S314  our own generated file
                except ET.ParseError as error:
                    problems.append(f"{relative}: not well-formed XML ({error})")

            if "-en" in path.stem and path.suffix in (".drawio", ".svg"):
                residue = sorted(set(CJK.findall(path.read_text(encoding="utf-8"))))
                if residue:
                    problems.append(
                        f"{relative}: {len(residue)} Japanese character(s) remain in an "
                        f"English artifact: {''.join(residue[:20])}"
                    )

    if problems:
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(f"diagram assets: {len(problems)} problem(s)", file=sys.stderr)
        return 1

    print(f"diagram assets: OK ({len(FIGURES)} figures, {checked} artifacts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
