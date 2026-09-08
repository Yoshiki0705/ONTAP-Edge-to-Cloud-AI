#!/usr/bin/env python3
"""Resolve Markdown links: relative paths and anchors offline, URLs with --external.

Why this exists
---------------
This repository points readers outward on purpose. The README delegates the
storage-selection decision, the limits and the evidence tiers to the adoption
playbook, `verification-status.md` cites two sibling repositories for numbers it
declines to re-measure, and the docs cross-link heavily between `docs/ja/` and
`docs/en/`. Nothing verified any of it. Measured when this gate was written: the
Raspberry Pi setup guide had told readers to clone `Yoshiki0705/edge-to-cloud-ai`
since the repository was renamed to `ontap-edge-to-cloud-ai`; the old name still
redirects, so the instruction worked and would have broken silently the day that
name was reused.

An anchor is the part that rots most quietly. Renaming a heading leaves every
link to it pointing at the top of the page, and GitHub answers an unknown
fragment with the page rather than a 404, so neither the reader nor a crawler
learns that the target moved.

Two modes, because they fail differently
----------------------------------------
Offline (default) resolves relative links and fragments. It needs no network, is
deterministic, and belongs in `make lint`.

`--external` probes http(s) URLs. It depends on hosts outside this repository, so
a red run can mean "their outage" rather than "our defect". It is a separate
target and is deliberately not part of `make check`; a networked probe inside the
commit gate teaches people to ignore the gate.

What it cannot tell you
-----------------------
That a link resolves says nothing about whether the claim it supports is still
there. A cited document can be rewritten around an intact anchor. Verifying that
a specific claim survives needs a probe string per citation, which is what the
playbook's `cross-repo-index.md` does and this gate does not.

Exit codes: 0 every link resolved, 1 at least one did not.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]

# Directories holding nothing a reader can follow, or nothing published:
# .private/ and .kiro/ are gitignored working material, the rest are caches,
# build output and vendored trees.
SKIP_DIR_PARTS = {
    ".venv",
    ".aws-sam",
    ".git",
    ".kiro",
    ".private",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
}

# [text](target) — skips image embeds (leading !) and reference-style definitions.
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^\s*(?:```|~~~)")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
SKIP_SCHEMES = {"mailto", "tel", "data"}
USER_AGENT = "ontap-edge-to-cloud-ai-link-check"


def slugify(text: str) -> str:
    """GitHub-flavoured heading slug: lowercase, punctuation dropped, spaces to hyphens.

    Each whitespace character becomes its own hyphen; GitHub does not collapse
    runs. Japanese headings survive because `\\w` is Unicode-aware here, so
    `## 姉妹リポジトリの数値を引くときの条件` slugs to itself and a heading mixing
    scripts (`## S3 AP 経由で使える AWS サービス`) keeps its inner hyphens.
    """
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s", "-", text)


def anchors_of(path: Path) -> set[str]:
    """Every fragment the file offers: heading slugs plus explicit HTML ids."""
    found: set[str] = set()
    in_fence = False
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return found
    for line in lines:
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = HEADING.match(line)
        if heading:
            found.add(slugify(heading.group(2)))
        for named in re.finditer(r'(?:id|name)="([^"]+)"', line):
            found.add(named.group(1).lower())
    return found


def iter_links(path: Path):
    """Yield (lineno, target) for every inline link outside fenced code.

    Fenced blocks are skipped because they hold commands, not links a reader
    clicks. The clone URL that was wrong for months lived in exactly such a
    block, so this gate would not have caught it — `--external` would not either,
    since the stale name still redirects.
    """
    in_fence = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in LINK.finditer(line):
            yield lineno, match.group(1)


def iter_markdown(root: Path):
    for path in sorted(root.rglob("*.md")):
        if SKIP_DIR_PARTS & set(path.relative_to(root).parts[:-1]):
            continue
        yield path


def check_internal(source: Path, target: str, root: Path = REPO_ROOT) -> str | None:
    """Return a message when a relative link or fragment does not resolve."""
    raw_path, _, fragment = target.partition("#")
    raw_path = unquote(raw_path)
    if not raw_path:  # same-document anchor
        if fragment and slugify(fragment) not in anchors_of(source):
            return f"anchor '#{fragment}' not found in this document"
        return None
    resolved = (root / raw_path[1:]) if raw_path.startswith("/") else (source.parent / raw_path)
    resolved = resolved.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return f"link escapes the repository root: {target}"
    if resolved.is_dir():
        # GitHub renders a directory link as a file listing, so a README is not
        # required. Git does not track empty directories though, so one that
        # exists locally but holds nothing would 404 after a clone.
        if not any(child.is_file() and child.name != ".DS_Store" for child in resolved.rglob("*")):
            return f"directory is empty and will not survive a clone: {raw_path} (add .gitkeep)"
        return None
    if not resolved.exists():
        return f"file not found: {raw_path}"
    if fragment and resolved.suffix == ".md" and slugify(fragment) not in anchors_of(resolved):
        return f"anchor '#{fragment}' not found in {raw_path}"
    return None


# Prefix marking a verdict as "the server did not answer", which is not the same
# as "the link is broken". Reporting an outage as a broken link is how a check
# stops being read; reporting it as fine is worse, because an unreachable URL
# then looks checked. So it is printed separately and does not fail the run.
UNDETERMINED = "? "


def _probe(url: str, method: str, timeout: float) -> str | None:
    # The scheme is re-checked here rather than trusted from the caller. B310 is
    # about urlopen accepting file: and custom schemes, and a Markdown link is
    # attacker-reachable in principle: a pull request can add `[x](file:///etc/…)`
    # and this process would open it. Refusing anything but http(s) at the call
    # site is what makes the suppression below true rather than asserted.
    if urlparse(url).scheme not in ("http", "https"):
        return f"refusing to probe a non-http(s) URL: {url}"
    request = urllib.request.Request(  # noqa: S310  scheme refused above
        url, method=method, headers={"User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310  # noqa: S310
            if response.status >= 400:
                return f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405, 429):
            return None  # bot-blocked or method-not-allowed, not a broken link
        if exc.code >= 500:
            return f"{UNDETERMINED}HTTP {exc.code}"
        return f"HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return f"{UNDETERMINED}unreachable ({exc})"
    return None


def check_external(url: str, timeout: float = 10.0) -> str | None:
    """HEAD first, then confirm a failure with GET before reporting it.

    Some hosts answer HEAD from a landing page that 404s while GET returns the
    real page. HEAD stays first because it avoids downloading bodies for the
    common case.
    """
    problem = _probe(url, "HEAD", timeout)
    if problem is None:
        return None
    return _probe(url, "GET", timeout)


def check(root: Path = REPO_ROOT, external: bool = False) -> int:
    errors: list[str] = []
    unknown: list[str] = []
    internal_count = 0
    external_seen: dict[str, str | None] = {}

    for path in iter_markdown(root):
        rel = path.relative_to(root)
        for lineno, target in iter_links(path):
            scheme = urlparse(target).scheme
            if scheme in SKIP_SCHEMES:
                continue
            if scheme in ("http", "https"):
                if not external:
                    continue
                if target not in external_seen:
                    external_seen[target] = check_external(target)
                problem = external_seen[target]
                if problem and problem.startswith(UNDETERMINED):
                    unknown.append(f"{rel}:{lineno}: {problem[len(UNDETERMINED) :]} -> {target}")
                elif problem:
                    errors.append(f"{rel}:{lineno}: {problem} -> {target}")
                continue
            if scheme:  # some other scheme; nothing to resolve on disk
                continue
            internal_count += 1
            problem = check_internal(path, target, root)
            if problem:
                errors.append(f"{rel}:{lineno}: {problem}")

    if unknown:
        print(
            "undetermined (the server did not answer; nothing learned about the link):",
            file=sys.stderr,
        )
        for line in unknown:
            print(f"  ? {line}", file=sys.stderr)

    if errors:
        print(f"link check failed ({len(errors)} issue(s)):", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    summary = f"links: OK ({internal_count} relative link(s) and anchor(s) resolved"
    summary += f", {len(external_seen)} URL(s) probed)" if external else ")"
    print(summary)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve Markdown links.")
    parser.add_argument(
        "--external",
        action="store_true",
        help="also probe http(s) URLs (needs a network; not part of make check)",
    )
    args = parser.parse_args()
    return check(external=args.external)


if __name__ == "__main__":
    sys.exit(main())
