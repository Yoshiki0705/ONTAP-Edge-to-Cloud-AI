#!/usr/bin/env python3
"""Fail when a template's environment variables and its handler's reads disagree.

Why this exists
---------------
Measured on this repository: `usecases/visual-inspection` is documented as the same
handler as `3d-print-quality` with only the prompt changed, and shipped without the prompt
being passed at all. The handler hardcoded 3D-print prompts, the template set none, so the
stack deployed cleanly and then analysed manufactured parts by looking for stringing and
spaghetti. The README even named the variable — `ANALYSIS_PROMPT` — that nothing read.

The same review found the prompt documented in that README asked the model for
`{"status": "pass"|"fail", "defects": [...], "quality_score": …}` while the handler reads
`status == "anomaly_detected"`, `confidence` and `anomalies`. Had the prompt been wired as
written, alerting would have stayed silent for every defective part, because the status
string it produces is one the handler never compares against.

Neither failure is visible to cfn-lint, to ruff, or to a unit test of either side alone:
each half is internally valid and the contract between them is not written down anywhere a
tool can read. `usecases/handler-map.txt` is where it is written down.

What is checked
---------------
  1. Every variable the handler reads without a usable default is set by every template
     that runs it. A missing one is a runtime `KeyError` or, worse, a silent empty string.
  2. Every variable a template sets is one the handler reads. Dead configuration reads as
     live and invites the next person to tune a value that has no effect.
  3. A prompt variable asks the model for the JSON keys the handler parses.
  4. Every template declaring a Lambda function appears in the map.

Reads are found with the AST, not a regex. `os.environ.get(` is written across two lines in
this repository, and a line-oriented grep silently reported four of the six variables while
looking authoritative.

Exit codes: 0 the contract holds, 1 a mismatch.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAP_FILE = REPO_ROOT / "usecases" / "handler-map.txt"
TEMPLATE_GLOBS = ("cloud/*/template.yaml", "usecases/*/template.yaml")

# Variables the runtime supplies, so a handler may read them without a template setting one.
RUNTIME_PROVIDED = {"AWS_REGION", "AWS_DEFAULT_REGION", "AWS_LAMBDA_FUNCTION_NAME", "TZ"}

# A variable whose name says it carries a prompt must ask for what the handler parses.
PROMPT_HINT = re.compile(r"PROMPT$")


def env_reads(module: Path) -> dict[str, bool]:
    """Map variable name -> whether a usable default exists, from the AST.

    A usable default means the handler still works when the variable is absent:
    `os.environ.get("X", "y")`, or `os.environ.get("X") or "y"`. `os.environ["X"]` and a
    bare `get` with no fallback do not qualify.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    reads: dict[str, bool] = {}

    def name_of(node: ast.AST) -> str | None:
        """The literal variable name in os.environ.get("X") / os.getenv("X") / os.environ["X"]."""
        if isinstance(node, ast.Call):
            target = node.func
            attr = getattr(target, "attr", None)
            if attr in {"get", "getenv"} and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    # os.environ.get / os.getenv, not some other .get
                    source = ast.unparse(target)
                    if "environ" in source or "getenv" in source:
                        return first.value
        if isinstance(node, ast.Subscript) and "environ" in ast.unparse(node.value):
            index = node.slice
            if isinstance(index, ast.Constant) and isinstance(index.value, str):
                return index.value
        return None

    for node in ast.walk(tree):
        variable = name_of(node)
        if variable is None:
            continue
        defaulted = isinstance(node, ast.Call) and len(node.args) > 1
        reads[variable] = reads.get(variable, False) or defaulted

    # `os.environ.get("X") or "default"` — the fallback is the BoolOp, not an argument.
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            for value in node.values:
                variable = name_of(value)
                if variable is not None and len(node.values) > 1:
                    reads[variable] = True
    return reads


def env_sets(template: Path, resource: str) -> dict[str, str]:
    """Variable name -> literal value (empty when the value is a CFn function).

    Parsed by indentation rather than with a YAML loader: these templates use short-form
    intrinsics (`!Ref`, `!ImportValue`, `!Sub`) that a plain loader rejects, and the check
    only needs the key names and any literal scalars.
    """
    lines = template.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == f"{resource}:")
    except StopIteration:
        return {}

    variables: dict[str, str] = {}
    in_vars = False
    vars_indent = 0
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped and not line.startswith(" "):
            break  # left the resource
        if stripped == "Variables:":
            in_vars = True
            vars_indent = len(line) - len(line.lstrip())
            continue
        if not in_vars:
            continue
        indent = len(line) - len(line.lstrip())
        if stripped and indent <= vars_indent:
            break  # left the Variables block
        match = re.match(r"^([A-Z][A-Z0-9_]*):\s*(.*)$", stripped)
        if match:
            variables[match.group(1)] = match.group(2).strip()
    return variables


