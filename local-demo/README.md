# Local Demo Environment

Run the full event pipeline (Kafka + ClickHouse + Grafana) locally — no physical
hardware or managed services required. Useful for development, dashboard work,
and demos before the Kafka/ClickHouse and ONTAP environment is ready.

## Prerequisites

- Docker + Docker Compose
- Python 3.12 (for event generation)

## Quick Start

```bash
# 1. Start services
cd local-demo
docker compose up -d

# 2. Wait ~30s, then apply ClickHouse DDL
./setup.sh

# 3a. Fast path — load events directly into ClickHouse (no Kafka needed)
pip install clickhouse-connect
python3 load_events_direct.py --count 200

# 3b. OR full path — through Kafka
#    Edit ../cloud/clickhouse/ddl/002_kafka_source_table.sql:
#      <KAFKA_BROKER> -> localhost:9092
#    Apply it, then:
KAFKA_ENABLED=true KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  python3 ../tests/synthetic_events.py --count 100 --interval 0.5

# 4. Open Grafana
open http://localhost:3000   # admin/admin, dashboard auto-provisioned
```

## Tear Down

```bash
docker compose down -v   # -v removes volumes (clean slate)
```

## Services

| Service | Port | URL |
|---------|------|-----|
| Kafka | 9092 | localhost:9092 |
| ClickHouse | 8123 (HTTP), 9000 (native) | http://localhost:8123 |
| Grafana | 3000 | http://localhost:3000 |

## What Gets Provisioned

- **ClickHouse datasource** (uid: clickhouse-demo) — auto-configured in Grafana
- **Quality Monitoring dashboard** — 8 panels, auto-loaded into "Edge Demo" folder

## Two Demo Paths

| Path | Command | When to use |
|------|---------|-------------|
| Direct insert | `load_events_direct.py` | Fast dashboard demo (skips Kafka) |
| Through Kafka | `synthetic_events.py` + Kafka source table | Full pipeline validation |

Both trigger all Materialized Views (quality_events, payload_manifest,
anomaly_events, feedback_events).

## Notes

- All demo data has `is_synthetic = true` (governance: distinguishes from real data)
- This is a local dev/demo setup. Not for production. Single-node, no auth, no TLS.
- For production-like managed Kafka/ClickHouse, see `docs/*/kafka-integration.md`.
