#!/usr/bin/env python3
"""Fail when a documented local gate cannot fire.

Why this exists
---------------
AGENTS.md states that a pre-commit hook runs author-email verification, gitleaks
and zizmor "automatically (via .githooks/pre-commit)". Measured in this
repository: `git config core.hooksPath` returns
`/Users/<user>/.config/git/hooks`. A global core.hooksPath replaces the
per-repository hook path entirely, so `.githooks/pre-commit` had never executed.
The global hook does run a secret scan, with a different config file, and does
not check the author email or lint workflows at all.

`.pre-commit-config.yaml` was in the same state: the `pre-commit` CLI is not
installed, `.git/hooks/` contains no installed hook, and no workflow invokes
`pre-commit run`. Six configured checks were executing nowhere.

Neither situation produces an error. Both make the repository look protected.

Exit codes: 0 all wired, 1 a documented gate cannot fire.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404  # fixed argv, never a shell string
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_HOOKS_DIR = ".githooks"


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def check_hooks_path(problems: list[str]) -> None:
    """`.githooks/` must be the active hook path if it exists."""
    hooks_dir = REPO_ROOT / REPO_HOOKS_DIR
    if not hooks_dir.is_dir():
        return

    configured = _git("config", "core.hooksPath")
    if configured == REPO_HOOKS_DIR:
        return

    scripts = sorted(p.name for p in hooks_dir.iterdir() if p.is_file())
    if not configured:
        problems.append(
            f"{REPO_HOOKS_DIR}/ contains {scripts} but core.hooksPath is unset, so git "
            f"uses .git/hooks/ instead and these never run. Fix: make precommit-install"
        )
        return

    problems.append(
        f"core.hooksPath is '{configured}', which overrides {REPO_HOOKS_DIR}/. The "
        f"repository hooks {scripts} never execute — including the author-email check, "
        f"the scan against this repo's .gitleaks.toml, and the drift guards that "
        f"docs/agent/supply-chain-security.md describes as running on every commit. "
        f"Fix: make precommit-install (per-repo; your global default still applies "
        f"elsewhere, and .githooks/pre-commit delegates to it)."
    )


def check_precommit_framework(problems: list[str]) -> None:
    """A .pre-commit-config.yaml that nothing runs is worse than none."""
    config = REPO_ROOT / ".pre-commit-config.yaml"
    if not config.is_file():
        return

    cli_available = shutil.which("pre-commit") is not None
    installed_hook = (REPO_ROOT / ".git" / "hooks" / "pre-commit").is_file()
    hooks_path = _git("config", "core.hooksPath")
    # `pre-commit install` writes into whichever path core.hooksPath names.
    if hooks_path:
        installed_hook = installed_hook or (Path(hooks_path).expanduser() / "pre-commit").is_file()

    workflows = REPO_ROOT / ".github" / "workflows"
    in_ci = any(
        "pre-commit" in path.read_text(encoding="utf-8")
        for path in workflows.glob("*.yml")
    ) if workflows.is_dir() else False

    if not cli_available and not in_ci:
        problems.append(
            ".pre-commit-config.yaml exists, the pre-commit CLI is not installed, and no "
            "workflow runs `pre-commit run`. Every hook it configures executes nowhere. "
            "Fix: either add a CI job that runs `pre-commit run --all-files`, or delete "
            "the config so it stops implying coverage."
        )
        return

    if cli_available and not installed_hook and not in_ci:
        problems.append(
            ".pre-commit-config.yaml exists and the CLI is installed, but no pre-commit "
            "hook is installed and no workflow runs it. Fix: pre-commit install"
        )


def check_documented_gates_exist(problems: list[str]) -> None:
    """AGENTS.md names commands; the things they need must be present."""
    agents = REPO_ROOT / "AGENTS.md"
    if not agents.is_file():
        return
    text = agents.read_text(encoding="utf-8")
    for referenced in (".gitleaks.toml", ".githooks/pre-commit"):
        if referenced in text and not (REPO_ROOT / referenced).exists():
            problems.append(
                f"AGENTS.md references {referenced}, which does not exist."
            )


def main() -> int:
    problems: list[str] = []
    check_hooks_path(problems)
    check_precommit_framework(problems)
    check_documented_gates_exist(problems)

    if not problems:
        print("git hooks wiring: OK")
        return 0

    print("Local gates that cannot fire:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
