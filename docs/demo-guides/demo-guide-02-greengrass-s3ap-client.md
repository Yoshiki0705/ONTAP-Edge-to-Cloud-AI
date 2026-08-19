> 🌐 Language: **English**

# Demo Guide 02: Greengrass S3 AP Client Component

> **Goal**: Deploy the custom Greengrass S3 AP client component on a Raspberry Pi (or EC2 simulator), verify PutObject directly to FSx for ONTAP S3 AP with offline buffer and retry.

> **Time**: ~60 minutes
> **Cost**: Greengrass is free on device. FSx for ONTAP cost is separate.

> **Prerequisites**: Complete [Demo Guide 00](./demo-guide-00-prerequisites.md) and [Demo Guide 01](./demo-guide-01-iot-core-lambda-s3ap.md) (confirms S3 AP is working).

---

## Architecture

```
[Raspberry Pi 5 / EC2]                          [AWS Cloud]
┌────────────────────────────────────┐          ┌──────────────────────────────┐
│ IoT Greengrass V2 Core             │          │ FSx for ONTAP                │
│ ┌────────────────────────────────┐ │  HTTPS   │ Volume: /iot-data            │
│ │ com.edge-to-cloud.S3APClient   │ │─────────>│   S3 AP: iot-ingest-ap       │
│ │  - Watch /incoming/ dir        │ │ PutObject│                              │
│ │  - Buffer in SQLite            │ │          │   Same data visible via:     │
│ │  - Flush to S3 AP with retry   │ │          │     NFS: /mnt/fsxn/iot-data/ │
│ │  - Dead letter on max retry    │ │          │     S3:  s3://{AP_ARN}/...   │
│ └────────────────────────────────┘ │          └──────────────────────────────┘
│                                    │
│ ┌────────────────────────────────┐ │
│ │ Sensor/Camera Data Producer    │ │
│ │  (simulated or real)           │ │
│ │  → writes files to /incoming/  │ │
│ └────────────────────────────────┘ │
└────────────────────────────────────┘
```

---

## Step 1: Set Up Greengrass Core Device

### Option A: Raspberry Pi 5 (real device)

```bash
# On Raspberry Pi (Raspberry Pi OS, 64-bit)
# Install Java (required by Greengrass nucleus)
sudo apt-get update && sudo apt-get install -y default-jdk python3-pip

# Install Greengrass V2
curl -s https://d2s8p88vqu9w66.cloudfront.net/releases/greengrass-nucleus-latest.zip > greengrass-nucleus-latest.zip
unzip greengrass-nucleus-latest.zip -d GreengrassInstaller

sudo java -Droot="/greengrass/v2" -Dlog.store=FILE \
  -jar ./GreengrassInstaller/lib/Greengrass.jar \
  --aws-region "$AWS_REGION" \
  --thing-name "GreengrassCore-${DEVICE_ID}" \
  --thing-group-name "EdgeToCloudGroup" \
  --component-default-user ggc_user:ggc_group \
  --provision true \
  --setup-system-service true

# Verify Greengrass is running
sudo systemctl status greengrass.service
```

### Option B: EC2 Instance (cloud simulation)

```bash
# Launch Amazon Linux 2023 instance in same VPC as FSx for ONTAP
# (t3.small is sufficient)

# Install Greengrass (same steps as above)
# This simulates the edge device for development/testing
```

### Verify Greengrass Core is connected

```bash
aws greengrassv2 list-core-devices \
  --status HEALTHY \
  --region "$AWS_REGION" | jq '.coreDevices[] | {coreDeviceThingName, status, lastStatusUpdateTimestamp}'
```

---

## Step 2: Package and Upload Component Artifact

```bash
# On your development machine
cd /path/to/edge-to-cloud-ai

# Create artifact ZIP
cd edge/greengrass
zip -r /tmp/s3ap_client.zip s3ap_client/
cd ../..

# Upload to S3 (component artifact bucket)
ARTIFACT_BUCKET="edge-to-cloud-artifacts-${ACCOUNT_ID}-${AWS_REGION}"
aws s3 mb "s3://${ARTIFACT_BUCKET}" --region "$AWS_REGION" 2>/dev/null || true

aws s3 cp /tmp/s3ap_client.zip \
  "s3://${ARTIFACT_BUCKET}/com.edge-to-cloud.S3APClient/1.0.0/s3ap_client.zip" \
  --region "$AWS_REGION"
```

---

## Step 3: Create Greengrass Component

