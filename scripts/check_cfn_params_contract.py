#!/usr/bin/env python3
"""Fail when a parameter file and its template disagree.

Why this exists
---------------
A parameter file is the one artifact a reader copies and edits before their first deploy,
and every way it can be wrong produces a stack that either refuses to start or starts and
misbehaves:

  * A key the template does not declare. CloudFormation rejects the whole operation, which
    is the benign case — it fails loudly and immediately.
  * A key besides `ParameterKey` / `ParameterValue` inside an entry. `aws cloudformation
    deploy help` states the command throws on `UsePreviousValue` or `ResolvedValue`. Easy
    to add by copying output from `describe-stacks`, which includes them.
  * A parameter with no `Default` missing from the file, or present and empty. Nothing
    supplies a value, so either the deploy stops for an unprovided parameter or the stack
    is built around an empty string. Measured in a sibling repository: examples shipped
    with an empty access-point name deployed cleanly and then denied every request,
    because the empty value dropped the ARNs out of an IAM policy.
  * A file no template uses, or a template no file covers. Both read as coverage.

Also checked: the file table in cfn-params/README.md lists every parameter file. It was
missing `iot-ingestion.example.json` when this guard was written — a stack with no entry in
the index a reader is pointed at.

Templates are parsed by indentation rather than with a YAML loader on purpose: they use
short-form intrinsics (`!Ref`, `!ImportValue`, `!Sub`) that a plain loader rejects, and only
the parameter names and whether each has a Default are needed here.

Exit codes: 0 the files and templates agree, 1 a mismatch.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PARAMS_DIR = REPO_ROOT / "cfn-params"
README = PARAMS_DIR / "README.md"
TEMPLATE_GLOBS = ("cloud/*/template.yaml", "usecases/*/template.yaml")

ALLOWED_ENTRY_KEYS = {"ParameterKey", "ParameterValue"}

# A value that is obviously a stand-in rather than something that would deploy.
PLACEHOLDER = re.compile(r"(<[^>]+>|REPLACE_ME|CHANGEME|TODO|xxxx)", re.IGNORECASE)


def template_parameters(template: Path) -> dict[str, bool]:
    """Parameter name -> whether it declares a Default."""
    text = template.read_text(encoding="utf-8")
    match = re.search(r"^Parameters:\n(.*?)(?=^[A-Za-z]|\Z)", text, re.S | re.M)
    if not match:
        return {}
    parameters: dict[str, bool] = {}
    for block in re.split(r"\n(?=  [A-Za-z0-9]+:)", match.group(1)):
        name = re.match(r"\s*([A-Za-z0-9]+):", block)
        if name:
            parameters[name.group(1)] = bool(re.search(r"^\s+Default:", block, re.M))
    return parameters


def params_file_for(template: Path) -> Path:
    """cloud/iot_ingestion/ -> cfn-params/iot-ingestion.example.json."""
    return PARAMS_DIR / f"{template.parent.name.replace('_', '-')}.example.json"


def main() -> int:
    problems: list[str] = []
    templates = sorted(
        path for pattern in TEMPLATE_GLOBS for path in REPO_ROOT.glob(pattern)
    )
    if not templates:
        print("  no templates found; this guard would pass vacuously", file=sys.stderr)
        return 1

    used: set[Path] = set()
    checked = 0

    for template in templates:
        label = str(template.relative_to(REPO_ROOT))
        declared = template_parameters(template)
        params_file = params_file_for(template)

        if not params_file.is_file():
            problems.append(
                f"{label} declares {len(declared)} parameter(s) but there is no "
                f"{params_file.relative_to(REPO_ROOT)}. A reader has nothing to copy."
            )
            continue
        used.add(params_file.resolve())

        try:
            entries = json.loads(params_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            problems.append(f"{params_file.relative_to(REPO_ROOT)}: invalid JSON ({error})")
            continue
        if not isinstance(entries, list):
            problems.append(
                f"{params_file.relative_to(REPO_ROOT)}: expected a JSON array of "
                f"{{ParameterKey, ParameterValue}} entries."
            )
            continue
        checked += 1

        supplied: dict[str, str] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                problems.append(
                    f"{params_file.relative_to(REPO_ROOT)}: entry is not an object: {entry!r}"
                )
                continue
            for key in sorted(set(entry) - ALLOWED_ENTRY_KEYS):
                problems.append(
                    f"{params_file.relative_to(REPO_ROOT)}: entry carries {key!r}. "
                    f"aws cloudformation deploy throws on anything but ParameterKey and "
                    f"ParameterValue."
                )
            name = entry.get("ParameterKey")
            if name is not None:
                supplied[name] = str(entry.get("ParameterValue", ""))

        for name in sorted(set(supplied) - set(declared)):
            problems.append(
                f"{params_file.relative_to(REPO_ROOT)}: sets {name}, which {label} does not "
                f"declare. CloudFormation rejects the whole operation."
            )

        for name, has_default in sorted(declared.items()):
            if has_default:
                continue
            if name not in supplied:
                problems.append(
                    f"{params_file.relative_to(REPO_ROOT)}: {label} declares {name} with no "
                    f"Default and the file does not supply it."
                )
            elif supplied[name] == "":
                problems.append(
                    f"{params_file.relative_to(REPO_ROOT)}: {name} has no Default in {label} "
                    f"and is empty here. The stack would be built around an empty value."
                )

        for name, value in sorted(supplied.items()):
            if PLACEHOLDER.search(value):
                problems.append(
                    f"{params_file.relative_to(REPO_ROOT)}: {name}={value!r} is a "
                    f"placeholder. Give a value that deploys, or document the substitution."
                )

    for orphan in sorted(PARAMS_DIR.glob("*.example.json")):
        if orphan.resolve() not in used:
            problems.append(
                f"{orphan.relative_to(REPO_ROOT)} matches no template. It reads as coverage "
                f"for a stack that does not exist."
            )

    # The index a reader is pointed at has to list every file.
    if README.is_file():
        index = README.read_text(encoding="utf-8")
        for params_file in sorted(PARAMS_DIR.glob("*.example.json")):
            if f"`{params_file.name}`" not in index:
                problems.append(
                    f"{README.relative_to(REPO_ROOT)}: no row for {params_file.name}."
                )

    if problems:
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(f"cfn params contract: {len(problems)} problem(s)", file=sys.stderr)
        return 1

    print(f"cfn params contract: OK ({checked} template/parameter-file pair(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
