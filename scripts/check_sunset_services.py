#!/usr/bin/env python3
"""Fail when a document names an AWS service that is closed to new customers
without saying so.

Why this exists
---------------
A reader following a reference architecture builds what it describes. If a step
names a service that no longer accepts new customers, they cannot: the console
offers no path to create it, and nothing in the document warned them. The failure
lands on the reader, and it lands late.

This is not hypothetical here. Measured when this guard was written, documents in
this repository proposed AWS IoT SiteWise Cold Tier, Buffered Destination and
Bulk Export as workarounds, referenced SageMaker Edge Manager for model delivery,
and described a time-series path through Amazon Timestream for LiveAnalytics —
written while each was current, and left standing after it was not.

What this checks, and what it cannot
------------------------------------
Per document, not per line: the same service is usually named in prose and again
in a table, and a line-level rule would flag every mention except the one
carrying the note. Document-level asks only "if you bring this up, say where it
stands", which is the part that can be automated. Whether the note sits where a
reader will see it, and whether the alternative offered is a reasonable one, still
needs a human.

The inventory below is a snapshot with a date on it. Services move into
maintenance continuously, so an empty violation list means the recorded services
are handled, not that every service named in the docs is current.

Exit codes: 0 every mention carries a note, 1 a mention does not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Status as of 2026-08-19. Each entry: the phrase to match, its status, and the
# source. Adding one without a source makes the list unauditable; the next reader
# cannot tell a verified status from a remembered one.
SUNSET_SERVICES: dict[str, tuple[str, str]] = {
    "IoT Analytics": (
        "discontinued 2025-12-15",
        "https://docs.aws.amazon.com/greengrass/v1/developerguide/stream-export-configurations.html",
    ),
    "IoT Events": (
        "end of support announced 2025-06",
        "https://aws.amazon.com/about-aws/whats-new/2025/05/aws-service-changes/",
    ),
    "Timestream for LiveAnalytics": (
        "closed to new customers 2025-06-20",
        "https://docs.aws.amazon.com/timestream/latest/developerguide/AmazonTimestreamForLiveAnalytics-availability-change.html",
    ),
    "SiteWise Monitor": (
        "closed to new customers 2025-11-07",
        "https://docs.aws.amazon.com/iot-sitewise/latest/userguide/document-history.html",
    ),
    "Data Processing Pack": (
        "IoT SiteWise Edge DPP, closed to new customers 2025-11-07",
        "https://docs.aws.amazon.com/iot-sitewise/latest/userguide/document-history.html",
    ),
    "Lookout for Equipment": (
        "sunset announced 2025-10",
        "https://aws.amazon.com/about-aws/whats-new/2025/10/aws-service-availability/",
    ),
    "S3 Object Lambda": (
        "maintenance, closed to new customers 2025-11-07",
        "https://aws.amazon.com/about-aws/whats-new/2025/10/aws-service-availability/",
    ),
    "SageMaker Edge Manager": (
        "end of support 2024-04-26",
        "https://docs.aws.amazon.com/sagemaker/latest/dg/edge-eol.html",
    ),
    "Greengrass v1": (
        "sunset announced 2025-10",
        "https://aws.amazon.com/about-aws/whats-new/2025/10/aws-service-availability/",
    ),
    "AWS Panorama": (
        "support ended 2026-05-31",
        "https://docs.aws.amazon.com/panorama/latest/dev/gettingstarted-compatibility.html",
    ),
    # Closed to new customers 2026-07-30 as a group. None is named in this
    # repository today; they are listed because a labelling or model-monitoring
    # step is the obvious place for one to appear later.
    "Ground Truth": (
        "SageMaker AI feature, closed to new customers 2026-07-30",
        "https://aws.amazon.com/sagemaker/ai/features/",
    ),
    "Model Monitor": (
        "SageMaker AI feature, closed to new customers 2026-07-30",
        "https://aws.amazon.com/sagemaker/ai/features/",
    ),
    "Augmented AI": (
        "SageMaker AI feature, closed to new customers 2026-07-30",
        "https://aws.amazon.com/sagemaker/ai/features/",
    ),
}

# A note can be written in either language and in several registers. Matching a
# vocabulary rather than one fixed sentence keeps the guard from dictating prose.
#
# Every marker has to be a phrase that only appears when describing availability.
# Bare "maintenance" was in this list first and made the guard useless on the
# document it was written for: the English iot-greengrass-flexcache-integration.md
# names SageMaker Edge Manager with no note, and passed anyway because "predictive
# maintenance" appears elsewhere in it — one of two identical defects reported.
# Seven of sixty documents here contain "maintenance" in that sense.
NOTICE_MARKERS = (
    "新規顧客",
    "new customers",
    "提供終了",
    "discontinued",
    "end of support",
    "end-of-support",
    "in maintenance",
    "maintenance mode",
    "メンテナンスモード",
    "sunset",
    "非開放",
    "サポート終了",
)

SEARCH_ROOTS = ("docs", "usecases", "cloud", "edge")
ROOT_FILES = ("README.md", "README_en.md", "TESTING.md", "TESTING_en.md", "CONTRIBUTING.md")
SKIP_DIR_PARTS = {".venv", ".aws-sam", "node_modules", "__pycache__", ".git", ".kiro", ".private"}

# This file names every service in the inventory by definition, and so does the
# lifecycle reference it points at. Excluding them keeps the guard from reporting
# its own inventory.
SELF_REFERENTIAL = {
    "scripts/check_sunset_services.py",
    "docs/agent/service-lifecycle.md",
    "docs/agent/service-lifecycle_en.md",
}


def documents() -> list[Path]:
    found: list[Path] = []
    for name in ROOT_FILES:
        path = REPO_ROOT / name
        if path.is_file():
            found.append(path)
    for root in SEARCH_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.md"):
            if SKIP_DIR_PARTS & set(path.parts):
                continue
            found.append(path)
    return sorted(found)


def mentions(text: str) -> list[str]:
    return [
        service
        for service in SUNSET_SERVICES
        if re.search(re.escape(service), text, re.IGNORECASE)
    ]


def has_notice(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in NOTICE_MARKERS)


def main() -> int:
    docs = documents()

    if not docs:
        print(
            "no documents discovered — the walker is probably broken, which would make "
            "this check vacuous",
            file=sys.stderr,
        )
        return 1

    problems: list[str] = []
    checked = 0

    for path in docs:
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in SELF_REFERENTIAL:
            continue
        text = path.read_text(encoding="utf-8")
        named = mentions(text)
        if not named:
            continue
        checked += 1
        if has_notice(text):
            continue
        for service in named:
            status, source = SUNSET_SERVICES[service]
            problems.append(
                f"{relative} names '{service}' ({status}) with no note about its "
                f"availability. A reader cannot build this. State the status and give a "
                f"current alternative, or drop the mention. Source: {source}"
            )

    if not problems:
        # Distinguish "checked and fine" from "nothing to check". A bare count of
        # zero reads like the walker failed, which is the state this guard is
        # least able to detect on its own.
        detail = (
            f"{checked} of {len(docs)} documents name one, each with a note"
            if checked
            else f"no document among {len(docs)} names any of the {len(SUNSET_SERVICES)} recorded services"
        )
        print(f"sunset services: OK ({detail})")
        return 0

    print("Documents name services that are closed to new customers:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
