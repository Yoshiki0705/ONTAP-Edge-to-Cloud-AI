#!/bin/bash
# ONTAP Setup for 3D Print Quality Monitoring
#
# Run these commands on ONTAP CLI (SSH or System Manager CLI)
# Replace variables marked with <...> before executing
#
# Prerequisites:
#   - ONTAP 9.13.1+
#   - SVM created (svm-iot)
#   - Aggregate with available space

set -euo pipefail

cat << 'ONTAP_COMMANDS'
# ============================================================
# 1. Create NFS volumes for images and results
# ============================================================

vol create -vserver svm-iot -volume vol_images \
  -aggregate aggr1 -size 100GB \
  -junction-path /vol_images \
  -security-style unix

vol create -vserver svm-iot -volume vol_results \
  -aggregate aggr1 -size 10GB \
  -junction-path /vol_results \
  -security-style unix

# ============================================================
# 2. Configure export policy (allow Pi access)
# ============================================================

# Create policy
export-policy create -vserver svm-iot -policyname iot-devices

# Add rule for Pi IP (replace <PI_IP>)
export-policy rule create -vserver svm-iot \
  -policyname iot-devices \
  -clientmatch <PI_IP> \
  -rorule sys -rwrule sys -superuser sys \
  -protocol nfs

# Apply to volumes
vol modify -vserver svm-iot -volume vol_images -policy iot-devices
vol modify -vserver svm-iot -volume vol_results -policy iot-devices

# ============================================================
# 3. (Optional) FPolicy configuration for Phase 2
#    Triggers external notification on file create
# ============================================================

# Create FPolicy event (monitor JPEG file creation)
fpolicy policy event create -vserver svm-iot \
  -event-name img-create \
  -protocol nfs \
  -file-operations create \
  -filters first-write

# Create FPolicy external engine (Pi as FPolicy server)
# fpolicy policy external-engine create -vserver svm-iot \
#   -engine-name pi-engine \
#   -primary-servers <PI_IP> \
#   -port 9999 \
#   -extern-engine-type asynchronous \
#   -ssl-option no-auth

# Create FPolicy policy
# fpolicy policy create -vserver svm-iot \
#   -policy-name print-monitor \
#   -events img-create \
#   -engine pi-engine \
#   -is-mandatory false

# Enable FPolicy
# fpolicy enable -vserver svm-iot -policy-name print-monitor

# ============================================================
# 4. Verify setup
# ============================================================

vol show -vserver svm-iot -fields junction-path,size,used
export-policy rule show -vserver svm-iot -policyname iot-devices

ONTAP_COMMANDS

echo ""
echo "Copy the commands above and run on ONTAP CLI."
echo "Replace <PI_IP> with your Raspberry Pi's IP address."
echo ""
echo "After ONTAP setup, mount on Pi:"
echo "  sudo mount -t nfs <ONTAP_DATA_LIF_IP>:/vol_images /mnt/ontap/images"
echo "  sudo mount -t nfs <ONTAP_DATA_LIF_IP>:/vol_results /mnt/ontap/results"
