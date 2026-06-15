# Sample Events (v3 Schema)

Pre-generated synthetic events for cross-project testing.

## Usage

These JSONL files can be used to:
1. Validate ClickHouse DDL (insert and query)
2. Test Databricks DLT pipelines (Bronze ingestion)
3. Verify Kafka → ClickHouse Materialized Views
4. Develop dashboards without live data

## Files

| File | Event Type | Count | Description |
|------|-----------|-------|-------------|
| `payload_arrival_samples.jsonl` | payload_arrival | 5 | Camera capture → ONTAP NFS |
| `quality_event_samples.jsonl` | quality_event | 5 | AI analysis results |
| `sensor_event_samples.jsonl` | sensor_event | 5 | Temperature/humidity readings |
| `telemetry_event_samples.jsonl` | telemetry_event | 3 | ONTAP performance metrics |
| `anomaly_event_samples.jsonl` | anomaly_event | 3 | Anomaly detections |

## Regeneration

```bash
# Regenerate with fresh UUIDs and timestamps
python3 tests/synthetic_events.py --count 5 --types payload_arrival --stdout > tests/sample_events/payload_arrival_samples.jsonl
python3 tests/synthetic_events.py --count 5 --types quality_event --stdout > tests/sample_events/quality_event_samples.jsonl
python3 tests/synthetic_events.py --count 5 --types sensor_event --stdout > tests/sample_events/sensor_event_samples.jsonl
python3 tests/synthetic_events.py --count 3 --types telemetry_event --stdout > tests/sample_events/telemetry_event_samples.jsonl
python3 tests/synthetic_events.py --count 3 --types anomaly_event --stdout > tests/sample_events/anomaly_event_samples.jsonl
```

## Cross-Project Sync

These samples are shared with [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) for E2E testing.
Sync method: TBD (git subtree / CI artifact / manual copy).
