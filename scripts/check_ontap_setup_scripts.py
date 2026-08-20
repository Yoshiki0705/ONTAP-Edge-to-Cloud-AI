#!/usr/bin/env python3
"""Fail when a use case's ONTAP setup script emits commands that do not hold together.

Why this exists
---------------
`usecases/*/ontap-setup.sh` does not configure anything. Each one prints a block of ONTAP
CLI commands for an operator to paste into an SSH session, which means the block is the
deliverable and nothing executes it — so nothing catches a block that cannot work. Two
defects of that shape shipped:

  * `ontap-telemetry-analytics` emitted `export-policy rule create -policyname iot-devices`
    without an `export-policy create` for it. On a fresh SVM that fails: the policy does not
    exist. It only appeared to work because `3d-print-quality`'s script creates the same
    policy, so whoever ran that one first never saw it. The dependency was not written down
    in either script.
  * `3d-print-quality` emitted `fpolicy policy event create` as the single live command in
    an otherwise commented-out optional section. Pasting it left an `img-create` event on
    the SVM that no policy referenced, because the engine, policy and enable lines were all
    comments.

Both are the same class: an object is referenced without being created, or created without
being referenced. This guard reads what each script *prints* -- the heredoc body, ignoring
commented lines the way an operator pasting them would -- and checks both directions.

What it cannot check: whether the commands are correct ONTAP syntax, or whether they suit
the volume layout a use case actually needs. It only checks that the block is internally
consistent with itself.

Exit codes: 0 the blocks hold together, 1 one does not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPTS = "usecases/*/ontap-setup.sh"

# An operator pastes what is printed. A commented line is not printed as a command, so it
# neither creates nor consumes anything.
HEREDOC = re.compile(r"cat\s*<<\s*'?(\w+)'?\n(.*?)\n\1", re.S)


def emitted_commands(script: Path) -> list[str]:
    """The lines an operator would actually run, joined across backslash continuations."""
    text = script.read_text(encoding="utf-8")
    body = "\n".join(match.group(2) for match in HEREDOC.finditer(text))
    if not body:
        return []
    # Join continuations first: a `\`-terminated line carries its arguments on the next.
    joined = re.sub(r"\\\n\s*", " ", body)
    return [
        line.strip()
        for line in joined.split("\n")
        if line.strip() and not line.strip().startswith("#")
    ]


def named(commands: list[str], verb: str, flag: str) -> set[str]:
    """Values of `flag` on every command matching `verb`."""
    found = set()
    pattern = re.compile(rf"{re.escape(flag)}\s+(\S+)")
    for command in commands:
        if not re.search(rf"\b{verb}\b", command):
            continue
        match = pattern.search(command)
        if match:
            found.add(match.group(1))
    return found


def main() -> int:
    problems: list[str] = []
    scripts = sorted(REPO_ROOT.glob(SETUP_SCRIPTS))
    if not scripts:
        print(
            f"  no scripts matched {SETUP_SCRIPTS}; this guard would pass vacuously",
            file=sys.stderr,
        )
        return 1

    checked = 0
    for script in scripts:
        label = script.relative_to(REPO_ROOT)
        commands = emitted_commands(script)
        if not commands:
            problems.append(
                f"{label}: no commands found inside a heredoc. Either the script stopped "
                f"printing a command block or this guard can no longer find it."
            )
            continue
        checked += 1

        # --- export policies -----------------------------------------------------------
        created = named(commands, "export-policy create", "-policyname")
        used = named(commands, "export-policy rule create", "-policyname")
        used |= named(commands, "vol modify", "-policy")
        for policy in sorted(used - created):
            problems.append(
                f"{label}: uses export policy {policy!r} but never creates it. Pasted into "
                f"a fresh SVM this fails. Add the `export-policy create`, noting that it "
                f"errors if another use case created the policy first."
            )

        # --- FPolicy events ------------------------------------------------------------
        events_created = named(commands, "fpolicy policy event create", "-event-name")
        events_used = named(commands, "fpolicy policy create", "-events")
        for event in sorted(events_created - events_used):
            problems.append(
                f"{label}: creates FPolicy event {event!r} and no emitted `fpolicy policy "
                f"create` references it. Pasting this leaves an event on the SVM that "
                f"nothing consumes. Either emit the policy too, or comment the event out "
                f"with the rest of the optional section."
            )
        for event in sorted(events_used - events_created):
            problems.append(
                f"{label}: an emitted FPolicy policy references event {event!r}, which no "
                f"emitted command creates."
            )

        # --- volumes -------------------------------------------------------------------
        volumes_created = named(commands, "vol create", "-volume")
        volumes_touched = named(commands, "vol modify", "-volume")
        for volume in sorted(volumes_touched - volumes_created):
            problems.append(
                f"{label}: modifies volume {volume!r} without creating it in the same block."
            )

    if problems:
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(f"ontap setup scripts: {len(problems)} problem(s)", file=sys.stderr)
        return 1

    print(f"ontap setup scripts: OK ({checked} command block(s) internally consistent)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
