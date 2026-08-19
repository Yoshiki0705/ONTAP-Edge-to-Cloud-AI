"""Unit tests for IoT Core → Lambda → S3 AP ingestion handler."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "cloud" / "iot_ingestion"))


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    """Set required environment variables."""
    monkeypatch.setenv(
        "S3AP_ACCESS_POINT_ARN",
        "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/iot-ingest-ap",
    )
    monkeypatch.setenv("DEVICE_PREFIX", "ingest")
    monkeypatch.setenv("BATCH_MODE", "false")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")


@pytest.fixture
def mock_s3():
    """Mock boto3 S3 client at module level."""
    mock = MagicMock()
    mock.put_object.return_value = {"ETag": '"test-etag-123"'}
    with patch("handler.s3_client", mock):
        yield mock


@pytest.fixture
def reload_handler(set_env, mock_s3):
    """Reload handler module and patch s3_client."""
    if "handler" in sys.modules:
        del sys.modules["handler"]
    import handler
    # Patch module-level S3AP_ARN and s3_client
    handler.S3AP_ARN = "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/iot-ingest-ap"
    handler.s3_client = mock_s3
    return handler


class TestSingleMessageMode:
    """Tests for direct IoT Core → Lambda invocation (single message)."""

    def test_single_message_writes_json(self, mock_s3, reload_handler):
        """Single MQTT message is written as JSON to S3 AP."""
        event = {
            "device_id": "rpi5-001",
            "temperature": 23.5,
            "humidity": 67.2,
            "timestamp": "2026-07-27T10:00:00Z",
        }

        result = reload_handler.handler(event, None)

        assert result["statusCode"] == 200
        assert result["body"]["device_id"] == "rpi5-001"
        assert result["body"]["etag"] == '"test-etag-123"'

        # Verify put_object call
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/iot-ingest-ap"
        assert call_kwargs["Key"].startswith("ingest/rpi5-001/year=")
        assert call_kwargs["Key"].endswith(".json")
        assert call_kwargs["ContentType"] == "application/json"

        # Verify body contains original event data
        written_body = json.loads(call_kwargs["Body"])
        assert written_body["temperature"] == 23.5
        assert written_body["device_id"] == "rpi5-001"

    def test_single_message_uses_source_id_fallback(self, mock_s3, reload_handler):
        """Falls back to source_id when device_id not present."""
        event = {
            "source_id": "sensor-array-003",
            "vibration_rms": 0.42,
        }

        result = reload_handler.handler(event, None)

        assert result["statusCode"] == 200
        assert result["body"]["device_id"] == "sensor-array-003"
        assert "sensor-array-003" in mock_s3.put_object.call_args[1]["Key"]

    def test_single_message_uses_unknown_when_no_id(self, mock_s3, reload_handler):
        """Uses 'unknown' when neither device_id nor source_id present."""
        event = {"value": 42}

        result = reload_handler.handler(event, None)

        assert result["body"]["device_id"] == "unknown"
        assert "unknown" in mock_s3.put_object.call_args[1]["Key"]

    def test_metadata_includes_device_and_source(self, mock_s3, reload_handler):
        """S3 user metadata includes device-id and source info."""
        event = {"device_id": "rpi5-001", "data": "test"}

        reload_handler.handler(event, None)

        metadata = mock_s3.put_object.call_args[1]["Metadata"]
        assert metadata["device-id"] == "rpi5-001"
        assert metadata["source"] == "iot-core-rule"
        assert "ingest-time" in metadata


class TestSQSBatchMode:
    """Tests for SQS batch invocation (IoT Core → SQS → Lambda)."""

    def test_sqs_batch_writes_ndjson(self, mock_s3, reload_handler):
        """SQS batch with multiple records is written as NDJSON."""
        event = {
            "Records": [
                {"body": json.dumps({"device_id": "rpi5-001", "temp": 23.5})},
                {"body": json.dumps({"device_id": "rpi5-001", "temp": 24.0})},
                {"body": json.dumps({"device_id": "rpi5-001", "temp": 24.2})},
            ]
        }

        result = reload_handler.handler(event, None)

        assert result["statusCode"] == 200
        assert result["body"]["record_count"] == 3
        assert result["body"]["format"] == "ndjson"

        # Verify NDJSON content
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["ContentType"] == "application/x-ndjson"
        body_lines = call_kwargs["Body"].decode().strip().split("\n")
        assert len(body_lines) == 3
        assert json.loads(body_lines[0])["temp"] == 23.5
        assert json.loads(body_lines[2])["temp"] == 24.2

    def test_sqs_batch_skips_malformed_records(self, mock_s3, reload_handler):
        """Malformed SQS records are skipped without failing."""
        event = {
            "Records": [
                {"body": json.dumps({"device_id": "rpi5-001", "temp": 23.5})},
                {"body": "not valid json {{{"},
                {"body": json.dumps({"device_id": "rpi5-001", "temp": 25.0})},
            ]
        }

        result = reload_handler.handler(event, None)

        assert result["statusCode"] == 200
        assert result["body"]["record_count"] == 2

    def test_sqs_batch_empty_records(self, mock_s3, reload_handler):
        """Empty Records list returns success with no-op."""
        event = {"Records": []}

        result = reload_handler.handler(event, None)

        assert result["statusCode"] == 200
        assert result["body"]["message"] == "No records"
        mock_s3.put_object.assert_not_called()

    def test_sqs_batch_all_malformed(self, mock_s3, reload_handler):
        """All malformed records returns success with no valid messages."""
        event = {
            "Records": [
                {"body": "invalid1"},
                {"body": "invalid2"},
            ]
        }

        result = reload_handler.handler(event, None)

        assert result["statusCode"] == 200
        assert result["body"]["message"] == "No valid messages"
        mock_s3.put_object.assert_not_called()

    def test_sqs_batch_metadata_includes_record_count(self, mock_s3, reload_handler):
        """S3 user metadata includes record count for batch."""
        event = {
            "Records": [
                {"body": json.dumps({"device_id": "rpi5-001", "v": 1})},
                {"body": json.dumps({"device_id": "rpi5-001", "v": 2})},
            ]
        }

        reload_handler.handler(event, None)

        metadata = mock_s3.put_object.call_args[1]["Metadata"]
        assert metadata["record-count"] == "2"
        assert metadata["source"] == "iot-core-sqs-batch"
        assert metadata["format"] == "ndjson"


class TestKeyGeneration:
    """Tests for Hive-partitioned key generation."""

    def test_key_format_matches_directory_design(self, mock_s3, reload_handler):
        """Generated key follows the documented directory structure."""
        event = {"device_id": "rpi5-001", "value": 42}

        reload_handler.handler(event, None)

        key = mock_s3.put_object.call_args[1]["Key"]
        parts = key.split("/")
        assert parts[0] == "ingest"
        assert parts[1] == "rpi5-001"
        assert parts[2].startswith("year=")
        assert parts[3].startswith("month=")
        assert parts[4].startswith("day=")
        assert parts[5].startswith("hour=")
        assert parts[6].endswith(".json")


class TestErrorHandling:
    """Tests for error conditions."""

    def test_missing_s3ap_arn_raises(self, monkeypatch, mock_s3):
        """Missing S3AP_ACCESS_POINT_ARN raises ValueError caught as 500."""
        monkeypatch.setenv("S3AP_ACCESS_POINT_ARN", "")
        if "handler" in sys.modules:
            del sys.modules["handler"]
        import handler

        # Patch the module-level variable
        handler.S3AP_ARN = ""
        handler.s3_client = mock_s3

        result = handler.handler({"device_id": "test", "v": 1}, None)
        assert result["statusCode"] == 500
        assert "S3AP_ACCESS_POINT_ARN" in result["body"]["error"]

    def test_s3_error_returns_500(self, mock_s3, reload_handler):
        """S3 client error returns 500 status."""
        from botocore.exceptions import ClientError

        mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "test"}},
            "PutObject",
        )

        result = reload_handler.handler({"device_id": "rpi5-001", "v": 1}, None)

        assert result["statusCode"] == 500
        assert "error" in result["body"]


class TestParquetFallbackIsAudible:
    """BatchMode=true with no PyArrow layer writes NDJSON. It must say so.

    `PyArrowLayerArn` defaults to empty and nothing requires it, so this combination
    is a deploy CloudFormation accepts. Until the warning was added the only trace
    was the response `format` field, which nothing reads: a Glue table with a Parquet
    SerDe returns zero rows over a prefix full of NDJSON, and no invocation fails.
    """

    @staticmethod
    def _batch_event():
        return {
            "Records": [
                {"body": json.dumps({"device_id": "rpi5-001", "temp": 23.5})},
                {"body": json.dumps({"device_id": "rpi5-001", "temp": 24.0})},
            ]
        }

    def test_warns_and_writes_ndjson_when_pyarrow_is_missing(
        self, monkeypatch, mock_s3, caplog
    ):
        monkeypatch.setenv("BATCH_MODE", "true")
        if "handler" in sys.modules:
            del sys.modules["handler"]
        import handler

        handler.s3_client = mock_s3
        monkeypatch.setattr(handler, "_parquet_available", lambda: False)
        handler._parquet_fallback_warned = False

        with caplog.at_level("WARNING"):
            result = handler.handler(self._batch_event(), None)

        assert result["body"]["format"] == "ndjson"
        assert mock_s3.put_object.call_args[1]["ContentType"] == "application/x-ndjson"
        messages = " ".join(record.getMessage() for record in caplog.records)
        assert "pyarrow" in messages
        assert "PyArrowLayerArn" in messages, "the warning must name the fix"

    def test_warns_once_per_container(self, monkeypatch, mock_s3, caplog):
        """The import cannot start succeeding mid-container; repeating adds no signal."""
        monkeypatch.setenv("BATCH_MODE", "true")
        if "handler" in sys.modules:
            del sys.modules["handler"]
        import handler

        handler.s3_client = mock_s3
        monkeypatch.setattr(handler, "_parquet_available", lambda: False)
        handler._parquet_fallback_warned = False

        with caplog.at_level("WARNING"):
            for _ in range(3):
                handler.handler(self._batch_event(), None)

        fallback = [r for r in caplog.records if "pyarrow" in r.getMessage()]
        assert len(fallback) == 1, f"expected one warning, got {len(fallback)}"

    def test_stays_quiet_when_parquet_is_available(self, monkeypatch, mock_s3, caplog):
        """No warning when the layer is attached and Parquet is actually written."""
        monkeypatch.setenv("BATCH_MODE", "true")
        if "handler" in sys.modules:
            del sys.modules["handler"]
        import handler

        handler.s3_client = mock_s3
        monkeypatch.setattr(handler, "_parquet_available", lambda: True)
        monkeypatch.setattr(
            handler,
            "_write_parquet_batch",
            lambda *a, **k: {"statusCode": 200, "body": {"format": "parquet"}},
        )
        handler._parquet_fallback_warned = False

        with caplog.at_level("WARNING"):
            result = handler.handler(self._batch_event(), None)

        assert result["body"]["format"] == "parquet"
        assert not [r for r in caplog.records if "pyarrow" in r.getMessage()]

    def test_stays_quiet_when_batch_mode_is_off(self, monkeypatch, mock_s3, caplog):
        """NDJSON with BatchMode=false is the configured outcome, not a degradation."""
        monkeypatch.setenv("BATCH_MODE", "false")
        if "handler" in sys.modules:
            del sys.modules["handler"]
        import handler

        handler.s3_client = mock_s3
        monkeypatch.setattr(handler, "_parquet_available", lambda: False)
        handler._parquet_fallback_warned = False

        with caplog.at_level("WARNING"):
            result = handler.handler(self._batch_event(), None)

        assert result["body"]["format"] == "ndjson"
        assert not [r for r in caplog.records if "pyarrow" in r.getMessage()]
