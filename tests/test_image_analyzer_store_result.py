"""Regression tests for `_store_result` in the Bedrock image analyzer.

Why these exist
---------------
Both copies of this handler referenced an undefined `MODEL_ID` when building the
result document. `_store_result` runs on every successful analysis, inside the
handler's `try`, so the NameError was caught by the broad `except Exception` and
returned as a 500 — after the Bedrock call had already been paid for. Every
invocation failed at the last step and no test touched that line. bandit does not
look for undefined names; ruff's F821 found it in the second copy.

The file used to exist twice, byte-identical, as
usecases/3d-print-quality/lambda/handler.py as well. That is how the defect
reached two places at once, so `test_handler_is_not_duplicated` below fails if a
copy reappears.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The single source. The deployment guide zips this directory, and both
# usecases/3d-print-quality and usecases/visual-inspection point at it.
HANDLER_PATH = REPO_ROOT / "cloud" / "ai" / "image_analyzer" / "handler.py"

SKIP_DIR_PARTS = {".venv", ".aws-sam", "__pycache__", ".git", ".pytest_cache", ".ruff_cache"}


def load_handler(path: Path, module_name: str):
    """Import a handler by path, so both copies can be loaded in one session."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def handler(monkeypatch):
    assert HANDLER_PATH.is_file(), f"{HANDLER_PATH} is missing"
    monkeypatch.setenv("RESULT_BUCKET", "results-bucket")
    monkeypatch.setenv("LOG_LEVEL", "CRITICAL")
    module = load_handler(HANDLER_PATH, "image_analyzer_handler")
    monkeypatch.setattr(module, "RESULT_BUCKET", "results-bucket")
    return module


def test_handler_is_not_duplicated():
    """No other file in the repository may be a copy of this handler.

    The MODEL_ID defect existed in two byte-identical files. A copy passes its
    own tests right up until one side is edited, and then keeps passing.
    Comparing content rather than filename catches a copy under any name.
    """
    canonical = hashlib.sha256(HANDLER_PATH.read_bytes()).hexdigest()
    copies = []
    for path in REPO_ROOT.rglob("*.py"):
        if path == HANDLER_PATH or SKIP_DIR_PARTS & set(path.parts):
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() == canonical:
            copies.append(path.relative_to(REPO_ROOT).as_posix())

    assert not copies, (
        f"these files are byte-identical copies of {HANDLER_PATH.relative_to(REPO_ROOT)}: "
        f"{copies}. Reference the single source instead; the deployment guide zips "
        f"cloud/ai/image_analyzer/ for every use case."
    )


def test_store_result_does_not_raise_on_a_screening_only_verdict(handler):
    mock_s3 = MagicMock()
    result = {"status": "normal", "confidence": 0.9, "_stage": "screening_only"}
    with patch.object(handler, "s3_client", mock_s3):
        key = handler._store_result("src-bucket", "img/a.jpg", result)

    assert key.startswith("processed/image_analysis/year=")
    body = json.loads(mock_s3.put_object.call_args.kwargs["Body"])
    analyzer = body["payload"]["analyzer"]
    assert analyzer["model_id"] == handler.SCREENING_MODEL_ID
    assert analyzer["stage"] == "screening_only"


def test_store_result_records_the_detail_model_when_stage_two_ran(handler):
    mock_s3 = MagicMock()
    result = {"status": "anomaly_detected", "confidence": 0.8, "_stage": "detailed"}
    with patch.object(handler, "s3_client", mock_s3):
        handler._store_result("src-bucket", "img/b.jpg", result)

    analyzer = json.loads(mock_s3.put_object.call_args.kwargs["Body"])["payload"]["analyzer"]
    assert analyzer["model_id"] == handler.DETAIL_MODEL_ID
    assert analyzer["stage"] == "detailed"


def test_handler_reaches_store_result_and_returns_200(handler):
    """The end-to-end shape of the defect: analysis succeeded, the store failed."""
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: b"\xff\xd8\xff\xe0jpeg")}
    analysis = {
        "status": "normal",
        "confidence": 0.95,
        "anomalies": [],
        "overall_quality_score": 92,
        "_stage": "screening_only",
    }
    with patch.object(handler, "s3_client", mock_s3), \
         patch.object(handler, "_analyze_image", return_value=analysis), \
         patch.object(handler, "_publish_metrics"):
        response = handler.handler({"bucket": "src-bucket", "key": "img/c.jpg"}, None)

    assert response["statusCode"] == 200, response
    assert response["body"]["result_key"].startswith("processed/image_analysis/")


def test_store_result_is_encrypted_and_targets_the_result_bucket(handler):
    mock_s3 = MagicMock()
    with patch.object(handler, "s3_client", mock_s3):
        handler._store_result("src-bucket", "img/d.jpg", {"_stage": "detailed"})

    kwargs = mock_s3.put_object.call_args.kwargs
    assert kwargs["Bucket"] == "results-bucket"
    assert kwargs["ServerSideEncryption"] == "aws:kms"
