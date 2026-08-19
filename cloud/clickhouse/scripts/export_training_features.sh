#!/usr/bin/env bash
# Export training features from ClickHouse to ONTAP S3 as Parquet
# Run daily via cron: 0 2 * * * /opt/edge-to-cloud/export_training_features.sh
#
# Prerequisites:
#   - clickhouse-client installed and configured
#   - ONTAP S3 credentials in environment (see below)
#
# Usage:
#   ./export_training_features.sh              # Export yesterday's data
#   ./export_training_features.sh 2026-06-14   # Export specific date
#
# Two things about how the query is built are load-bearing:
#
#   1. $1 reaches both the SQL text and the S3 object path. Before validation,
#      `./export_training_features.sh "2026-01-01' OR 1=1 --"` was a working
#      injection into ClickHouse. It is now checked against a date regex and
#      confirmed to be a real calendar date before it is used anywhere, and the
#      WHERE clause additionally binds it as a typed parameter.
#   2. The query is fed on stdin, not via --query. Arguments to clickhouse-client
#      are visible to any local user in `ps`, and this query embeds the ONTAP S3
#      secret key. ClickHouse has no way to pass s3() credentials out of band,
#      so keeping them off argv is the available mitigation.
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

# --- Validate the one caller-supplied value before it reaches SQL or a path ---
if [[ ! "$EXPORT_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "ERROR: export date must be YYYY-MM-DD, got: ${EXPORT_DATE}" >&2
  exit 2
fi
# The regex accepts 2026-13-45. Reject it by asking the OS to parse the date.
if ! date -u -d "$EXPORT_DATE" +%Y-%m-%d >/dev/null 2>&1 \
   && ! date -u -j -f %Y-%m-%d "$EXPORT_DATE" +%Y-%m-%d >/dev/null 2>&1; then
  echo "ERROR: not a valid calendar date: ${EXPORT_DATE}" >&2
  exit 2
fi

# ONTAP S3 bucket names are DNS-label shaped; reject anything that could add
# path segments or escape the intended prefix.
if [[ ! "$ONTAP_S3_BUCKET" =~ ^[a-z0-9][a-z0-9.-]{1,62}$ ]]; then
  echo "ERROR: ONTAP_S3_BUCKET must be a DNS-label-shaped name, got: ${ONTAP_S3_BUCKET}" >&2
  exit 2
fi

EXPORT_PATH="training_features/${EXPORT_DATE}.parquet"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting export for date: ${EXPORT_DATE}"
echo "  Target: ${ONTAP_S3_ENDPOINT}/${ONTAP_S3_BUCKET}/${EXPORT_PATH}"

# Execute export. Query on stdin so the secret key stays out of argv.
clickhouse-client \
  --host "${CLICKHOUSE_HOST}" \
  --port "${CLICKHOUSE_PORT}" \
  --database "${CLICKHOUSE_DB}" \
  --param_export_date="${EXPORT_DATE}" <<SQL
    INSERT INTO FUNCTION s3(
      '${ONTAP_S3_ENDPOINT}/${ONTAP_S3_BUCKET}/${EXPORT_PATH}',
      '${ONTAP_S3_ACCESS_KEY}',
      '${ONTAP_S3_SECRET_KEY}',
      'Parquet'
    )
    SELECT *
    FROM training_features_export
    WHERE toDate(export_timestamp) = {export_date:Date}
SQL

ROWS=$(clickhouse-client \
  --host "${CLICKHOUSE_HOST}" \
  --port "${CLICKHOUSE_PORT}" \
  --database "${CLICKHOUSE_DB}" \
  --param_export_date="${EXPORT_DATE}" <<SQL
    SELECT count()
    FROM training_features_export
    WHERE toDate(export_timestamp) = {export_date:Date}
SQL
)

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Export complete: ${ROWS} rows → ${EXPORT_PATH}"
