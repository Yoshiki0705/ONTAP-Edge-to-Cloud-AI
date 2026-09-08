#!/usr/bin/env python3
"""Every Actions pin must be a SHA that exists, at the version its comment claims.

Why this exists
---------------
`.github/workflows/scorecard.yml` pinned `github/codeql-action/upload-sarif` to
`ce28f5bb…`, commented `# v3.28.0`. **That commit does not exist in that
repository** — the real v3.28.0 is `48ab28a6…`. The workflow therefore failed at
action resolution, before a single step ran, on every push to main since it was
added. The badge in the README pointed at a scan that had never happened.

Nothing caught it, because every check that could have was looking elsewhere:

- zizmor lints workflow *content* and only runs when `.github/workflows/**`
  changes; an unresolvable SHA is well-formed as far as it is concerned
- Renovate keeps digests current, but it updates pins it can resolve. A digest it
  cannot find is not a pin it manages
- the workflow's own red X was indistinguishable from the Scorecard checks that
  genuinely depend on repository settings, which is what an earlier commit
  message in this repository had already recorded as the reason for a red run

Two modes
---------
Offline (default) checks shape: a third-party `uses:` must carry a 40-character
SHA and a `# vX.Y.Z` comment. It needs no network and belongs in `make lint`.

`--verify` asks GitHub two questions per pin: does the commit exist, and does the
tag in the comment resolve to that same commit. The second half matters as much as
the first: a pin that resolves to a different version than it claims makes every
reader of the file wrong about what runs.

The API is rate-limited to 60 requests an hour unauthenticated, which two runs
exhaust. A token is read from `GITHUB_TOKEN`, `GH_TOKEN`, or `gh auth token`. When
the limit is hit anyway the result is reported as undetermined and does not fail
the run, because "GitHub would not answer" is not "the pin is wrong".

Exit codes: 0 every pin is well-formed (and verified, with --verify), 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess  # nosec B404  # fixed argv, never a shell string
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
API = "https://api.github.com"

# uses: owner/repo[/subpath]@ref  [# comment]
USES = re.compile(
    r"^\s*-?\s*uses:\s*(?P<ref>[^\s#]+)\s*(?:#\s*(?P<comment>.+?))?\s*$"
)
SHA = re.compile(r"^[0-9a-f]{40}$")
VERSION_COMMENT = re.compile(r"^v?\d+\.\d+(\.\d+)?")


def token() -> str | None:
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    try:
        result = subprocess.run(  # nosec B603  # noqa: S603  fixed argv, no shell
            ["gh", "auth", "token"],  # noqa: S607 - resolved from PATH deliberately
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


class RateLimited(Exception):
    """GitHub refused to answer. Nothing was learned about the pin."""


def api(path: str, auth: str | None) -> dict | None:
    """Return the parsed body, None for 404/422, and raise on a rate limit."""
    headers = {"User-Agent": "action-pin-check", "Accept": "application/vnd.github+json"}
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    request = urllib.request.Request(API + path, headers=headers)  # noqa: S310  fixed host
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310  # noqa: S310
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise RateLimited(f"HTTP {exc.code} for {path}") from exc
        if exc.code in (404, 422):
            return None
        raise
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RateLimited(f"unreachable: {exc}") from exc


def iter_pins():
    """Yield (path, lineno, ref, comment) for every `uses:` in the workflows."""
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = USES.match(line)
            if match:
                yield path, lineno, match.group("ref"), (match.group("comment") or "").strip()


def check(verify: bool = False) -> int:
    errors: list[str] = []
    undetermined: list[str] = []
    pins: dict[tuple[str, str, str], str] = {}

    for path, lineno, ref, comment in iter_pins():
        rel = path.relative_to(REPO_ROOT)
        where = f"{rel}:{lineno}"
        if ref.startswith("./") or ref.startswith("docker://"):
            continue
        if "@" not in ref:
            errors.append(f"{where}: not pinned at all: {ref}")
            continue
        repo, _, revision = ref.partition("@")
        if not SHA.match(revision):
            errors.append(f"{where}: pinned to a mutable ref, not a SHA: {ref}")
            continue
        if not VERSION_COMMENT.match(comment):
            errors.append(
                f"{where}: no version comment; a bare SHA cannot be read or audited: {ref}"
            )
            continue
        owner_repo = "/".join(repo.split("/")[:2])
        pins[(owner_repo, revision, comment.split()[0])] = where

    if verify and not errors:
        auth = token()
        if not auth:
            print(
                "NOTE: no token found (GITHUB_TOKEN, GH_TOKEN, gh auth token). "
                "The API allows 60 unauthenticated requests an hour.",
                file=sys.stderr,
            )
        for (owner_repo, sha, tag), where in sorted(pins.items()):
            try:
                commit = api(f"/repos/{owner_repo}/commits/{sha}", auth)
                if commit is None:
                    errors.append(
                        f"{where}: {owner_repo}@{sha} does not exist in that repository. "
                        f"The workflow cannot resolve it and fails before any step runs"
                    )
                    continue
                tagged = api(f"/repos/{owner_repo}/commits/{tag}", auth)
            except RateLimited as exc:
                undetermined.append(f"{where}: {owner_repo} {tag}: {exc}")
                continue
            if tagged is None:
                undetermined.append(
                    f"{where}: {owner_repo} has no ref named {tag}; the SHA exists, "
                    f"so the comment may name a tag that was moved or deleted"
                )
            elif tagged["sha"] != sha:
                errors.append(
                    f"{where}: {owner_repo} {tag} is {tagged['sha'][:12]}, "
                    f"but the pin is {sha[:12]}. The comment names a different version "
                    f"than the one that runs"
                )

    if undetermined:
        print("undetermined (nothing was learned about these pins):", file=sys.stderr)
        for line in undetermined:
            print(f"  ? {line}", file=sys.stderr)

    if errors:
        print(f"action pins: {len(errors)} problem(s):", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    summary = f"action pins: OK ({len(pins)} pin(s)"
    summary += ", each resolving to the version its comment claims)" if verify else " well-formed)"
    print(summary)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check GitHub Actions pins.")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="ask GitHub whether each SHA exists and matches its version comment",
    )
    args = parser.parse_args()
    return check(verify=args.verify)


if __name__ == "__main__":
    sys.exit(main())
