"""Regression tests for `_store_result` in the Bedrock image analyzer.

Why these exist
---------------
Both copies of this handler referenced an undefined `MODEL_ID` when building the
result document. `_store_result` runs on every successful analysis, inside the
handler's `try`, so the NameError was caught by the broad `except Exception` and
returned as a 500 — after the Bedrock call had already been paid for. Every
invocation failed at the last step and no test touched that line. bandit does not
look for undefined names; ruff's F821 found it in the second copy.

The file exists twice, byte-identical: cloud/ai/image_analyzer/handler.py and
usecases/3d-print-quality/lambda/handler.py. Both are loaded here, because fixing
one copy of a duplicated bug is the usual way the other copy survives.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

HANDLER_PATHS = [
    REPO_ROOT / "cloud" / "ai" / "image_analyzer" / "handler.py",
    REPO_ROOT / "usecases" / "3d-print-quality" / "lambda" / "handler.py",
]


def load_handler(path: Path, module_name: str):
    """Import a handler by path, so both copies can be loaded in one session."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(params=HANDLER_PATHS, ids=lambda p: p.parent.parent.name)
def handler(request, monkeypatch):
    path = request.param
    if not path.is_file():
        pytest.skip(f"{path} not present")
    monkeypatch.setenv("RESULT_BUCKET", "results-bucket")
    monkeypatch.setenv("LOG_LEVEL", "CRITICAL")
    module = load_handler(path, f"analyzer_{path.parent.parent.name.replace('-', '_')}")
    monkeypatch.setattr(module, "RESULT_BUCKET", "results-bucket")
    return module


def test_both_handler_copies_are_present():
    """If one copy is deleted, this test says so instead of silently halving coverage."""
    missing = [str(p.relative_to(REPO_ROOT)) for p in HANDLER_PATHS if not p.is_file()]
    assert not missing, f"expected handler copies are missing: {missing}"


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
