#!/usr/bin/env python3
"""Fail when the toolchain can differ between a local run and CI.

Why this exists
---------------
A gate that reports different findings depending on where it runs is not a gate.
Measured in this repository before the fix: `cfn-lint` on PATH was 1.52.1 while
.venv held 1.52.0, and requirements.txt pinned `cfn-lint>=0.87.0` — a range wide
enough to span a major version. ruff and bandit were not pinned anywhere at all,
so whichever build a developer happened to have installed was the one that
decided whether the code passed.

Three things are checked:

  1. requirements-dev.txt uses `==` for every entry. A range means two machines
     can install different linters from the same lockfile.
  2. The Python version CI installs matches the Lambda runtime the templates
     declare. These drifted here: .venv is 3.14, while the workflow and every
     `Runtime:` line say 3.12, so a syntax or stdlib difference would only show up
     after deploying.
  3. Workflows install tooling through requirements-dev.txt rather than naming
     versions inline, so bumping a pin updates both sides in one commit.

Exit codes: 0 consistent, 1 a divergence that can produce different verdicts.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_REQUIREMENTS = REPO_ROOT / "requirements-dev.txt"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# Tools whose version changes the verdict of a gate.
GATE_TOOLS = {"ruff", "bandit", "cfn-lint", "pytest", "pre-commit"}


def parse_requirements(path: Path) -> list[tuple[str, str]]:
    entries = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9._-]+)\s*(.*)$", line)
        if match:
            entries.append((match.group(1).lower(), match.group(2).strip()))
    return entries


def check_dev_pins(problems: list[str]) -> None:
    if not DEV_REQUIREMENTS.is_file():
        problems.append(
            "requirements-dev.txt is missing; gate tooling versions are then whatever "
            "each machine happens to have installed."
        )
        return

    entries = parse_requirements(DEV_REQUIREMENTS)
    if not entries:
        problems.append("requirements-dev.txt parsed to zero entries — check the parser.")
        return

    for name, spec in entries:
        if not spec.startswith("=="):
            problems.append(
                f"requirements-dev.txt pins {name} as '{spec or '(unconstrained)'}'. "
                f"Use == so local and CI resolve to the same build."
            )

    pinned = {name for name, _ in entries}
    for tool in sorted(GATE_TOOLS - pinned):
        problems.append(
            f"{tool} decides whether a gate passes but is not pinned in requirements-dev.txt."
        )


def lambda_runtimes() -> set[str]:
    versions = set()
    for template in list(REPO_ROOT.glob("cloud/*/template.yaml")) + list(
        REPO_ROOT.glob("usecases/*/template.yaml")
    ):
        for match in re.finditer(r"Runtime:\s*python([\d.]+)", template.read_text(encoding="utf-8")):
            versions.add(match.group(1))
    return versions


def ci_python_versions() -> set[str]:
    versions = set()
    if not WORKFLOWS.is_dir():
        return versions
    for workflow in WORKFLOWS.glob("*.yml"):
        for match in re.finditer(
            r"python-version:\s*[\"']?([\d.]+)[\"']?", workflow.read_text(encoding="utf-8")
        ):
            versions.add(match.group(1))
    return versions


def check_python_versions(problems: list[str]) -> None:
    runtimes = lambda_runtimes()
    ci_versions = ci_python_versions()
    if not runtimes or not ci_versions:
        return
    if not runtimes & ci_versions:
        problems.append(
            f"CI tests on Python {sorted(ci_versions)} but the Lambda templates declare "
            f"python{sorted(runtimes)}. Tests then pass on an interpreter that never runs "
            f"the code."
        )

    local = f"{sys.version_info.major}.{sys.version_info.minor}"
    if local not in runtimes:
        # A warning, not a failure: a contributor's interpreter is not the gate.
        # It is still the most common reason a local pass differs from CI.
        print(
            f"NOTE: this interpreter is Python {local}; the Lambda runtime is "
            f"python{sorted(runtimes)}. `make test` is not exercising the deployed version.",
        )


def check_ci_installs_from_requirements(problems: list[str]) -> None:
    if not WORKFLOWS.is_dir():
        return
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for match in re.finditer(r"pip install ([^\n|]+)", text):
            args = match.group(1).strip()
            if "-r " in args:
                continue
            named = {
                token.split("==")[0].split(">=")[0].strip().lower()
                for token in args.split()
                if not token.startswith("-")
            }
            overlap = named & GATE_TOOLS
            if overlap:
                problems.append(
                    f"{workflow.name} installs {sorted(overlap)} inline (`pip install {args}`). "
                    f"Install from requirements-dev.txt instead so a version bump lands in "
                    f"both places at once."
                )


def main() -> int:
    problems: list[str] = []
    check_dev_pins(problems)
    check_python_versions(problems)
    check_ci_installs_from_requirements(problems)

    if not problems:
        print("dependency pins: OK")
        return 0

    print("Toolchain can differ between local and CI:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
