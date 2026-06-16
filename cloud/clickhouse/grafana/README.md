# Grafana Dashboards

Dashboard definitions for visualizing the ClickHouse real-time analytics layer.

## Prerequisites

- Grafana 10+ with the [ClickHouse datasource plugin](https://grafana.com/grafana/plugins/grafana-clickhouse-datasource/)
- ClickHouse with DDL applied (see `../ddl/`)

## Import

1. Grafana UI → Dashboards → Import
2. Upload `dashboard_quality_monitoring.json`
3. Select your ClickHouse datasource for the `${DS_CLICKHOUSE}` variable

## Dashboard: Edge Quality Monitoring

| Panel | Type | Purpose |
|-------|------|---------|
| Anomaly Rate (1h) | Stat | Quick health (green <15%, red >30%) |
| Total Inspections (1h) | Stat | Throughput |
| Ingest Lag p95 | Stat | Pipeline freshness (red >500ms) |
| Dead Letter Count | Stat | Data quality (red >1) |
| Quality Trend (hourly) | Timeseries | Anomaly vs normal over 24h |
| AI Analysis Latency | Timeseries | Bedrock p50/p95 response time |
| Recent Anomalies | Table | Anomalies + payload_uri (ONTAP reference) |
| Sensor Environment | Timeseries | Temperature / humidity trend |

## Variables

- `equipment_id`: Multi-select filter for equipment (auto-populated from data)

## Demo Use

This dashboard backs **Demo 1** (30-second anomaly detection) and **Demo 3**
(payload reference). See `docs/*/demo-scenarios.md`.

For demo data isolation, filter or run edge with `SITE_ID=demo`.
