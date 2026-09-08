#!/usr/bin/env python3
"""Ask OSV whether the pinned dependency versions have known vulnerabilities.

Why this exists
---------------
An OSV scan of this repository reported **26 known vulnerabilities**, and the cause
was the shape of the requirements files rather than a single bad dependency. Every
runtime file used lower-bound ranges (`numpy>=1.26.0`, `requests>=2.31.0`), and a
range does not state which version runs, so a scanner attributes every advisory
ever filed against the package. Two of them were real at the floor: `requests`
2.31.0 leaks .netrc credentials to a malicious redirect (PYSEC-2026-1872, fixed in
2.32.4), and `pyarrow` 15.0.0 predates the fixes in 17.0.0 and 23.0.1.

`scripts/check_dependency_pins.py` now requires `==` in those files. That makes the
question answerable; this script asks it. **Pinning is what removes the ambiguity,
not what removes the risk** — a pin is a statement about a version that was clean
on the day it was written, and advisories are published afterwards.

Why it is not part of `make check`
----------------------------------
It needs the network and a third party's index, and its verdict changes without any
commit here: a run that was green yesterday can be red today because an advisory was
published overnight. That is information, not a reason to block a commit. `make
deps-audit` is a pre-release and periodic check.

Exit codes: 0 nothing known against the pinned versions, 1 at least one advisory,
2 the question could not be asked (network, API shape).
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OSV_QUERY = "https://api.osv.dev/v1/query"
SKIP_DIR_PARTS = {".venv", ".aws-sam", "node_modules", "__pycache__", ".git", ".kiro", ".private"}
PIN = re.compile(r"^([A-Za-z0-9._-]+)\s*==\s*([^\s;#]+)")


def pinned() -> dict[tuple[str, str], list[str]]:
    """Map (package, version) to the files pinning it. Dev tooling included: a
    linter with a known vulnerability is still running on this machine."""
    found: dict[tuple[str, str], list[str]] = {}
    # The lock is included on purpose: it is the only file naming the transitive
    # dependencies, and those are installed too. Auditing the direct pins alone
    # would have said "OK" about a tree of 42 packages while looking at 15.
    for path in sorted(
        [*REPO_ROOT.rglob("requirements*.txt"), *REPO_ROOT.rglob("requirements*.lock")]
    ):
        if SKIP_DIR_PARTS & set(path.relative_to(REPO_ROOT).parts):
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            match = PIN.match(line)
            if match:
                key = (match.group(1).lower(), match.group(2))
                found.setdefault(key, []).append(path.relative_to(REPO_ROOT).as_posix())
    return found


def query(package: str, version: str) -> list[dict]:
    body = json.dumps(
        {"package": {"name": package, "ecosystem": "PyPI"}, "version": version}
    ).encode()
    request = urllib.request.Request(  # noqa: S310  fixed host, https
        OSV_QUERY, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310  # noqa: S310
        return json.load(response).get("vulns", [])


def main() -> int:
    entries = pinned()
    if not entries:
        print(
            "no pinned dependency found — the sweep is looking in the wrong place",
            file=sys.stderr,
        )
        return 2

    findings: list[str] = []
    for (package, version), files in sorted(entries.items()):
        try:
            vulns = query(package, version)
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            print(f"could not ask OSV about {package}=={version}: {exc}", file=sys.stderr)
            return 2
        for vuln in vulns:
            fixed = sorted(
                {
                    event["fixed"]
                    for affected in vuln.get("affected", [])
                    for rng in affected.get("ranges", [])
                    for event in rng.get("events", [])
                    if "fixed" in event
                }
            )
            findings.append(
                f"{package}=={version} ({', '.join(files)}): {vuln['id']} "
                f"{vuln.get('summary', '').strip()[:90]}"
                + (f" [fixed in {', '.join(fixed[-3:])}]" if fixed else "")
            )

    if findings:
        print(f"dependency audit: {len(findings)} advisory(ies):", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1

    print(f"dependency audit: OK ({len(entries)} pinned version(s), none known to OSV)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
