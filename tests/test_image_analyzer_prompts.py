"""The prompts the image analyzer runs are configuration, not code.

usecases/visual-inspection is documented as the same handler as 3d-print-quality with only
the prompt changed. That was prose until the prompts became environment variables: the
handler hardcoded 3D-print text, the template passed none, and the stack deployed cleanly
and then looked for stringing and spaghetti on a metal part.

These tests pin the three properties that make the override trustworthy:

  * absent variable  -> the 3D print defaults, so 3d-print-quality is unaffected
  * set variable     -> used verbatim, so a use case can retarget the handler
  * empty variable   -> falls back, because an empty prompt makes the model answer
                        something rather than fail, and the result parses as absent
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HANDLER = Path(__file__).resolve().parents[1] / "cloud" / "ai" / "image_analyzer" / "handler.py"


def load_handler(monkeypatch: pytest.MonkeyPatch, **environment: str):
    """Import the handler with a given environment.

    The prompts are resolved at import time, so the module has to be loaded afresh for each
    case rather than reloaded from sys.modules.
    """
    for name in ("SCREENING_PROMPT", "DETAIL_PROMPT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    spec = importlib.util.spec_from_file_location("image_analyzer_under_test", HANDLER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["image_analyzer_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_defaults_inspect_a_3d_print(monkeypatch):
    module = load_handler(monkeypatch)
    assert "3D print" in module.SCREENING_PROMPT
    assert "3D printing quality inspector" in module.DETAIL_PROMPT


def test_a_use_case_can_retarget_both_prompts(monkeypatch):
    module = load_handler(
        monkeypatch,
        SCREENING_PROMPT="Any visible defect on this part?",
        DETAIL_PROMPT="You are a manufacturing quality inspector.",
    )
    assert module.SCREENING_PROMPT == "Any visible defect on this part?"
    assert module.DETAIL_PROMPT == "You are a manufacturing quality inspector."
    assert "3D print" not in module.DETAIL_PROMPT


@pytest.mark.parametrize("variable", ["SCREENING_PROMPT", "DETAIL_PROMPT"])
def test_an_empty_variable_falls_back_rather_than_shipping_an_empty_prompt(monkeypatch, variable):
    module = load_handler(monkeypatch, **{variable: ""})
    assert getattr(module, variable).strip(), f"{variable} resolved to an empty prompt"


def test_the_default_prompts_ask_for_every_key_the_handler_parses(monkeypatch):
    """A prompt that omits a key is not a parse error — the value reads as absent.

    `status` is the one that matters most: only "anomaly_detected" raises an alert, so a
    prompt offering a different vocabulary finds defects and reports none.
    """
    module = load_handler(monkeypatch)
    assert "has_defect" in module.SCREENING_PROMPT
    assert "confidence" in module.SCREENING_PROMPT
    for key in ("status", "anomaly_detected", "confidence", "anomalies"):
        assert key in module.DETAIL_PROMPT, f"the default detail prompt never asks for {key}"


def test_the_prompts_fit_the_lambda_environment_limit(monkeypatch):
    """AWS Lambda caps all environment variables at 4 KB combined.

    Both prompts plus the other variables have to fit, so a much longer prompt belongs in
    Amazon S3 or a layer. This asserts the shipped defaults leave room rather than sitting
    at the edge of the limit.
    """
    module = load_handler(monkeypatch)
    total = len(module.SCREENING_PROMPT.encode()) + len(module.DETAIL_PROMPT.encode())
    assert total < 3072, f"the default prompts already use {total} B of the 4 KB budget"
