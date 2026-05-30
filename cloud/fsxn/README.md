# FSx for ONTAP Infrastructure

> ⚠️ **Cost Warning**: FSx for ONTAP costs ~$500+/month (Multi-AZ, 128 MBps, 1 TiB). Deploy only when needed for Phase 3 testing.

## Purpose

SnapMirror destination for on-premises ONTAP data. Provides S3 Access Points for AWS AI/analytics services to access aggregated data without copying.

## Architecture

```
[On-premises ONTAP] --SnapMirror--> [FSx for ONTAP] --S3 AP--> [Athena/Bedrock/SageMaker]
```

## Deploy

```bash
aws cloudformation deploy \
  --template-file cloud/fsxn/template.yaml \
  --stack-name edge-to-cloud-fsxn \
  --parameter-overrides Environment=poc \
  --region ap-northeast-1
```

## After Deployment

### 1. Create Volume (AWS CLI)

```bash
aws fsx create-volume \
  --volume-type ONTAP \
  --name vol_images_dp \
  --ontap-configuration '{
    "StorageVirtualMachineId": "<SVM_ID>",
    "JunctionPath": "/vol_images_dp",
    "SizeInMegabytes": 102400,
    "StorageEfficiencyEnabled": true,
    "OntapVolumeType": "DP"
  }'
```

### 2. Configure SnapMirror (On-premises ONTAP CLI)

```bash
# Peer clusters
cluster peer create -address-family ipv4 \
  -peer-addrs <FSX_INTERCLUSTER_IP>

# Peer SVMs
vserver peer create -vserver svm-iot \
  -peer-vserver svm-edge-to-cloud \
  -peer-cluster <FSX_CLUSTER_NAME> \
  -applications snapmirror

# Create SnapMirror relationship
snapmirror create \
  -source-path svm-iot:vol_images \
  -destination-path svm-edge-to-cloud:vol_images_dp \
  -type XDP -policy MirrorAllSnapshots

# Initialize
snapmirror initialize \
  -destination-path svm-edge-to-cloud:vol_images_dp
```

### 3. Create S3 Access Point

Configure via AWS Console or FSx for ONTAP API after volume is synced.

## Teardown (to stop costs)

```bash
aws cloudformation delete-stack --stack-name edge-to-cloud-fsxn
```
