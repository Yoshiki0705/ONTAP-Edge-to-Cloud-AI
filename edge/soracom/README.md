# SORACOM Configuration Guide (Option: Cellular Connectivity)

> 🌐 [日本語](./README_ja.md) | English

> **Note**: This guide is for sites WITHOUT wired LAN connectivity. If wired LAN is available, the primary data path is Pi → NFS → ONTAP (see main README). SORACOM is positioned as a fallback/remote connectivity option.

This guide covers SORACOM service configuration for cellular connectivity scenarios.

## Prerequisites

- SORACOM account with Japan coverage (plan-D)
- IoT SIM activated and registered
- AWS infrastructure deployed (CloudFormation stack `edge-to-cloud-ai-poc`)

## Architecture

```
Raspberry Pi → SORACOM Air (cellular) → SORACOM Funnel → Amazon Kinesis
                                       → SORACOM Flux  → Amazon S3 + Bedrock
```

## 1. SORACOM Funnel Configuration (Sensor Data → Kinesis)

Funnel forwards device data directly to Amazon Kinesis without device-side code changes.

### Step 1: Create IAM Role for SORACOM

The CloudFormation stack already created `EdgeToCloud-SoracomIngestion-poc`.
Update the ExternalId with your actual SORACOM Operator ID:

```bash
# Get your SORACOM Operator ID from console or CLI
# Console: https://console.soracom.io → Operator ID (top-right)

# Update the CloudFormation stack with real Operator ID
aws cloudformation update-stack \
  --stack-name edge-to-cloud-ai-poc \
  --use-previous-template \
  --parameters \
    ParameterKey=Environment,UsePreviousValue=true \
    ParameterKey=SoracomOperatorId,ParameterValue=<YOUR_OPERATOR_ID> \
    ParameterKey=AlertEmail,UsePreviousValue=true \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### Step 2: Configure Funnel in SORACOM Console

1. Go to **SORACOM Console** → **SIM Groups** → Create or select a group
2. Navigate to **SORACOM Funnel** settings
3. Configure:

| Setting | Value |
|---------|-------|
| Enabled | ON |
| Destination service | Amazon Kinesis Data Streams |
| Credentials | AWS IAM Role |
| Role ARN | `arn:aws:iam::<ACCOUNT_ID>:role/EdgeToCloud-SoracomIngestion-poc` |
| External ID | Your SORACOM Operator ID |
| Region | `ap-northeast-1` |
| Stream name | `edge-to-cloud-poc-ingestion` |
| Content type | JSON |

### Step 3: Assign SIM to Group

1. Go to **SIM Management**
2. Select your IoT SIM
3. Assign to the configured group

### Step 4: Verify

From the Raspberry Pi (with SORACOM SIM connected):

```bash
# Send test data to Funnel
curl -X POST http://funnel.soracom.io \
  -H "Content-Type: application/json" \
  -d '{
    "schema_version": "1.0",
    "message_id": "test-001",
    "device_id": "rpi5-001",
    "timestamp": "2026-05-29T10:00:00Z",
    "message_type": "sensor_reading",
    "payload": {
      "readings": [{"sensor_id": "test", "sensor_type": "temperature", "values": {"temperature_celsius": 25.0}}]
    }
  }'
```

Verify data arrives in Kinesis:
```bash
aws kinesis get-shard-iterator \
  --stream-name edge-to-cloud-poc-ingestion \
  --shard-id shardId-000000000000 \
  --shard-iterator-type LATEST \
  --region ap-northeast-1
```

---

## 2. SORACOM Flux Configuration (Camera Images → AI Analysis)

Flux provides a low-code workflow for camera image capture → AI analysis → notification.

### Step 1: Create Flux App

1. Go to **SORACOM Console** → **Flux** → **Create App**
2. Name: `print-quality-monitor`

### Step 2: Define Workflow

```
[Trigger: Device Image Upload]
    ↓
[Action: Store to S3]
    ↓
[Action: Invoke Lambda]  → edge-to-cloud-image-analyzer
    ↓
[Condition: anomaly_detected AND confidence >= 0.7]
    ↓
[Action: Send Notification (Slack/Teams)]
```

### Step 3: Configure S3 Storage Action

| Setting | Value |
|---------|-------|
| Destination | Amazon S3 |
| Bucket | `edge-to-cloud-ai-poc-<ACCOUNT_ID>` |
| Key prefix | `raw/image_capture/` |
| Credentials | Same IAM Role as Funnel |

### Step 4: Configure Lambda Invocation

| Setting | Value |
|---------|-------|
| Action type | AWS Lambda |
| Function ARN | `arn:aws:lambda:ap-northeast-1:<ACCOUNT_ID>:function:edge-to-cloud-image-analyzer` |
| Region | `ap-northeast-1` |

---

## 3. SORACOM Harvest (Prototyping / Visualization)

For quick prototyping, Harvest stores and visualizes data without AWS setup.

### Enable Harvest Data

1. Go to **SIM Group** → **SORACOM Harvest Data**
2. Enable: ON

### Send Data

```bash
curl -X POST http://harvest.soracom.io \
  -H "Content-Type: application/json" \
  -d '{"temperature": 24.5, "humidity": 45.2}'
```

### View Dashboard

Go to **SORACOM Console** → **Harvest Data** → Select SIM → View graphs

---

## 4. Network Security (Optional: VPG)

For production, consider SORACOM VPG (Virtual Private Gateway) for private connectivity:

- Creates a dedicated VPN between SORACOM and your AWS VPC
- Eliminates internet exposure for device-to-cloud communication
- Adds cost (~$100/month) but improves security posture

---

## Troubleshooting

| Issue | Check |
|-------|-------|
| Funnel data not arriving | Verify SIM is in correct group, check Funnel logs in console |
| IAM permission denied | Verify ExternalId matches Operator ID, check role trust policy |
| Flux workflow not triggering | Check device is sending to correct endpoint, verify Flux app is active |
| High latency | Check signal strength (SORACOM console), consider data compression |
