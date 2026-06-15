#!/usr/bin/env bash
# Export training features from ClickHouse to ONTAP S3 as Parquet
# Run daily via cron: 0 2 * * * /opt/edge-to-cloud/export_training_features.sh
#
# Prerequisites:
#   - clickhouse-client installed and configured
#   - ONTAP S3 credentials in environment or this script
#
# Usage:
#   ./export_training_features.sh              # Export yesterday's data
#   ./export_training_features.sh 2026-06-14   # Export specific date

set -euo pipefail

# Configuration (override via environment)
CLICKHOUSE_HOST="${CLICKHOUSE_HOST:-localhost}"
CLICKHOUSE_PORT="${CLICKHOUSE_PORT:-9000}"
CLICKHOUSE_DB="${CLICKHOUSE_DB:-default}"
ONTAP_S3_ENDPOINT="${ONTAP_S3_ENDPOINT:-https://<ONTAP_S3_LIF>:443}"
ONTAP_S3_BUCKET="${ONTAP_S3_BUCKET:-clickhouse-export}"
ONTAP_S3_ACCESS_KEY="${ONTAP_S3_ACCESS_KEY:?Error: ONTAP_S3_ACCESS_KEY not set}"
ONTAP_S3_SECRET_KEY="${ONTAP_S3_SECRET_KEY:?Error: ONTAP_S3_SECRET_KEY not set}"

# Date to export (default: yesterday)
EXPORT_DATE="${1:-$(date -u -d 'yesterday' +%Y-%m-%d 2>/dev/null || date -u -v-1d +%Y-%m-%d)}"
EXPORT_PATH="training_features/${EXPORT_DATE}.parquet"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting export for date: ${EXPORT_DATE}"
echo "  Target: ${ONTAP_S3_ENDPOINT}/${ONTAP_S3_BUCKET}/${EXPORT_PATH}"

# Execute export
clickhouse-client \
  --host "${CLICKHOUSE_HOST}" \
  --port "${CLICKHOUSE_PORT}" \
  --database "${CLICKHOUSE_DB}" \
  --query "
    INSERT INTO FUNCTION s3(
      '${ONTAP_S3_ENDPOINT}/${ONTAP_S3_BUCKET}/${EXPORT_PATH}',
      '${ONTAP_S3_ACCESS_KEY}',
      '${ONTAP_S3_SECRET_KEY}',
      'Parquet'
    )
    SELECT *
    FROM training_features_export
    WHERE toDate(export_timestamp) = '${EXPORT_DATE}'
  "

ROWS=$(clickhouse-client \
  --host "${CLICKHOUSE_HOST}" \
  --port "${CLICKHOUSE_PORT}" \
  --database "${CLICKHOUSE_DB}" \
  --query "
    SELECT count()
    FROM training_features_export
    WHERE toDate(export_timestamp) = '${EXPORT_DATE}'
  ")

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Export complete: ${ROWS} rows → ${EXPORT_PATH}"
