#!/usr/bin/env bash
# Apply ClickHouse DDL to the local demo environment.
# Run after `docker compose up -d` and services are healthy.

set -euo pipefail

CH="docker exec -i demo-clickhouse clickhouse-client"
DDL_DIR="$(dirname "$0")/../cloud/clickhouse/ddl"

echo "Waiting for ClickHouse to be ready..."
for i in {1..30}; do
  if docker exec demo-clickhouse clickhouse-client --query "SELECT 1" >/dev/null 2>&1; then
    echo "ClickHouse is ready."
    break
  fi
  sleep 2
done

echo "Applying DDL (excluding Kafka source table, applied separately)..."
# Apply base tables and MVs first (skip 002 Kafka engine until topic exists)
for f in 001 003 004 005 006 007 008 010; do
  ddl_file=$(ls "${DDL_DIR}/${f}_"*.sql 2>/dev/null | head -1)
  if [ -n "${ddl_file}" ]; then
    echo "  Applying $(basename "${ddl_file}")"
    ${CH} --multiquery < "${ddl_file}"
  fi
done

echo ""
echo "Base tables created. To connect Kafka source:"
echo "  1. Edit ${DDL_DIR}/002_kafka_source_table.sql"
echo "     Replace <KAFKA_BROKER> with: kafka (inside compose network) or localhost:9092 (host)"
echo "  2. docker exec -i demo-clickhouse clickhouse-client --multiquery < <edited-002>"
echo ""
echo "Or for host-based testing, generate events directly:"
echo "  KAFKA_ENABLED=true KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \\"
echo "    python3 ../tests/synthetic_events.py --count 100 --interval 0.5"
echo ""
echo "Grafana: http://localhost:3000 (admin/admin)"
echo "ClickHouse: http://localhost:8123"
