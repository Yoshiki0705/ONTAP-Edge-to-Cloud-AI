#!/bin/bash
# ONTAP Setup for Telemetry Analytics
#
# Run these commands on ONTAP CLI (SSH or System Manager CLI)
# Replace variables marked with <...> before executing
#
# Prerequisites:
#   - ONTAP 9.13.1+
#   - SVM created (svm-iot)
#   - REST API enabled (default on 9.13.1+)

set -euo pipefail

cat << 'ONTAP_COMMANDS'
# ============================================================
# 1. Create NFS volume for telemetry data
# ============================================================

vol create -vserver svm-iot -volume vol_telemetry \
  -aggregate aggr1 -size 50GB \
  -junction-path /vol_telemetry \
  -security-style unix

# ============================================================
# 2. Create read-only service account for REST API
# ============================================================

# Create custom role (read-only access to metrics)
security login role create -vserver svm-iot \
  -role iot-readonly \
  -cmddirname "volume show" \
  -access readonly

security login role create -vserver svm-iot \
  -role iot-readonly \
  -cmddirname "statistics" \
  -access readonly

# Create service account
security login create -vserver svm-iot \
  -user-or-group-name svc-iot-telemetry \
  -application http \
  -authentication-method password \
  -role iot-readonly

# ============================================================
# 3. Configure export policy
# ============================================================

export-policy rule create -vserver svm-iot \
  -policyname iot-devices \
  -clientmatch <PI_IP> \
  -rorule sys -rwrule sys -superuser sys \
  -protocol nfs

vol modify -vserver svm-iot -volume vol_telemetry -policy iot-devices

# ============================================================
# 4. (Optional) SnapMirror to FSx for ONTAP
#    For cloud analytics via S3 Access Points
# ============================================================

# On FSx for ONTAP side:
# vol create -vserver svm-fsxn -volume vol_telemetry_dp \
#   -aggregate aggr1 -size 50GB -type DP

# Create SnapMirror relationship:
# snapmirror create -source-path svm-iot:vol_telemetry \
#   -destination-path svm-fsxn:vol_telemetry_dp \
#   -type XDP -policy MirrorAllSnapshots

# Initialize:
# snapmirror initialize -destination-path svm-fsxn:vol_telemetry_dp

# Schedule (hourly sync):
# snapmirror modify -destination-path svm-fsxn:vol_telemetry_dp \
#   -schedule hourly

# ============================================================
# 5. Verify setup
# ============================================================

vol show -vserver svm-iot -volume vol_telemetry
security login show -vserver svm-iot -user-or-group-name svc-iot-telemetry

# Test REST API access:
# curl -k -u svc-iot-telemetry https://<ONTAP_DATA_LIF_IP>/api/cluster

ONTAP_COMMANDS

echo ""
echo "Copy the commands above and run on ONTAP CLI."
echo "Replace <PI_IP> with your Raspberry Pi's IP address."
echo ""
echo "After ONTAP setup, mount on Pi:"
echo "  sudo mount -t nfs <ONTAP_DATA_LIF_IP>:/vol_telemetry /mnt/ontap/telemetry"
echo ""
echo "Test REST API:"
echo "  curl -k -u svc-iot-telemetry https://<ONTAP_DATA_LIF_IP>/api/cluster"
