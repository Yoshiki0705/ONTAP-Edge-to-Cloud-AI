#!/bin/bash
# ONTAP S3 Setup for ClickHouse Backup
#
# Configures ONTAP S3 object storage as a backup target for ClickHouse.
# Run these commands on ONTAP CLI. Replace <...> placeholders before executing.
#
# Prerequisites:
#   - ONTAP 9.8+ (S3 protocol support)
#   - Aggregate with available space
#   - Data LIF for S3 (or reuse existing)

set -euo pipefail

cat << 'ONTAP_COMMANDS'
# ============================================================
# 1. Create a dedicated SVM for S3 (or reuse existing)
# ============================================================

vserver create -vserver svm-s3 -subtype default -rootvolume svm_s3_root \
  -aggregate aggr1 -rootvolume-security-style unix

# ============================================================
# 2. Create a data LIF for S3 access
# ============================================================

network interface create -vserver svm-s3 \
  -lif s3-data-lif \
  -service-policy default-data-files \
  -home-node <NODE_NAME> -home-port <PORT> \
  -address <S3_LIF_IP> -netmask <NETMASK>

# ============================================================
# 3. Enable the S3 object store server
#    (TLS certificate auto-generated; use CA-signed in production)
# ============================================================

vserver object-store-server create -vserver svm-s3 \
  -object-store-server s3-backup \
  -is-http-enabled false \
  -is-https-enabled true \
  -secure-listener-port 443

# ============================================================
# 4. Create a bucket for ClickHouse backups
# ============================================================

vserver object-store-server bucket create -vserver svm-s3 \
  -bucket clickhouse-backup \
  -type nas \
  -size 500GB

# Also create a bucket for ClickHouse Parquet exports (Databricks pickup)
vserver object-store-server bucket create -vserver svm-s3 \
  -bucket clickhouse-export \
  -type nas \
  -size 200GB

# ============================================================
# 5. Create an S3 user and capture access keys
#    (SAVE the secret key output — it is shown only once)
# ============================================================

vserver object-store-server user create -vserver svm-s3 \
  -user clickhouse-backup-user

# ============================================================
# 6. Grant the user access via bucket policy
# ============================================================

vserver object-store-server bucket policy statement create -vserver svm-s3 \
  -bucket clickhouse-backup \
  -effect allow \
  -action GetObject,PutObject,DeleteObject,ListBucket \
  -principal clickhouse-backup-user \
  -resource clickhouse-backup,clickhouse-backup/*

vserver object-store-server bucket policy statement create -vserver svm-s3 \
  -bucket clickhouse-export \
  -effect allow \
  -action GetObject,PutObject,DeleteObject,ListBucket \
  -principal clickhouse-backup-user \
  -resource clickhouse-export,clickhouse-export/*

# ============================================================
# 7. Verify
# ============================================================

vserver object-store-server show -vserver svm-s3
vserver object-store-server bucket show -vserver svm-s3
vserver object-store-server user show -vserver svm-s3

ONTAP_COMMANDS

echo ""
echo "Run the commands above on ONTAP CLI. Replace placeholders:"
echo "  <NODE_NAME>, <PORT>, <S3_LIF_IP>, <NETMASK>"
echo ""
echo "IMPORTANT: Save the access key + secret key from step 5 (shown once)."
echo ""
echo "Configure ClickHouse export with these credentials:"
echo "  export ONTAP_S3_ENDPOINT=https://<S3_LIF_IP>:443"
echo "  export ONTAP_S3_ACCESS_KEY=<access_key>"
echo "  export ONTAP_S3_SECRET_KEY=<secret_key>"
echo "  ./cloud/clickhouse/scripts/export_training_features.sh"
