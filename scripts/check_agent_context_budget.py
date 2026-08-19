#!/usr/bin/env python3
"""Keep always-loaded agent context small, and keep its index honest.

Why this exists
---------------
AGENTS.md is read on every turn and cannot be made conditional. Anything in it
that only matters for one kind of work is paid for on every other kind. The
counterpressure is real, though: material moved out of AGENTS.md has to stay
findable, and `.kiro/` is gitignored here, so moving prose into `.kiro/steering/`
deletes it from the published repository while appearing to preserve it.

The arrangement this enforces:

  AGENTS.md          — always-true rules, plus a one-line index per topic
  docs/agent/*.md    — the content, git-tracked, published
  .kiro/steering/*   — thin loaders that say when to read, nothing more

Four ways it goes wrong, none of which produce an error on their own:

  1. AGENTS.md grows back and the per-turn cost returns.
  2. A loader accumulates content, so the knowledge exists only in a gitignored
     file and vanishes for anyone cloning the repository.
  3. A loader points at a document that has been moved or renamed.
  4. A loader's target is not tracked by git, so it is invisible on GitHub.

Exit codes: 0 within budget, 1 over budget or an unreachable index target.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # fixed argv, never a shell string
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS = REPO_ROOT / "AGENTS.md"
STEERING = REPO_ROOT / ".kiro" / "steering"
AGENT_DOCS = REPO_ROOT / "docs" / "agent"

# AGENTS.md was 4,105 bytes when this guard was written and is now smaller.
# The ceiling leaves room for genuinely always-true rules without room for a
# procedure. Raising it should take an argument, not a commit.
AGENTS_MAX_BYTES = 6_000

# A loader is front matter plus a pointer. Anything larger is content.
LOADER_MAX_BYTES = 1_200

# Body lines excluding front matter; a pointer does not need many.
LOADER_MAX_BODY_LINES = 12

MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def tracked_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return set(result.stdout.split())


def front_matter_bounds(text: str) -> int:
    """Return the index just past the closing front-matter delimiter, or 0."""
    if not text.startswith("---"):
        return 0
    end = text.find("\n---", 3)
    return 0 if end == -1 else end + 4


def check_agents_size(problems: list[str]) -> None:
    if not AGENTS.is_file():
        problems.append("AGENTS.md is missing.")
        return
    size = AGENTS.stat().st_size
    if size > AGENTS_MAX_BYTES:
        problems.append(
            f"AGENTS.md is {size:,} bytes, over the {AGENTS_MAX_BYTES:,} byte budget. It is "
            f"read on every turn. Move the work-specific part to docs/agent/ and leave one "
            f"index line."
        )


def check_agents_links(problems: list[str], tracked: set[str]) -> None:
    """Every path AGENTS.md points at must exist and be published."""
    if not AGENTS.is_file():
        return
    for target in MARKDOWN_LINK.findall(AGENTS.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "#")):
            continue
        clean = target.split("#", 1)[0]
        resolved = (REPO_ROOT / clean).resolve()
        rel = clean.lstrip("./")
        if not resolved.exists():
            problems.append(f"AGENTS.md links to {target}, which does not exist.")
        elif rel not in tracked:
            problems.append(
                f"AGENTS.md links to {target}, which git does not track. Readers cloning "
                f"the repository cannot open it."
            )


def check_loaders(problems: list[str], tracked: set[str]) -> None:
    if not STEERING.is_dir():
        # Legal: a repository need not have workspace steering. Global steering
        # still applies. Nothing to verify.
        return

    for path in sorted(STEERING.glob("*.md")):
        where = f".kiro/steering/{path.name}"
        text = path.read_text(encoding="utf-8")
        size = path.stat().st_size

        body_start = front_matter_bounds(text)
        if body_start == 0:
            problems.append(
                f"{where}: no front matter. Without `inclusion`, `name` and `description` "
                f"Kiro does not register the file and never loads it."
            )
            continue

        head = text[:body_start]
        if "inclusion: auto" in head:
            for field in ("name:", "description:"):
                if field not in head:
                    problems.append(
                        f"{where}: inclusion:auto without `{field.rstrip(':')}`. The file is "
                        f"not registered and is never read; no error is produced."
                    )

        if size > LOADER_MAX_BYTES:
            problems.append(
                f"{where} is {size:,} bytes, over the {LOADER_MAX_BYTES:,} byte loader "
                f"budget. .kiro/ is gitignored, so content here is absent from the "
                f"published repository. Move it to docs/agent/ and link."
            )

        body_lines = [line for line in text[body_start:].splitlines() if line.strip()]
        if len(body_lines) > LOADER_MAX_BODY_LINES:
            problems.append(
                f"{where} has {len(body_lines)} body lines, over {LOADER_MAX_BODY_LINES}. "
                f"A loader states when to read something; it does not carry the content."
            )

        targets = [
            t for t in MARKDOWN_LINK.findall(text[body_start:])
            if not t.startswith(("http://", "https://", "#"))
        ]
        if not targets:
            problems.append(
                f"{where} links to no document. A loader with nothing to point at is "
                f"content in disguise."
            )
        for target in targets:
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            if not resolved.exists():
                problems.append(f"{where} points at {target}, which does not exist.")
                continue
            try:
                rel = resolved.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                problems.append(f"{where} points outside the repository: {target}")
                continue
            if rel not in tracked:
                problems.append(
                    f"{where} points at {rel}, which git does not track. The knowledge would "
                    f"exist only on this machine."
                )


def check_agent_docs_are_indexed(problems: list[str]) -> None:
    """A document nobody links to is a document nobody reads."""
    if not AGENT_DOCS.is_dir() or not AGENTS.is_file():
        return
    agents_text = AGENTS.read_text(encoding="utf-8")
    steering_text = "".join(
        path.read_text(encoding="utf-8") for path in STEERING.glob("*.md")
    ) if STEERING.is_dir() else ""

    for doc in sorted(AGENT_DOCS.glob("*.md")):
        name = doc.name
        # English mirrors are reached from their Japanese counterpart.
        if name.endswith("_en.md"):
            counterpart = AGENT_DOCS / name.replace("_en.md", ".md")
            if counterpart.is_file() and name in counterpart.read_text(encoding="utf-8"):
                continue
        if name in agents_text or name in steering_text:
            continue
        problems.append(
            f"docs/agent/{name} is referenced from neither AGENTS.md nor a .kiro/steering "
            f"loader, so nothing will cause it to be read."
        )


def main() -> int:
    problems: list[str] = []
    tracked = tracked_files()
    if not tracked:
        print(
            "git ls-files returned nothing; the tracked-file checks would be vacuous.",
            file=sys.stderr,
        )
        return 1

    check_agents_size(problems)
    check_agents_links(problems, tracked)
    check_loaders(problems, tracked)
    check_agent_docs_are_indexed(problems)

    if not problems:
        size = AGENTS.stat().st_size
        loaders = len(list(STEERING.glob("*.md"))) if STEERING.is_dir() else 0
        print(
            f"agent context budget: OK (AGENTS.md {size:,}/{AGENTS_MAX_BYTES:,} bytes, "
            f"{loaders} loaders)"
        )
        return 0

    print("Always-loaded context or its index needs attention:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
