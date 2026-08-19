"""Unified event schema builder (v3 aligned).

Creates structured events compatible with Kafka → ClickHouse → Databricks pipeline.
See docs/*/data-schema-design.md for full schema specification.
"""

import hashlib
import os
import uuid
from datetime import UTC, datetime

# Factory hierarchy configuration (via environment variables)
SITE_ID = os.getenv("SITE_ID", "lab-tokyo")
LINE_ID = os.getenv("LINE_ID", "line-01")
DOMAIN = os.getenv("EVENT_DOMAIN", "manufacturing")
SCHEMA_VERSION = "2.0.0"


def build_event(
    event_type: str,
    event_category: str,
    source_id: str,
    asset_type: str,
    asset_id: str,
    equipment_id: str,
    sensor_id: str,
    timestamp: str | None = None,
    payload_uri: str | None = None,
    payload_type: str | None = None,
    content_type: str | None = None,
    payload_bytes: bytes | None = None,
    lineage_id: str | None = None,
    processing_status: str = "pending_analysis",
    metadata: dict | None = None,
) -> dict:
    """Build a v3-aligned event envelope.

    Args:
        event_type: payload_arrival / sensor_event / quality_event / anomaly_event / telemetry_event
        event_category: quality_inspection / environmental_monitoring / equipment_telemetry / storage_health
        source_id: Device ID emitting the event
        asset_type: 3d_printer / cnc_machine / storage_system / sensor_array
        asset_id: Individual asset identifier
        equipment_id: Equipment identifier
        sensor_id: Sensor / camera identifier
        timestamp: ISO 8601 UTC (auto-generated if None)
        payload_uri: NFS or S3 URI for associated payload
        payload_type: image / video / csv / json / binary
        content_type: MIME type
        payload_bytes: Raw bytes for checksum calculation
        lineage_id: Session/batch tracking ID (auto-generated daily if None)
        processing_status: pending_analysis / analyzing / completed / failed
        metadata: Event-type-specific additional data

    Returns:
        dict: Complete event envelope ready for Kafka publish
    """
    now = datetime.now(UTC)

    if timestamp is None:
        timestamp = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    if lineage_id is None:
        lineage_id = f"session-{now.strftime('%Y-%m-%d')}"

    checksum = None
    size_bytes = None
    if payload_bytes is not None:
        checksum = f"sha256:{hashlib.sha256(payload_bytes).hexdigest()}"
        size_bytes = len(payload_bytes)

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "domain": DOMAIN,
        "event_category": event_category,
        "source_id": source_id,
        "asset_type": asset_type,
        "asset_id": asset_id,
        "site_id": SITE_ID,
        "line_id": LINE_ID,
        "equipment_id": equipment_id,
        "sensor_id": sensor_id,
        "timestamp": timestamp,
        "ingest_time": now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "schema_version": SCHEMA_VERSION,
        "payload_uri": payload_uri,
        "payload_type": payload_type,
        "content_type": content_type,
        "checksum": checksum,
        "size_bytes": size_bytes,
        "lineage_id": lineage_id,
        "processing_status": processing_status,
        "metadata": metadata or {},
    }

    return event
