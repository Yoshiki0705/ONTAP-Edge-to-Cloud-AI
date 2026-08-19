"""What the analyzer knows about what it spent.

Every cost figure this repository published was a hand calculation from list prices, and it
could not have been anything else: `_invoke_model` parsed the Bedrock response, read
`content[0].text` out of it, and discarded the rest — including the `usage` block carrying
the token counts. `docs/ja/operations-design.md` meanwhile listed a `CostPerImage` metric
with a `> $0.02` alarm that nothing emitted, so the alarm could never fire.

These tests pin the properties that make a cost number traceable to a call:

  * the counts leave `_invoke_model` alongside the text
  * a response without `usage` yields zeros rather than raising, because a missing count
    must not fail an analysis that otherwise worked
  * both stages are attributed separately, including on the screening-only early return
  * `CostPerImage` is emitted only when the per-million-token rates are configured, and is
    never a partial sum over the stages whose rate happens to be set
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

HANDLER = Path(__file__).resolve().parents[1] / "cloud" / "ai" / "image_analyzer" / "handler.py"

RATE_VARIABLES = (
    "SCREENING_INPUT_USD_PER_MTOK",
    "SCREENING_OUTPUT_USD_PER_MTOK",
    "DETAIL_INPUT_USD_PER_MTOK",
    "DETAIL_OUTPUT_USD_PER_MTOK",
)


def load_handler(monkeypatch: pytest.MonkeyPatch, **environment: str):
    for name in RATE_VARIABLES + ("TWO_STAGE_ENABLED",):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("analyzer_token_usage_under_test", HANDLER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["analyzer_token_usage_under_test"] = module
    spec.loader.exec_module(module)
    return module


def bedrock_returning(text: str, usage: dict | None) -> MagicMock:
    """A Bedrock client whose response body carries `text` and optionally `usage`."""
    body = {"content": [{"text": text}]}
    if usage is not None:
        body["usage"] = usage
    client = MagicMock()
    stream = MagicMock()
    stream.read.return_value = json.dumps(body).encode()
    client.invoke_model.return_value = {"body": stream}
    return client


# --------------------------------------------------------------------------------------
# _invoke_model
# --------------------------------------------------------------------------------------


def test_invoke_model_returns_the_token_counts_with_the_text(monkeypatch):
    module = load_handler(monkeypatch)
    module.bedrock_client = bedrock_returning(
        "verdict", {"input_tokens": 1500, "output_tokens": 200}
    )
    text, usage = module._invoke_model("aGk=", "prompt", "model-x")
    assert text == "verdict"
    assert usage == {"input_tokens": 1500, "output_tokens": 200}


def test_invoke_model_reports_zeros_when_the_response_has_no_usage(monkeypatch):
    """Not every model family returns it, and an analysis must not fail over a count."""
    module = load_handler(monkeypatch)
    module.bedrock_client = bedrock_returning("verdict", None)
    text, usage = module._invoke_model("aGk=", "prompt", "model-x")
    assert text == "verdict"
    assert usage == {"input_tokens": 0, "output_tokens": 0}


def test_invoke_model_survives_a_null_usage_block(monkeypatch):
    module = load_handler(monkeypatch)
    module.bedrock_client = bedrock_returning("verdict", None)
    module.bedrock_client.invoke_model.return_value["body"].read.return_value = json.dumps(
        {"content": [{"text": "verdict"}], "usage": None}
    ).encode()
    _, usage = module._invoke_model("aGk=", "prompt", "model-x")
    assert usage == {"input_tokens": 0, "output_tokens": 0}


# --------------------------------------------------------------------------------------
# _analyze_image
# --------------------------------------------------------------------------------------


def test_both_stages_are_attributed_separately(monkeypatch):
    module = load_handler(monkeypatch)
    calls = [
        ('{"has_defect": true, "confidence": 0.9}', {"input_tokens": 1000, "output_tokens": 20}),
        ('{"status": "anomaly_detected", "confidence": 0.9, "anomalies": [], '
         '"recommendation": "x", "overall_quality_score": 40}',
         {"input_tokens": 1200, "output_tokens": 300}),
    ]
    monkeypatch.setattr(module, "_invoke_model", lambda *a, **k: calls.pop(0))

    result = module._analyze_image(b"\xff\xd8jpeg")

    usage = result["_token_usage"]
    assert set(usage) == {"screening", "detail"}
    assert usage["screening"]["input_tokens"] == 1000
    assert usage["detail"]["output_tokens"] == 300
    assert usage["screening"]["model_id"] == module.SCREENING_MODEL_ID
    assert usage["detail"]["model_id"] == module.DETAIL_MODEL_ID


def test_the_screening_only_path_still_reports_what_it_spent(monkeypatch):
    """The cheap path is the common one, so leaving it unattributed loses most of the bill."""
    module = load_handler(monkeypatch)
    monkeypatch.setattr(
        module,
        "_invoke_model",
        lambda *a, **k: (
            '{"has_defect": false, "confidence": 0.95}',
            {"input_tokens": 900, "output_tokens": 15},
        ),
    )

    result = module._analyze_image(b"\xff\xd8jpeg")

    assert result["_stage"] == "screening_only"
    assert set(result["_token_usage"]) == {"screening"}
    assert result["_token_usage"]["screening"]["input_tokens"] == 900


def test_a_detail_response_that_does_not_parse_still_reports_usage(monkeypatch):
    module = load_handler(monkeypatch)
    calls = [
        ('{"has_defect": true, "confidence": 0.9}', {"input_tokens": 100, "output_tokens": 5}),
        ("not json at all", {"input_tokens": 700, "output_tokens": 50}),
    ]
    monkeypatch.setattr(module, "_invoke_model", lambda *a, **k: calls.pop(0))

    result = module._analyze_image(b"\xff\xd8jpeg")

    assert result["_stage"] == "parse_error"
    assert result["_token_usage"]["detail"]["input_tokens"] == 700


# --------------------------------------------------------------------------------------
# cost
# --------------------------------------------------------------------------------------

FULL_RATES = {
    "SCREENING_INPUT_USD_PER_MTOK": "1.00",
    "SCREENING_OUTPUT_USD_PER_MTOK": "5.00",
    "DETAIL_INPUT_USD_PER_MTOK": "3.00",
    "DETAIL_OUTPUT_USD_PER_MTOK": "15.00",
}

USAGE = {
    "screening": {"input_tokens": 1_000_000, "output_tokens": 100_000},
    "detail": {"input_tokens": 1_000_000, "output_tokens": 200_000},
}


def test_cost_is_the_sum_over_stages_and_directions(monkeypatch):
    module = load_handler(monkeypatch, **FULL_RATES)
    # 1.00 + 0.5 + 3.00 + 3.00
    assert module._cost_usd(USAGE) == pytest.approx(7.50)


def test_cost_is_none_when_any_rate_is_missing(monkeypatch):
    """A sum over only the priced stages would read as a cheap image, not a missing rate."""
    partial = dict(FULL_RATES)
    del partial["DETAIL_OUTPUT_USD_PER_MTOK"]
    module = load_handler(monkeypatch, **partial)
    assert module._cost_usd(USAGE) is None


def test_cost_is_none_when_a_rate_is_not_a_number(monkeypatch):
    module = load_handler(monkeypatch, **dict(FULL_RATES, DETAIL_INPUT_USD_PER_MTOK="cheap"))
    assert module._cost_usd(USAGE) is None


def test_a_rate_is_not_needed_for_a_direction_with_no_tokens(monkeypatch):
    """An output-only rate cannot be required by a call that produced no output."""
    module = load_handler(
        monkeypatch, SCREENING_INPUT_USD_PER_MTOK="2.00", DETAIL_INPUT_USD_PER_MTOK="2.00"
    )
    usage = {"screening": {"input_tokens": 500_000, "output_tokens": 0}}
    assert module._cost_usd(usage) == pytest.approx(1.00)


# --------------------------------------------------------------------------------------
# _publish_metrics
# --------------------------------------------------------------------------------------


def published(module) -> dict[str, float]:
    call = module.cloudwatch_client.put_metric_data.call_args
    return {item["MetricName"]: item["Value"] for item in call[1]["MetricData"]}


def test_token_counts_are_published(monkeypatch):
    module = load_handler(monkeypatch)
    module.cloudwatch_client = MagicMock()
    module._publish_metrics({"status": "normal", "_token_usage": USAGE})
    metrics = published(module)
    assert metrics["InputTokens"] == 2_000_000
    assert metrics["OutputTokens"] == 300_000


def test_cost_per_image_is_published_when_the_rates_are_configured(monkeypatch):
    module = load_handler(monkeypatch, **FULL_RATES)
    module.cloudwatch_client = MagicMock()
    module._publish_metrics({"status": "normal", "_token_usage": USAGE})
    assert published(module)["CostPerImage"] == pytest.approx(7.50)


def test_cost_per_image_is_omitted_and_explained_when_no_rate_is_set(monkeypatch, caplog):
    module = load_handler(monkeypatch)
    module.cloudwatch_client = MagicMock()
    with caplog.at_level("INFO"):
        module._publish_metrics({"status": "normal", "_token_usage": USAGE})
    metrics = published(module)
    assert "CostPerImage" not in metrics
    assert "InputTokens" in metrics, "token counts must survive a missing rate"
    assert "USD_PER_MTOK" in " ".join(r.getMessage() for r in caplog.records)


def test_the_original_metrics_are_untouched_without_usage(monkeypatch):
    """A result from before this change carries no _token_usage and must still publish."""
    module = load_handler(monkeypatch)
    module.cloudwatch_client = MagicMock()
    module._publish_metrics({"status": "anomaly_detected", "overall_quality_score": 30})
    metrics = published(module)
    assert metrics == {"AnomalyDetected": 1.0, "QualityScore": 30.0}


def test_all_zero_counts_publish_no_token_metrics(monkeypatch):
    """Zero is how a response with no usage block arrives; it is not a measurement."""
    module = load_handler(monkeypatch)
    module.cloudwatch_client = MagicMock()
    module._publish_metrics(
        {"status": "normal", "_token_usage": {"screening": {"input_tokens": 0, "output_tokens": 0}}}
    )
    assert "InputTokens" not in published(module)