```bash
# Update recipe with actual artifact bucket
RECIPE=$(cat edge/greengrass/s3ap_client/recipe.yaml | \
  sed "s|s3://ARTIFACT_BUCKET|s3://${ARTIFACT_BUCKET}|g")

# Create component version
aws greengrassv2 create-component-version \
  --inline-recipe "$(echo "$RECIPE" | base64)" \
  --region "$AWS_REGION"

# Verify component
aws greengrassv2 list-components \
  --query "components[?componentName=='com.edge-to-cloud.S3APClient']" \
  --region "$AWS_REGION"
```

---

## Step 4: Deploy Component to Device

```bash
# Create deployment targeting the Greengrass core device
CORE_THING="GreengrassCore-${DEVICE_ID}"

aws greengrassv2 create-deployment \
  --target-arn "arn:aws:iot:${AWS_REGION}:${ACCOUNT_ID}:thing/${CORE_THING}" \
  --deployment-name "s3ap-client-deployment-$(date +%s)" \
  --components '{
    "com.edge-to-cloud.S3APClient": {
      "componentVersion": "1.0.0",
      "configurationUpdate": {
        "merge": "{\"S3APAccessPointArn\": \"'"$S3AP_ARN"'\", \"AWSRegion\": \"'"$AWS_REGION"'\", \"DeviceId\": \"'"$DEVICE_ID"'\", \"FlushIntervalSeconds\": \"5\", \"LogLevel\": \"DEBUG\"}"
      }
    }
  }' \
  --region "$AWS_REGION"
```

### Monitor deployment

```bash
# Check deployment status
aws greengrassv2 list-effective-deployments \
  --core-device-thing-name "$CORE_THING" \
  --region "$AWS_REGION" | jq '.effectiveDeployments[0] | {deploymentName, coreDeviceExecutionStatus, reason}'
```

---

## Step 5: Test — Write Files to Incoming Directory

On the Greengrass core device:

```bash
# The component watches /var/lib/greengrass-s3ap/incoming/
INCOMING="/var/lib/greengrass-s3ap/incoming"
sudo mkdir -p "$INCOMING"
sudo chown ggc_user:ggc_group "$INCOMING"

# Write a test JSON file
echo '{"temperature": 25.3, "humidity": 55, "device_id": "'"$DEVICE_ID"'"}' | \
  sudo -u ggc_user tee "${INCOMING}/telemetry_001.json" > /dev/null

# Write a simulated image (random bytes as placeholder)
dd if=/dev/urandom bs=1024 count=50 2>/dev/null | \
  sudo -u ggc_user tee "${INCOMING}/capture_001.jpg" > /dev/null

# Write a batch of sensor readings
for i in $(seq 1 10); do
  echo "{\"sequence\": $i, \"temp\": $(echo "22 + $i * 0.5" | bc), \"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" | \
    sudo -u ggc_user tee "${INCOMING}/sensor_$(printf '%03d' $i).json" > /dev/null
done
```

---

## Step 6: Verify Upload to S3 AP

```bash
# Wait for flush interval (5 seconds configured above)
sleep 10

# Check from your workstation — objects should appear
aws s3api list-objects-v2 \
  --bucket "$S3AP_ARN" \
  --prefix "ingest/${DEVICE_ID}/" \
  --region "$AWS_REGION" | jq '.Contents | length'
# Expected: 12 (1 json + 1 jpg + 10 sensor jsons)

# Verify content of one object
FIRST_KEY=$(aws s3api list-objects-v2 \
  --bucket "$S3AP_ARN" \
  --prefix "ingest/${DEVICE_ID}/" \
  --query "Contents[0].Key" \
  --output text --region "$AWS_REGION")

aws s3api get-object \
  --bucket "$S3AP_ARN" \
  --key "$FIRST_KEY" \
  /dev/stdout --region "$AWS_REGION" | jq . 2>/dev/null || echo "(binary file)"
```

---

## Step 7: Test Offline Resilience

### 7.1 Simulate network disconnection

On the Greengrass device:

```bash
# Block outbound HTTPS to S3 (simulates network failure)
sudo iptables -A OUTPUT -p tcp --dport 443 -j DROP

# Write data while "offline"
for i in $(seq 1 5); do
  echo "{\"offline_test\": true, \"seq\": $i, \"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" | \
    sudo -u ggc_user tee "${INCOMING}/offline_${i}.json" > /dev/null
done

# Check buffer count (on device)
sudo sqlite3 /var/lib/greengrass-s3ap/buffer.db "SELECT COUNT(*) FROM pending_uploads;"
# Expected: 5 (buffered locally)

# Check component log for retry messages
sudo tail -20 /greengrass/v2/logs/com.edge-to-cloud.S3APClient.log | grep -i "retry\|failed\|buffer"
```

