#!/bin/bash
# ONTAP Telemetry Service Account Setup
#
# Creates a least-privilege read-only service account for the ONTAP telemetry
# collector (edge/raspberry-pi/sensors/ontap_telemetry.py).
# Run these commands on ONTAP CLI. Replace <...> placeholders before executing.
#
# Prerequisites:
#   - ONTAP 9.6+ (REST API)
#   - SVM created (svm-iot)

set -euo pipefail

cat << 'ONTAP_COMMANDS'
# ============================================================
# 1. Create a custom read-only role (least privilege)
#    Only allows reading metrics, volumes, and nodes
# ============================================================

security login role create -vserver svm-iot \
  -role iot-readonly \
  -cmddirname "volume show" \
  -access readonly

security login role create -vserver svm-iot \
  -role iot-readonly \
  -cmddirname "storage aggregate show" \
  -access readonly

security login role create -vserver svm-iot \
  -role iot-readonly \
  -cmddirname "system node show" \
  -access readonly

# ============================================================
# 2. Create the service account (HTTP/REST API access)
# ============================================================

security login create -vserver svm-iot \
  -user-or-group-name svc-iot-telemetry \
  -application http \
  -authentication-method password \
  -role iot-readonly

# ============================================================
# 3. Restrict access source to the Pi's IP (firewall policy)
#    Optional but recommended
# ============================================================

# Example: limit management access to the telemetry collector subnet
# system services firewall policy create -vserver svm-iot \
#   -policy iot-mgmt -service https -allow-list <PI_SUBNET>/24

# ============================================================
# 4. Verify
# ============================================================

security login show -vserver svm-iot -user-or-group-name svc-iot-telemetry
security login role show -vserver svm-iot -role iot-readonly

ONTAP_COMMANDS

echo ""
echo "Run the commands above on ONTAP CLI."
echo ""
echo "Configure the telemetry collector (edge/raspberry-pi/sensors/.env):"
echo "  ONTAP_API_HOST=<ONTAP_MGMT_LIF>"
echo "  ONTAP_API_USER=svc-iot-telemetry"
echo "  ONTAP_API_PASSWORD=<password set during creation>"
echo ""
echo "Test from the Pi:"
echo "  curl -k -u svc-iot-telemetry https://<ONTAP_MGMT_LIF>/api/storage/volumes?fields=space"