def prompt_body(template: Path, variable: str) -> str:
    """The block scalar that follows `VARIABLE: |` or `: >-`, for keyword checking."""
    lines = template.read_text(encoding="utf-8").splitlines()
    try:
        start = next(
            i for i, line in enumerate(lines) if re.match(rf"^\s*{variable}:\s*[|>]", line)
        )
    except StopIteration:
        return ""
    indent = len(lines[start]) - len(lines[start].lstrip())
    body = []
    for line in lines[start + 1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        body.append(line)
    return "\n".join(body)


def parsed_keys(module: Path) -> set[str]:
    """String literals the handler pulls out of the model's JSON response."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "get":
            if node.args and isinstance(node.args[0], ast.Constant):
                value = node.args[0].value
                if isinstance(value, str) and not value.isupper():
                    keys.add(value)
    return keys


def load_map() -> list[tuple[Path, str, Path, set[str]]]:
    pairs = []
    for raw in MAP_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("::")]
        if len(parts) not in (3, 4):
            raise SystemExit(f"{MAP_FILE.name}: cannot parse: {raw!r}")
        must_set: set[str] = set()
        if len(parts) == 4:
            field = parts[3]
            if not field.startswith("must-set="):
                raise SystemExit(
                    f"{MAP_FILE.name}: fourth field must be must-set=...: {raw!r}"
                )
            must_set = {v.strip() for v in field[len("must-set="):].split(",") if v.strip()}
        pairs.append((REPO_ROOT / parts[0], parts[1], REPO_ROOT / parts[2], must_set))
    return pairs


def main() -> int:
    problems: list[str] = []
    pairs = load_map()

    # 4. Every template that declares a Lambda function is covered.
    declared = {template.resolve() for template, _, _, _ in pairs}
    for pattern in TEMPLATE_GLOBS:
        for template in sorted(REPO_ROOT.glob(pattern)):
            text = template.read_text(encoding="utf-8")
            if "AWS::Lambda::Function" not in text and "AWS::Serverless::Function" not in text:
                continue
            if template.resolve() not in declared:
                problems.append(
                    f"{template.relative_to(REPO_ROOT)} declares a Lambda function but is "
                    f"absent from {MAP_FILE.name}, so its environment contract is unchecked."
                )

    checked = 0
    for template, resource, module, must_set in pairs:
        label = f"{template.relative_to(REPO_ROOT)}::{resource}"
        for path in (template, module):
            if not path.is_file():
                problems.append(f"{label}: {path.relative_to(REPO_ROOT)} does not exist")
        if not template.is_file() or not module.is_file():
            continue

        reads = env_reads(module)
        sets = env_sets(template, resource)
        if not sets:
            problems.append(
                f"{label}: no Environment.Variables found. Either the resource id is wrong "
                f"or the function is configured somewhere this check cannot see."
            )
            continue
        checked += 1

        # 1. Required by the handler, absent from the template.
        for variable, defaulted in sorted(reads.items()):
            if variable in RUNTIME_PROVIDED or defaulted or variable in sets:
                continue
            problems.append(
                f"{label}: handler reads {variable} with no default and the template does "
                f"not set it."
            )

        # 1b. Declared overrides. A default that belongs to another use case is worse
        # than a missing value: the stack deploys and analyses the wrong thing.
        for variable in sorted(must_set - set(sets)):
            problems.append(
                f"{label}: {MAP_FILE.name} declares {variable} as must-set and the template "
                f"does not set it. The handler's default belongs to a different use case, so "
                f"this deploys cleanly and then does the wrong analysis."
            )

        # 2. Set by the template, never read.
        for variable in sorted(set(sets) - set(reads)):
            problems.append(
                f"{label}: template sets {variable} but "
                f"{module.relative_to(REPO_ROOT)} never reads it. Dead configuration reads "
                f"as live."
            )

        # 3. A prompt has to ask for what the handler parses.
        keys = parsed_keys(module)
        for variable in sorted(v for v in sets if PROMPT_HINT.search(v)):
            body = prompt_body(template, variable) or sets[variable]
            required = {"confidence"} | ({"status", "anomalies"} if "DETAIL" in variable else {"has_defect"})
            missing = sorted(key for key in required if key in keys and key not in body)
            if missing:
                problems.append(
                    f"{label}: {variable} never asks the model for {', '.join(missing)}, "
                    f"which {module.relative_to(REPO_ROOT)} reads from the response. The "
                    f"stack deploys and the result is parsed as absent."
                )
            if "DETAIL" in variable and "anomaly_detected" in module.read_text(encoding="utf-8"):
                if "anomaly_detected" not in body:
                    problems.append(
                        f"{label}: {variable} does not offer the status value "
                        f"'anomaly_detected', which is the only value that triggers an "
                        f"alert. Defects would be found and never reported."
                    )

    if problems:
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(f"lambda env contract: {len(problems)} problem(s)", file=sys.stderr)
        return 1

    print(f"lambda env contract: OK ({checked} template/handler pair(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
