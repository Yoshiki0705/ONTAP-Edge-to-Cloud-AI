"""Unit tests for unified event schema builder."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "edge" / "raspberry-pi" / "common"))

from event_schema import build_event  # noqa: E402


class TestBuildEvent:
    """Tests for build_event function."""

    def test_creates_valid_event_envelope(self):
        """All required fields are present in the output."""
        event = build_event(
            event_type="payload_arrival",
            event_category="quality_inspection",
            source_id="rpi5-001",
            asset_type="3d_printer",
            asset_id="bambu-p2s-001",
            equipment_id="printer-001",
            sensor_id="camera-001",
        )

        required_fields = [
            "event_id", "event_type", "domain", "event_category",
            "source_id", "asset_type", "asset_id", "site_id", "line_id",
            "equipment_id", "sensor_id", "timestamp", "ingest_time",
            "schema_version", "payload_uri", "payload_type", "content_type",
            "checksum", "size_bytes", "lineage_id", "processing_status", "metadata",
        ]
        for field in required_fields:
            assert field in event, f"Missing field: {field}"

    def test_event_id_is_uuid(self):
        """event_id is a valid UUID v4."""
        import uuid

        event = build_event(
            event_type="sensor_event",
            event_category="environmental_monitoring",
            source_id="rpi5-002",
            asset_type="sensor_array",
            asset_id="env-sensor-001",
            equipment_id="sensor-rack-01",
            sensor_id="dht22-001",
        )

        # Should not raise
        parsed = uuid.UUID(event["event_id"])
        assert parsed.version == 4

    def test_schema_version_is_v2(self):
        """Schema version matches v3-aligned format."""
        event = build_event(
            event_type="telemetry_event",
            event_category="storage_health",
            source_id="rpi5-001",
            asset_type="storage_system",
            asset_id="cluster-01",
            equipment_id="node-01",
            sensor_id="rest-api",
        )

        assert event["schema_version"] == "2.0.0"

    def test_checksum_calculated_from_payload_bytes(self):
        """checksum and size_bytes are computed from payload_bytes."""
        test_bytes = b"test image data" * 100

        event = build_event(
            event_type="payload_arrival",
            event_category="quality_inspection",
            source_id="rpi5-001",
            asset_type="3d_printer",
            asset_id="bambu-p2s-001",
            equipment_id="printer-001",
            sensor_id="camera-001",
            payload_bytes=test_bytes,
        )

        assert event["checksum"].startswith("sha256:")
        assert event["size_bytes"] == len(test_bytes)

    def test_no_checksum_when_no_payload_bytes(self):
        """checksum and size_bytes are None when payload_bytes is not provided."""
        event = build_event(
            event_type="sensor_event",
            event_category="environmental_monitoring",
            source_id="rpi5-002",
            asset_type="sensor_array",
            asset_id="env-sensor-001",
            equipment_id="sensor-rack-01",
            sensor_id="dht22-001",
        )

        assert event["checksum"] is None
        assert event["size_bytes"] is None

    def test_metadata_passed_through(self):
        """Custom metadata is included in the event."""
        meta = {"temperature_celsius": 24.5, "humidity_percent": 45.2}

        event = build_event(
            event_type="sensor_event",
            event_category="environmental_monitoring",
            source_id="rpi5-002",
            asset_type="sensor_array",
            asset_id="env-sensor-001",
            equipment_id="sensor-rack-01",
            sensor_id="dht22-001",
            metadata=meta,
        )

        assert event["metadata"] == meta

    @patch.dict("os.environ", {"SITE_ID": "factory-a", "LINE_ID": "line-03"})
    def test_site_from_environment(self):
        """site_id and line_id come from environment variables."""
        import importlib
        import event_schema

        importlib.reload(event_schema)

        event = event_schema.build_event(
            event_type="payload_arrival",
            event_category="quality_inspection",
            source_id="rpi5-001",
            asset_type="3d_printer",
            asset_id="bambu-p2s-001",
            equipment_id="printer-001",
            sensor_id="camera-001",
        )

        assert event["site_id"] == "factory-a"
        assert event["line_id"] == "line-03"

    def test_payload_uri_included(self):
        """payload_uri is set when provided."""
        event = build_event(
            event_type="payload_arrival",
            event_category="quality_inspection",
            source_id="rpi5-001",
            asset_type="3d_printer",
            asset_id="bambu-p2s-001",
            equipment_id="printer-001",
            sensor_id="camera-001",
            payload_uri="nfs://svm-iot/vol_images/2026/06/14/test.jpg",
            payload_type="image",
            content_type="image/jpeg",
        )

        assert event["payload_uri"] == "nfs://svm-iot/vol_images/2026/06/14/test.jpg"
        assert event["payload_type"] == "image"
        assert event["content_type"] == "image/jpeg"
