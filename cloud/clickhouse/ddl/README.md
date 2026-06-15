# ClickHouse DDL

Table definitions for the real-time analytics layer.

## Execution Order

```bash
# Execute DDL files in numbered order:
clickhouse-client --multiquery < 001_kafka_events_raw.sql
clickhouse-client --multiquery < 003_quality_events.sql
clickhouse-client --multiquery < 004_payload_manifest.sql
clickhouse-client --multiquery < 005_sensor_rollup.sql
clickhouse-client --multiquery < 006_anomaly_events.sql
clickhouse-client --multiquery < 007_dead_letter.sql
clickhouse-client --multiquery < 008_training_features_export.sql

# After Kafka broker is configured:
# Edit 002_kafka_source_table.sql to replace <KAFKA_BROKER>
clickhouse-client --multiquery < 002_kafka_source_table.sql
```

## Table Overview

| # | Table | Engine | TTL | Purpose |
|---|-------|--------|-----|---------|
| 1 | `kafka_events_raw` | MergeTree | 30d | All events from Kafka |
| 2 | `kafka_events_queue` | Kafka Engine | — | Kafka consumer (source) |
| 3 | `quality_events` | ReplacingMergeTree | 365d | AI analysis results |
| 4 | `payload_manifest` | MergeTree | 365d | ONTAP file ↔ event bridge |
| 5 | `sensor_events_rollup_1m` | AggregatingMergeTree | 90d | 1-min sensor aggregation |
| 6 | `anomaly_events` | MergeTree | 365d | Anomaly detections |
| 7 | `dead_letter_events` | MergeTree | 30d | Failed/invalid events |
| 8 | `training_features_export` | MergeTree | — | Databricks export |

## Materialized Views

| MV | Source | Target | Logic |
|----|--------|--------|-------|
| `mv_kafka_to_raw` | kafka_events_queue | kafka_events_raw | Type conversion (String → DateTime64) |
| `mv_raw_to_quality` | kafka_events_raw | quality_events | Filter event_type = 'quality_event', extract JSON |
| `mv_raw_to_manifest` | kafka_events_raw | payload_manifest | Filter event_type = 'payload_arrival' |
| `mv_raw_to_sensor_rollup` | kafka_events_raw | sensor_events_rollup_1m | 1-min GROUP BY |
| `mv_raw_to_anomaly` | kafka_events_raw | anomaly_events | Filter event_type = 'anomaly_event' |
