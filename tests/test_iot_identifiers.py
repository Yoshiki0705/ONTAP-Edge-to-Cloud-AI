"""Guard tests for untrusted device identifiers reaching S3 keys.

These are regression tests for a measured defect, not hypotheticals. Before the
fix, `handler._build_key("../../../etc/shadow", ...)` returned
`ingest/../../../etc/shadow/year=2026/.../<id>.json`, and a CR/LF in the same
value reached a PutObject metadata header.

Three outcome classes are covered deliberately:
  block  — the value is rejected and no S3 call happens
  ask    — an ambiguous-but-legal value is accepted only from a trusted field
  allow  — an ordinary identifier still works end to end
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "cloud" / "iot_ingestion"))

import identifiers  # noqa: E402

TS = datetime(2026, 8, 19, 12, 30, tzinfo=timezone.utc)

# Values that must never reach an S3 key. Each is the shape of a real problem:
# prefix escape, extra partition levels, header injection, wrong type.
REJECTED = [
    "../../../etc/shadow",
    "../../other-tenant",
    "..",
    ".",
    "./x",
    "a/b/c",
    "/absolute",
    "trailing/",
    "a\r\nX-Injected: 1",
    "a\nb",
    "a\tb",
    "with space",
    "",
    "-leading-hyphen",
    ".leading-dot",
    "日本語",
    "x" * 129,
    None,
    123,
    {"nested": "dict"},
]

ACCEPTED = [
    "pi-001",
    "rpi5-001",
    "greengrass_core_01",
    "sensor.line3.temp",
    "urn:dev:ops:32473-1",
    "A1",
    "x" * 128,
]


@pytest.mark.parametrize("value", REJECTED)
def test_validate_device_id_blocks(value):
    with pytest.raises(identifiers.UnsafeIdentifierError):
        identifiers.validate_device_id(value)


@pytest.mark.parametrize("value", ACCEPTED)
def test_validate_device_id_allows(value):
    assert identifiers.validate_device_id(value) == value


def test_resolve_prefers_client_id_over_payload():
    """The payload field must not shadow the IoT Core-attached identity."""
    event = {
        "client_id": "rpi5-001",
        "topic_device_id": "rpi5-001",
        "device_id": "spoofed",
        "source_id": "also-spoofed",
    }
    assert identifiers.resolve_device_id(event) == "rpi5-001"


def test_resolve_falls_back_to_topic_then_payload():
    assert identifiers.resolve_device_id({"topic_device_id": "t-1", "device_id": "p-1"}) == "t-1"
    assert identifiers.resolve_device_id({"device_id": "p-1"}) == "p-1"
    assert identifiers.resolve_device_id({}, fallback="mixed") == "mixed"


def test_resolve_does_not_silently_replace_a_bad_value():
    """A bad trusted-field value must raise, not fall through to the next field.

    Falling through would let a publisher suppress its own authenticated id by
    sending a malformed one and have the payload field used instead.
    """
    with pytest.raises(identifiers.UnsafeIdentifierError):
        identifiers.resolve_device_id({"client_id": "../evil", "device_id": "pi-001"})


def test_empty_trusted_field_is_skipped_not_rejected():
    """IoT Core omits/blanks a field rather than removing the key; that is legal."""
    assert identifiers.resolve_device_id({"client_id": "", "device_id": "pi-001"}) == "pi-001"


class TestHandlerIntegration:
    """The invariant must hold at the S3 boundary, not only in the validator."""

    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch):
        monkeypatch.setenv("S3AP_ACCESS_POINT_ARN", "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/ap")
        monkeypatch.setenv("DEVICE_PREFIX", "ingest")
        monkeypatch.setenv("BATCH_MODE", "false")
        monkeypatch.setenv("LOG_LEVEL", "CRITICAL")

    @staticmethod
    def _fresh_handler():
        """Import the handler after env is set, so module constants pick it up."""
        for name in ("handler",):
            sys.modules.pop(name, None)
        import handler

        return handler

    def test_build_key_rejects_traversal(self):
        handler = self._fresh_handler()
        with pytest.raises(identifiers.UnsafeIdentifierError):
            handler._build_key("../../../etc/shadow", TS, "json")

    def test_build_key_allows_normal_id(self):
        handler = self._fresh_handler()
        key = handler._build_key("pi-001", TS, "json")
        assert key.startswith("ingest/pi-001/year=2026/month=08/day=19/hour=12/")
        assert ".." not in key
        assert key.endswith(".json")

    def test_traversal_payload_returns_400_and_writes_nothing(self):
        handler = self._fresh_handler()
        mock_s3 = MagicMock()
        with patch.object(handler, "s3_client", mock_s3):
            result = handler.handler({"device_id": "../../../etc/shadow"}, None)
        assert result["statusCode"] == 400
        mock_s3.put_object.assert_not_called()

    def test_normal_payload_writes_a_contained_key(self):
        handler = self._fresh_handler()
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {"ETag": '"e"'}
        with patch.object(handler, "s3_client", mock_s3):
            result = handler.handler({"device_id": "pi-001", "temp": 21.5}, None)
        assert result["statusCode"] == 200
        key = mock_s3.put_object.call_args.kwargs["Key"]
        assert key.startswith("ingest/pi-001/")
        assert ".." not in key

    def test_client_id_wins_over_spoofed_payload_device_id(self):
        handler = self._fresh_handler()
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {"ETag": '"e"'}
        event = {"client_id": "rpi5-001", "device_id": "victim-device"}
        with patch.object(handler, "s3_client", mock_s3):
            handler.handler(event, None)
        key = mock_s3.put_object.call_args.kwargs["Key"]
        assert key.startswith("ingest/rpi5-001/")

    def test_metadata_header_value_is_header_safe(self):
        """device-id goes into an HTTP header; CR/LF must never get there."""
        handler = self._fresh_handler()
        mock_s3 = MagicMock()
        with patch.object(handler, "s3_client", mock_s3):
            result = handler.handler({"device_id": "a\r\nX-Injected: 1"}, None)
        assert result["statusCode"] == 400
        mock_s3.put_object.assert_not_called()

    def test_sqs_batch_rejects_traversal(self):
        handler = self._fresh_handler()
        mock_s3 = MagicMock()
        event = {"Records": [{"body": '{"device_id": "../../escape"}'}]}
        with patch.object(handler, "s3_client", mock_s3):
            result = handler.handler(event, None)
        assert result["statusCode"] == 400
        mock_s3.put_object.assert_not_called()
