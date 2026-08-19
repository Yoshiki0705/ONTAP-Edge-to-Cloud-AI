> 🌐 Language: **English**

# Demo Guide 00: IoT × S3 AP Common Prerequisites

> This document describes the shared prerequisites for all IoT edge → FSx for ONTAP S3 AP demo guides in this project.

> 📐 **Design References**:
> - [IoT + S3 AP + FlexCache Integration Scenarios](../en/iot-greengrass-flexcache-integration.md)
> - [S3 AP + FlexCache / SnapMirror Design Considerations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/blob/main/docs/en/s3ap-flexcache-snapmirror-considerations.md)

---

## Required Tools

| Tool | Version | Check Command | Notes |
|------|---------|---------------|-------|
| AWS CLI | v2.15+ | `aws --version` | IoT Core + FSx APIs |
| jq | 1.6+ | `jq --version` | JSON processing |
| Python | 3.12+ | `python3 --version` | Lambda + Greengrass components |
| boto3 | 1.34+ | `python3 -c "import boto3; print(boto3.__version__)"` | S3 AP PutObject |
| SAM CLI | 1.100+ | `sam --version` | Lambda deployment (optional) |
| mosquitto_pub | 2.0+ | `mosquitto_pub --help` | MQTT test publishing |

## ONTAP Version Requirements

| Feature | Minimum ONTAP | Required for Demo |
|---------|:-------------:|:-----------------:|
| S3 Access Point (PutObject/GetObject) | 9.14.1 | Demo 01, 02 |
| FlexCache write-back | 9.15.1 | Demo 03 (future) |
| FlexCache (read-only) | 9.5 | Demo 04 (future) |

## AWS Services Used

| Service | Purpose | Estimated Cost (PoC) |
|---------|---------|---------------------|
| FSx for ONTAP | Origin storage + S3 AP endpoint | ~$500/month (1TB, 128 MBps) |
| AWS IoT Core | MQTT broker + rules engine | $1/million messages |
| AWS Lambda | Telemetry aggregation → S3 AP | $0.20/million invocations |
| Amazon Athena | Query verification via S3 AP | $5/TB scanned |
| AWS IoT Greengrass | Edge runtime (Demo 02) | Free (device-side) |

## Common Environment Variables

All demo guides assume these variables are exported:

```bash
# AWS
export AWS_REGION="ap-northeast-1"
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# FSx for ONTAP (set after stack deployment or manual lookup)
export FS_ID="fs-XXXXXXXXXXXXXXXXX"
export SVM_ID="svm-XXXXXXXXXXXXXXXXX"
export FSXN_MGMT_IP=""  # Set in Step 1 of each guide

# S3 Access Point
export S3AP_NAME="iot-ingest-ap"
export S3AP_ARN="arn:aws:s3:${AWS_REGION}:${ACCOUNT_ID}:accesspoint/${S3AP_NAME}"

# IoT
export IOT_ENDPOINT=$(aws iot describe-endpoint --endpoint-type iot:Data-ATS --query endpointAddress --output text)
export MQTT_TOPIC_PREFIX="edge"

# Device
export DEVICE_ID="rpi5-001"
```

## FSx for ONTAP Infrastructure

### Option A: Deploy via CloudFormation (recommended for PoC)

```bash
aws cloudformation deploy \
  --template-file cloud/fsxn/template.yaml \
  --stack-name edge-to-cloud-fsxn-poc \
  --parameter-overrides \
    Environment=poc \
    FSxStorageCapacity=1024 \
    FSxThroughputCapacity=128 \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$AWS_REGION"
```

Wait ~30 minutes for file system creation, then set variables:

```bash
export FS_ID=$(aws cloudformation describe-stacks \
  --stack-name edge-to-cloud-fsxn-poc \
  --query "Stacks[0].Outputs[?OutputKey=='FileSystemId'].OutputValue" \
  --output text --region "$AWS_REGION")

export SVM_ID=$(aws cloudformation describe-stacks \
  --stack-name edge-to-cloud-fsxn-poc \
  --query "Stacks[0].Outputs[?OutputKey=='SVMId'].OutputValue" \
  --output text --region "$AWS_REGION")
```

### Option B: Use existing FSx for ONTAP

Set `FS_ID` and `SVM_ID` manually from your existing environment.

## ONTAP REST API Helper

```bash
# Get management endpoint
FSXN_MGMT_IP=$(aws fsx describe-file-systems \
  --file-system-ids "$FS_ID" \
  --query 'FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]' \
  --output text --region "$AWS_REGION")

# ONTAP API call helper
ontap_api() {
  local method="$1" path="$2" body="${3:-}"
  curl -sk -u "fsxadmin:${FSXN_PASSWORD}" \
    -X "$method" "https://${FSXN_MGMT_IP}/api${path}" \
    -H "Content-Type: application/json" \
    ${body:+-d "$body"}
}
```

> **Security note**: In production, store `FSXN_PASSWORD` in AWS Secrets Manager and retrieve dynamically. For PoC demos, you may export it temporarily.

## IoT Core Setup

