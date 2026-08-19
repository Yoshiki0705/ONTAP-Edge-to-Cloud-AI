"""Unit tests for Greengrass S3 AP client component."""

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "edge" / "greengrass"))

from s3ap_client.buffer import S3APBuffer
from s3ap_client.config import BufferConfig, ComponentConfig, RetryConfig, S3APConfig
from s3ap_client.uploader import S3APUploader, S3APUploadError


# ============================================================
# S3APBuffer Tests
# ============================================================


class TestS3APBuffer:
    """Tests for S3APBuffer (SQLite offline persistence)."""

    @pytest.fixture
    def buffer(self, tmp_path):
        """Create a buffer with temp DB path."""
        config = BufferConfig.__new__(BufferConfig)
        object.__setattr__(config, "db_path", str(tmp_path / "test.db"))
        object.__setattr__(config, "max_size_mb", 100)
        object.__setattr__(config, "flush_batch_size", 5)
        object.__setattr__(config, "flush_interval_seconds", 10)

        buf = S3APBuffer(config)
        buf.open()
        yield buf
        buf.close()

    def test_enqueue_and_count(self, buffer):
        """Basic enqueue increments pending count."""
        assert buffer.pending_count() == 0

        buffer.enqueue(
            s3_key="ingest/rpi5-001/year=2026/month=07/day=27/hour=10/abc.json",
            data_path="/tmp/abc.json",
            content_type="application/json",
            size_bytes=1024,
        )
        assert buffer.pending_count() == 1

    def test_peek_returns_fifo(self, buffer):
        """Peek returns oldest entries first."""
        buffer.enqueue(s3_key="key1", data_path="/tmp/1", size_bytes=10)
        buffer.enqueue(s3_key="key2", data_path="/tmp/2", size_bytes=20)
        buffer.enqueue(s3_key="key3", data_path="/tmp/3", size_bytes=30)

        entries = buffer.peek(batch_size=2)
        assert len(entries) == 2
        assert entries[0]["s3_key"] == "key1"
        assert entries[1]["s3_key"] == "key2"

    def test_remove_deletes_entry(self, buffer):
        """Remove decrements pending count."""
        entry_id = buffer.enqueue(s3_key="key1", data_path="/tmp/1", size_bytes=10)
        assert buffer.pending_count() == 1

        buffer.remove(entry_id)
        assert buffer.pending_count() == 0

    def test_mark_failed_increments_retry(self, buffer):
        """mark_failed increments retry_count and stores error."""
        entry_id = buffer.enqueue(s3_key="key1", data_path="/tmp/1", size_bytes=10)

        buffer.mark_failed(entry_id, "Connection timeout")
        entries = buffer.peek()
        assert entries[0]["retry_count"] == 1
        assert entries[0]["last_error"] == "Connection timeout"

        buffer.mark_failed(entry_id, "DNS failure")
        entries = buffer.peek()
        assert entries[0]["retry_count"] == 2
        assert entries[0]["last_error"] == "DNS failure"

    def test_metadata_stored_and_retrieved(self, buffer):
        """S3 user metadata is JSON-serialized and retrieved correctly."""
        meta = {"device-id": "rpi5-001", "source": "camera"}
        buffer.enqueue(
            s3_key="key1",
            data_path="/tmp/1",
            content_type="image/jpeg",
            metadata=meta,
            size_bytes=5000,
        )

        entries = buffer.peek()
        assert entries[0]["metadata"] == meta
        assert entries[0]["content_type"] == "image/jpeg"
        assert entries[0]["size_bytes"] == 5000

    def test_context_manager(self, tmp_path):
        """Buffer works as context manager."""
        config = BufferConfig.__new__(BufferConfig)
        object.__setattr__(config, "db_path", str(tmp_path / "ctx.db"))
        object.__setattr__(config, "max_size_mb", 100)
        object.__setattr__(config, "flush_batch_size", 5)
        object.__setattr__(config, "flush_interval_seconds", 10)

        with S3APBuffer(config) as buf:
            buf.enqueue(s3_key="key1", data_path="/tmp/1", size_bytes=10)
            assert buf.pending_count() == 1


# ============================================================
# S3APUploader Tests
# ============================================================


