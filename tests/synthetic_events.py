"""Synthetic event generator for testing Kafka → ClickHouse pipeline.

Generates realistic v3-aligned events without requiring physical devices.
Use for:
  - Kafka connectivity testing
  - ClickHouse DDL validation
  - Materialized View verification
  - Dashboard development
  - E2E pipeline testing

Usage:
    # Generate events to stdout (for inspection)
    python synthetic_events.py --count 10 --stdout

    # Publish to Kafka
    KAFKA_ENABLED=true KAFKA_BOOTSTRAP_SERVERS=<broker>:9092 \
      python synthetic_events.py --count 100 --interval 1.0

    # Generate all event types
    python synthetic_events.py --count 50 --types all
"""

import argparse
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add common module path
sys.path.insert(0, str(Path(__file__).parent.parent / "edge" / "raspberry-pi" / "common"))
from event_schema import build_event
from kafka_producer import EventPublisher


# Synthetic data configuration
SITES = ["lab-tokyo", "factory-a"]
LINES = ["line-01", "line-02"]
EQUIPMENT = [
    {"id": "printer-001", "type": "3d_printer", "asset": "bambu-p2s-001"},
    {"id": "printer-002", "type": "3d_printer", "asset": "bambu-p2s-002"},
    {"id": "cnc-001", "type": "cnc_machine", "asset": "haas-vf2-001"},
]
SENSORS = ["camera-001", "camera-002", "dht22-001", "adxl345-001"]
ANOMALY_TYPES = ["stringing", "layer_shift", "delamination", "warping", "spaghetti"]
SEVERITIES = ["low", "medium", "high", "critical"]
VERDICTS = ["normal", "normal", "normal", "normal", "anomaly_detected"]  # 20% anomaly rate


def generate_payload_arrival() -> dict:
    """Generate a synthetic payload_arrival event (camera capture)."""
    equip = random.choice(EQUIPMENT)
    ts = datetime.now(timezone.utc)
    filename = f"{ts.strftime('%Y%m%dT%H%M%SZ')}_{equip['id']}.jpg"
    size = random.randint(150000, 400000)

    return build_event(
        event_type="payload_arrival",
        event_category="quality_inspection",
        source_id=f"rpi5-{random.randint(1,3):03d}",
        asset_type=equip["type"],
        asset_id=equip["asset"],
        equipment_id=equip["id"],
        sensor_id=random.choice(["camera-001", "camera-002"]),
        payload_uri=f"nfs://svm-iot/vol_images/{ts.strftime('%Y/%m/%d')}/{filename}",
        payload_type="image",
        content_type="image/jpeg",
        payload_bytes=os.urandom(size),  # Random bytes for checksum
        processing_status="pending_analysis",
        metadata={
            "capture_trigger": "scheduled",
            "capture_interval_seconds": 60,
            "camera_model": "brio-4k",
            "resolution": "1920x1080",
            "jpeg_quality": 80,
            "print_job_id": f"job-{ts.strftime('%Y%m%d')}-{random.randint(1,10):03d}",
            "print_layer_current": random.randint(1, 200),
            "print_layer_total": 200,
        },
    )


def generate_quality_event(source_event_id: str = None) -> dict:
    """Generate a synthetic quality_event (AI analysis result)."""
    equip = random.choice(EQUIPMENT)
    verdict = random.choice(VERDICTS)
    confidence = random.uniform(0.7, 0.99) if verdict == "anomaly_detected" else random.uniform(0.85, 0.99)

    anomalies = []
    if verdict == "anomaly_detected":
        num_anomalies = random.randint(1, 3)
        for _ in range(num_anomalies):
            anomalies.append({
                "type": random.choice(ANOMALY_TYPES),
                "severity": random.choice(SEVERITIES),
                "location": random.choice(["upper-left", "center", "lower-right", "full-frame"]),
            })

    return build_event(
        event_type="quality_event",
        event_category="quality_inspection",
        source_id="lambda-analyzer",
        asset_type=equip["type"],
        asset_id=equip["asset"],
        equipment_id=equip["id"],
        sensor_id="camera-001",
        processing_status="completed",
        metadata={
            "source_event_id": source_event_id or str(uuid.uuid4()),
            "analyzer_service": "bedrock",
            "analyzer_model": "anthropic.claude-sonnet-4-5-20250929-v1:0",
            "analysis_latency_ms": random.randint(2000, 5000),
            "verdict": verdict,
            "confidence": round(confidence, 3),
            "anomalies": anomalies,
            "max_severity": max((a["severity"] for a in anomalies), default="none",
                               key=lambda s: ["none", "low", "medium", "high", "critical"].index(s)),
            "recommended_action": "monitor" if verdict == "normal" else "inspect",
        },
    )