### Create IoT Thing + Certificate (for MQTT testing)

```bash
# Create thing
aws iot create-thing --thing-name "$DEVICE_ID" --region "$AWS_REGION"

# Create certificate
CERT_OUTPUT=$(aws iot create-keys-and-certificate \
  --set-as-active \
  --certificate-pem-outfile "certs/${DEVICE_ID}-cert.pem" \
  --public-key-outfile "certs/${DEVICE_ID}-public.pem" \
  --private-key-outfile "certs/${DEVICE_ID}-private.pem" \
  --region "$AWS_REGION")

CERT_ARN=$(echo "$CERT_OUTPUT" | jq -r '.certificateArn')

# Attach policy (create policy first if needed)
aws iot create-policy \
  --policy-name "edge-to-cloud-iot-policy" \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["iot:Connect", "iot:Publish", "iot:Subscribe", "iot:Receive"],
      "Resource": "*"
    }]
  }' --region "$AWS_REGION" 2>/dev/null || true

aws iot attach-policy --policy-name "edge-to-cloud-iot-policy" --target "$CERT_ARN" --region "$AWS_REGION"
aws iot attach-thing-principal --thing-name "$DEVICE_ID" --principal "$CERT_ARN" --region "$AWS_REGION"

# Download root CA
curl -o certs/AmazonRootCA1.pem https://www.amazontrust.com/repository/AmazonRootCA1.pem
```

## Volume + S3 AP Preparation

Each demo guide includes volume/S3 AP creation steps, but here is the common pattern:

```bash
# 1. Create volume on SVM (via ONTAP REST API)
ontap_api POST "/storage/volumes" '{
  "name": "iot_data",
  "svm": {"name": "svm-edge-to-cloud"},
  "size": "100GB",
  "nas": {"path": "/iot-data", "security_style": "unix"},
  "guarantee": {"type": "none"},
  "tiering": {"policy": "auto"}
}'

# 2. Create and attach S3 Access Point (via FSx API)
VOLUME_ID=$(aws fsx describe-volumes \
  --filters "Name=file-system-id,Values=$FS_ID" \
  --query "Volumes[?Name=='iot_data'].VolumeId" \
  --output text --region "$AWS_REGION")

aws fsx create-and-attach-s3-access-point \
  --name "$S3AP_NAME" \
  --volume-id "$VOLUME_ID" \
  --file-system-identity '{"IdentityType":"UNIX","PosixUser":{"Uid":0,"Gid":0}}' \
  --region "$AWS_REGION"

# 3. Wait for AVAILABLE status
aws fsx describe-s3-access-points \
  --filters "Name=file-system-id,Values=$FS_ID" \
  --query "S3AccessPoints[?Name=='${S3AP_NAME}'].Lifecycle" \
  --output text --region "$AWS_REGION"
```

## Verification: S3 AP PutObject Test

Before proceeding to any demo, confirm S3 AP write works:

```bash
# Write a test object via S3 AP
echo '{"test": "hello from S3 AP", "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}' | \
  aws s3api put-object \
    --bucket "$S3AP_ARN" \
    --key "test/hello.json" \
    --body /dev/stdin \
    --content-type "application/json" \
    --region "$AWS_REGION"

# Verify via ListObjectsV2
aws s3api list-objects-v2 \
  --bucket "$S3AP_ARN" \
  --prefix "test/" \
  --region "$AWS_REGION"

# Verify via NFS (from EC2 in same VPC)
# ssh to EC2: cat /mnt/fsxn/iot-data/test/hello.json
```

## Cleanup Notes

| Resource | Cleanup Command | Notes |
|----------|----------------|-------|
| S3 Access Point | `aws fsx detach-and-delete-s3-access-point --name $S3AP_NAME --region $AWS_REGION` | Must delete before volume |
| Volume | `ontap_api DELETE "/storage/volumes/{uuid}"` | After S3 AP deleted |
| CloudFormation stack | `aws cloudformation delete-stack --stack-name edge-to-cloud-fsxn-poc` | Deletes VPC + FSx |
| IoT Thing/Cert | `aws iot delete-thing --thing-name $DEVICE_ID` | After detaching principals |
| Lambda/IoT Rule | `aws cloudformation delete-stack --stack-name edge-to-cloud-iot-ingestion-poc` | Demo 01 stack |

---

## Demo Guide Index

| # | Title | Validates |
|---|-------|-----------|
| 00 | Prerequisites (this document) | Environment setup |
| 01 | [IoT Core → Lambda → S3 AP Direct Write](./demo-guide-01-iot-core-lambda-s3ap.md) | MQTT → Lambda → PutObject → FSx for ONTAP → Athena query |
| 02 | [Greengrass S3 AP Client Component](./demo-guide-02-greengrass-s3ap-client.md) | Edge device → Greengrass → PutObject → FSx for ONTAP |
| 03 | FlexCache Read Cache Distribution (planned) | Origin → FlexCache → Multi-site NFS access |
| 04 | FlexCache Write-Back Edge Buffer (planned) | Edge ONTAP Cache → async flush → Origin |