### 7.2 Restore connectivity

```bash
# Remove iptables block
sudo iptables -D OUTPUT -p tcp --dport 443 -j DROP

# Wait for flush (component will auto-retry)
sleep 15

# Verify buffer is drained
sudo sqlite3 /var/lib/greengrass-s3ap/buffer.db "SELECT COUNT(*) FROM pending_uploads;"
# Expected: 0 (all flushed to S3 AP)

# Verify objects appeared in S3 AP
aws s3api list-objects-v2 \
  --bucket "$S3AP_ARN" \
  --prefix "ingest/${DEVICE_ID}/" \
  --region "$AWS_REGION" | jq '[.Contents[] | select(.Key | contains("offline"))] | length'
# Expected: 5
```

---

## Step 8: Check Component Logs

```bash
# On the Greengrass device
sudo tail -50 /greengrass/v2/logs/com.edge-to-cloud.S3APClient.log | jq -r '.msg' 2>/dev/null || \
  sudo tail -50 /greengrass/v2/logs/com.edge-to-cloud.S3APClient.log
```

Expected log entries:
```
Starting S3 AP client component: device=rpi5-001, target=arn:aws:s3:ap-northeast-1:...
Ingested file telemetry_001.json → ingest/rpi5-001/year=2026/... (buffered)
Flushed 12 items to S3 AP
Upload failed (attempt 1/5): ... Retrying in 1.2s.
Upload success: key=ingest/rpi5-001/..., size=1024, attempt=2
```

---

## Validation Checklist

| # | Check | Method | Expected |
|---|-------|--------|----------|
| 1 | Greengrass core healthy | `aws greengrassv2 list-core-devices` | status: HEALTHY |
| 2 | Component deployed | `list-effective-deployments` | SUCCEEDED |
| 3 | Files ingested from /incoming/ | ls incoming dir (should be empty after flush) | 0 files remaining |
| 4 | Objects in S3 AP | `aws s3api list-objects-v2` | 12+ objects with Hive paths |
| 5 | Offline buffer works | iptables block → write → unblock → verify | Buffer drains after reconnect |
| 6 | Dead letter on repeated failure | Force 10+ retries | Files in dead_letter/ dir |
| 7 | Multiprotocol access | NFS read same objects | Content matches |
| 8 | No S3 standard bucket | Verify all paths use S3 AP ARN | Confirmed |

---

## Troubleshooting

| Symptom | Likely Cause | Resolution |
|---------|-------------|------------|
| Component fails to start | Missing boto3 on device | Check recipe `install` step; `pip3 install boto3` |
| "Access Denied" on PutObject | Greengrass TES role missing S3 AP permission | Add `s3:PutObject` on S3 AP ARN to the Token Exchange Service role |
| Files remain in /incoming/ | Component not running or wrong permissions | Check `ggc_user` ownership; check component logs |
| Buffer grows but never drains | S3 AP ARN misconfigured | Verify `S3AP_ACCESS_POINT_ARN` env var matches actual AP |
| Deploy stuck at IN_PROGRESS | Artifact download failure | Check artifact S3 bucket permissions; verify bucket exists |

---

## Performance Observations (Record During Demo)

| Metric | Value | Notes |
|--------|-------|-------|
| Flush latency (LAN) | ___ ms | Time from file drop to S3 AP write complete |
| Flush latency (cellular) | ___ ms | If using SORACOM Air |
| Throughput (files/sec) | ___ | Sustained write rate |
| Buffer drain time (10 files) | ___ sec | After network restore |
| S3 AP PutObject latency | ___ ms | Single file, from Lambda @YYYYY |

---

## Cleanup

```bash
# Remove deployment
aws greengrassv2 cancel-deployment --deployment-id <deployment-id> --region "$AWS_REGION"

# Delete component version
aws greengrassv2 delete-component \
  --arn "arn:aws:greengrass:${AWS_REGION}:${ACCOUNT_ID}:components:com.edge-to-cloud.S3APClient:versions:1.0.0" \
  --region "$AWS_REGION"

# Remove artifact from S3
aws s3 rm "s3://${ARTIFACT_BUCKET}/com.edge-to-cloud.S3APClient/" --recursive --region "$AWS_REGION"

# On device: remove local data
sudo rm -rf /var/lib/greengrass-s3ap/
```

---

## Next Steps

- **Demo Guide 03** (planned): FlexCache Read Cache — verify that data written to Origin via S3 AP is visible at on-prem or other-region Cache volumes via NFS
- **Demo Guide 04** (planned): FlexCache Write-Back — edge ONTAP as local NFS write buffer with async flush to FSx for ONTAP Origin