def generate_sensor_event() -> dict:
    """Generate a synthetic sensor_event (temperature/humidity)."""
    return build_event(
        event_type="sensor_event",
        event_category="environmental_monitoring",
        source_id=f"rpi5-{random.randint(1,3):03d}",
        asset_type="sensor_array",
        asset_id="env-sensor-rack-01",
        equipment_id=random.choice([e["id"] for e in EQUIPMENT]),
        sensor_id="dht22-001",
        processing_status="completed",
        metadata={
            "sensor_type": "temperature_humidity",
            "readings": {
                "temperature_celsius": round(random.uniform(20.0, 35.0), 1),
                "humidity_percent": round(random.uniform(30.0, 70.0), 1),
            },
            "aggregation_method": "mean",
            "aggregation_window_seconds": 60,
            "sample_count": 100,
        },
    )


def generate_telemetry_event() -> dict:
    """Generate a synthetic telemetry_event (ONTAP metrics)."""
    return build_event(
        event_type="telemetry_event",
        event_category="storage_health",
        source_id="rpi5-001",
        asset_type="storage_system",
        asset_id="edge-cluster-01",
        equipment_id="node-01",
        sensor_id="rest-api",
        processing_status="completed",
        metadata={
            "ontap_version": "9.15.1",
            "metrics_type": "volume_performance",
            "collection_interval_seconds": 60,
            "volumes": [
                {
                    "name": "vol_images",
                    "svm": "svm-iot",
                    "iops_total": random.randint(50, 500),
                    "throughput_read_mbps": round(random.uniform(1.0, 50.0), 1),
                    "throughput_write_mbps": round(random.uniform(0.5, 20.0), 1),
                    "latency_read_us": random.randint(200, 2000),
                    "latency_write_us": random.randint(500, 3000),
                    "capacity_used_percent": round(random.uniform(10.0, 80.0), 1),
                }
            ],
            "node_cpu_percent": round(random.uniform(10.0, 60.0), 1),
            "node_memory_percent": round(random.uniform(40.0, 80.0), 1),
        },
    )


def generate_anomaly_event(trigger_event_id: str = None) -> dict:
    """Generate a synthetic anomaly_event."""
    equip = random.choice(EQUIPMENT)
    return build_event(
        event_type="anomaly_event",
        event_category="equipment_telemetry",
        source_id="clickhouse-detector",
        asset_type=equip["type"],
        asset_id=equip["asset"],
        equipment_id=equip["id"],
        sensor_id="camera-001",
        processing_status="completed",
        metadata={
            "trigger_event_id": trigger_event_id or str(uuid.uuid4()),
            "anomaly_type": random.choice(ANOMALY_TYPES),
            "severity": random.choice(["high", "critical"]),
            "threshold_breached": "confidence > 0.8 AND severity IN ('high', 'critical')",
            "action_taken": "alert_sent",
            "alert_channel": "sns",
        },
    )


GENERATORS = {
    "payload_arrival": generate_payload_arrival,
    "quality_event": generate_quality_event,
    "sensor_event": generate_sensor_event,
    "telemetry_event": generate_telemetry_event,
    "anomaly_event": generate_anomaly_event,
}


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic v3 events for testing")
    parser.add_argument("--count", type=int, default=10, help="Number of events to generate")
    parser.add_argument("--interval", type=float, default=0.0, help="Seconds between events (0 = burst)")
    parser.add_argument("--types", default="all", help="Event types (comma-separated or 'all')")
    parser.add_argument("--stdout", action="store_true", help="Print to stdout instead of Kafka")
    args = parser.parse_args()

    if args.types == "all":
        event_types = list(GENERATORS.keys())
    else:
        event_types = args.types.split(",")

    publisher = None if args.stdout else EventPublisher()

    for i in range(args.count):
        event_type = random.choice(event_types)
        event = GENERATORS[event_type]()

        if args.stdout:
            print(json.dumps(event, ensure_ascii=False))
        else:
            ok = publisher.publish(event)
            status = "kafka" if ok else "buffered"
            print(f"[{i+1}/{args.count}] {event_type} → {status} (event_id: {event['event_id'][:8]}...)")

        if args.interval > 0:
            time.sleep(args.interval)

    if publisher:
        remaining = publisher.flush()
        print(f"\nDone. {args.count} events generated. Remaining in queue: {remaining}")


if __name__ == "__main__":
    main()