class TestS3APUploader:
    """Tests for S3APUploader (PutObject with retry)."""

    @pytest.fixture
    def mock_s3(self):
        """Create mock S3 client."""
        return MagicMock()

    @pytest.fixture
    def s3ap_config(self):
        """S3 AP config with test ARN."""
        config = S3APConfig.__new__(S3APConfig)
        object.__setattr__(
            config,
            "access_point_arn",
            "arn:aws:s3:ap-northeast-1:123456789012:accesspoint/iot-ingest-ap",
        )
        object.__setattr__(config, "access_point_alias", "")
        object.__setattr__(config, "region", "ap-northeast-1")
        return config

    @pytest.fixture
    def retry_config(self):
        """Fast retry config for testing."""
        config = RetryConfig.__new__(RetryConfig)
        object.__setattr__(config, "max_retries", 3)
        object.__setattr__(config, "base_delay_seconds", 0.01)
        object.__setattr__(config, "max_delay_seconds", 0.05)
        object.__setattr__(config, "dead_letter_max_retries", 10)
        return config

    def test_upload_success(self, mock_s3, s3ap_config, retry_config):
        """Successful upload calls put_object with correct params."""
        mock_s3.put_object.return_value = {"ETag": '"abc123"'}

        uploader = S3APUploader(s3ap_config, retry_config, s3_client=mock_s3)
        result = uploader.upload(
            key="ingest/rpi5-001/year=2026/month=07/day=27/hour=10/data.json",
            body=b'{"temperature": 23.5}',
            content_type="application/json",
            metadata={"device-id": "rpi5-001"},
        )

        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == s3ap_config.access_point_arn
        assert call_kwargs["Key"] == "ingest/rpi5-001/year=2026/month=07/day=27/hour=10/data.json"
        assert call_kwargs["Body"] == b'{"temperature": 23.5}'
        assert call_kwargs["ContentType"] == "application/json"
        assert call_kwargs["Metadata"] == {"device-id": "rpi5-001"}
        assert result["ETag"] == '"abc123"'

    def test_upload_retries_on_failure(self, mock_s3, s3ap_config, retry_config):
        """Upload retries on transient errors."""
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "InternalError", "Message": "Service error"}}
        mock_s3.put_object.side_effect = [
            ClientError(error_response, "PutObject"),
            ClientError(error_response, "PutObject"),
            {"ETag": '"success"'},  # Third attempt succeeds
        ]

        uploader = S3APUploader(s3ap_config, retry_config, s3_client=mock_s3)
        result = uploader.upload(key="test/key.json", body=b"data")

        assert mock_s3.put_object.call_count == 3
        assert result["ETag"] == '"success"'

    def test_upload_raises_after_max_retries(self, mock_s3, s3ap_config, retry_config):
        """Upload raises S3APUploadError after exhausting retries."""
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "InternalError", "Message": "Persistent failure"}}
        mock_s3.put_object.side_effect = ClientError(error_response, "PutObject")

        uploader = S3APUploader(s3ap_config, retry_config, s3_client=mock_s3)

        with pytest.raises(S3APUploadError) as exc_info:
            uploader.upload(key="test/key.json", body=b"data")

        assert exc_info.value.attempts == 3
        assert "Persistent failure" in exc_info.value.last_error
        assert mock_s3.put_object.call_count == 3

    def test_upload_raises_if_no_target(self, mock_s3, retry_config):
        """Upload raises ValueError if no AP ARN or alias configured."""
        empty_config = S3APConfig.__new__(S3APConfig)
        object.__setattr__(empty_config, "access_point_arn", "")
        object.__setattr__(empty_config, "access_point_alias", "")
        object.__setattr__(empty_config, "region", "ap-northeast-1")

        uploader = S3APUploader(empty_config, retry_config, s3_client=mock_s3)

        with pytest.raises(ValueError, match="S3 AP target not configured"):
            uploader.upload(key="test/key.json", body=b"data")

    def test_upload_uses_alias_when_arn_empty(self, mock_s3, retry_config):
        """Uses AP alias as Bucket when ARN is empty."""
        alias_config = S3APConfig.__new__(S3APConfig)
        object.__setattr__(alias_config, "access_point_arn", "")
        object.__setattr__(alias_config, "access_point_alias", "iot-ingest-ap-s3alias")
        object.__setattr__(alias_config, "region", "ap-northeast-1")

        mock_s3.put_object.return_value = {"ETag": '"xyz"'}
        uploader = S3APUploader(alias_config, retry_config, s3_client=mock_s3)
        uploader.upload(key="test/key.json", body=b"data")

        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "iot-ingest-ap-s3alias"

    def test_build_key_hive_partitioned(self, mock_s3, s3ap_config, retry_config):
        """build_key produces correct Hive-partitioned path."""
        uploader = S3APUploader(s3ap_config, retry_config, s3_client=mock_s3)

        ts = datetime(2026, 7, 27, 14, 30, 0, tzinfo=timezone.utc)
        key = uploader.build_key(
            device_id="rpi5-001",
            data_type="image/jpeg",
            filename="capture_001.jpg",
            timestamp=ts,
        )

        assert key == "ingest/rpi5-001/year=2026/month=07/day=27/hour=14/capture_001.jpg"

    def test_build_key_defaults_to_now(self, mock_s3, s3ap_config, retry_config):
        """build_key uses current time when timestamp not provided."""
        uploader = S3APUploader(s3ap_config, retry_config, s3_client=mock_s3)
        key = uploader.build_key(
            device_id="rpi5-002",
            data_type="application/json",
            filename="telemetry.json",
        )
        assert key.startswith("ingest/rpi5-002/year=")
        assert "telemetry.json" in key
