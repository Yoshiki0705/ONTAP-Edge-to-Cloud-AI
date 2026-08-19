# Deployment Guide

How to deploy the Edge-to-Cloud AI CloudFormation stacks into your existing AWS environment.

---

## Quick Start (Fastest Path)

To try AI image analysis without FSx for ONTAP:

```bash
# 1. Preflight check
./scripts/preflight-check.sh --skip network

# 2. Deploy shared infrastructure (3–5 min)
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides Environment=poc AlertEmail=you@example.com \
  --capabilities CAPABILITY_NAMED_IAM \
  --tags Project=edge-to-cloud-ai

# 3. Verify deployment
aws cloudformation describe-stacks --stack-name edge-to-cloud-ai-poc \
  --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' --output table

# 4. Deploy a use case (1–2 min)
aws cloudformation deploy \
  --template-file usecases/3d-print-quality/template.yaml \
  --stack-name edge-to-cloud-print-quality-poc \
  --parameter-overrides SharedStackName=edge-to-cloud-ai-poc \
  --capabilities CAPABILITY_NAMED_IAM

# 5. Deploy Lambda code (templates contain placeholder only)
cd cloud/ai/image_analyzer
zip -r /tmp/image_analyzer.zip handler.py
aws lambda update-function-code \
  --function-name edge-to-cloud-image-analyzer-edge-to-cloud-print-quality-poc \
  --zip-file fileb:///tmp/image_analyzer.zip
```

> For full details, existing-VPC integration, and FSx for ONTAP setup, see the sections below.

---

## What You Get After Deployment

| Stack | Resources Created | Verification |
|-------|-------------------|-------------|
| ingestion | S3 bucket, Kinesis Stream, Firehose, SNS Topic, IAM Roles, Glue DB | `aws cloudformation describe-stacks --stack-name <name> --query 'Stacks[0].Outputs'` |
| fsxn | VPC, 2 subnets, FSx for ONTAP file system, SVM | Check FSx console |
| 3d-print-quality | Lambda function, CloudWatch Alarms, EventBridge Rule | `aws lambda get-function --function-name <name>` |
| visual-inspection | Lambda function, CloudWatch Alarm | Same as above |
| ontap-telemetry | Glue Crawler, CloudWatch Alarms, Athena Named Queries | Check Glue console |

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Architecture & Deployment Order](#2-architecture--deployment-order)
3. [Preflight Check](#3-preflight-check)
4. [Per-Stack Deployment](#4-per-stack-deployment)
5. [Parameter Reference](#5-parameter-reference)
6. [`deploy` vs `create-stack`](#6-deploy-vs-create-stack)
7. [VPC Endpoint Conflict Matrix](#7-vpc-endpoint-conflict-matrix)
8. [Cost Estimates](#8-cost-estimates)
9. [Day 2 Operations](#9-day-2-operations)
10. [Troubleshooting](#10-troubleshooting)
11. [Cleanup](#11-cleanup)

---

## 1. Prerequisites

### Tools

| Tool | Minimum Version | Install |
|------|----------------|---------|
| AWS CLI | v2.x | [Official guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| jq | 1.6+ | macOS: `brew install jq` / Linux: `sudo apt-get install jq` / Windows: `choco install jq` |
| cfn-lint | 1.x (recommended) | `pip install cfn-lint` |
| zip | (optional) | For Lambda code packaging |

### AWS Account Requirements

- Permissions for CloudFormation, S3, Kinesis, Lambda, IAM, SNS, and Glue
- If deploying the FSx for ONTAP stack: `fsx:*` permissions
- For Bedrock use cases: model access enabled for the target models
- Ability to acknowledge `CAPABILITY_NAMED_IAM`

### Region

Tokyo region (`ap-northeast-1`) is recommended. The `jp.` prefix on Bedrock model IDs is the [cross-region inference](https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html) designation for Japan and works only in `ap-northeast-1`. For other regions, change the prefix (e.g., `us.` for `us-east-1`).

---

## 2. Architecture & Deployment Order

```
┌─────────────────────────────────────────────────────────────────┐
│                    Deployment Order                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ① cloud/fsxn/template.yaml          (optional — FSx for ONTAP)│
│       ↓                                                         │
│  ② cloud/ingestion/template.yaml     (required — shared infra) │
│       ↓                                                         │
│  ③ usecases/*/template.yaml          (pick one — use case)     │
│     ├── ontap-telemetry-analytics                               │
│     ├── 3d-print-quality                                        │
│     └── visual-inspection                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Dependencies:**
- Use-case stacks reference the `ingestion` stack Outputs via `Fn::ImportValue`
- The `fsxn` stack is independent — skip it if FSx for ONTAP is not needed

---

## 3. Preflight Check

Always run the preflight script before deploying.

```bash
# Run all checks
./scripts/preflight-check.sh

# Skip network checks
./scripts/preflight-check.sh --skip network

# Skip Bedrock checks (when not using AI models)
./scripts/preflight-check.sh --skip bedrock

# Validate a single stack
./scripts/preflight-check.sh --stack ingestion

# Specify region
./scripts/preflight-check.sh --region ap-northeast-1
```

What the script validates:
- AWS CLI installation and credential validity
- IAM permission spot checks
- CloudFormation template syntax
- VPC CIDR overlap detection
- AZ availability (FSx for ONTAP Multi-AZ needs >= 2 AZs)
- Bedrock model access
- Existing stack name conflicts
- Cost warnings

---

## 4. Per-Stack Deployment

### 4.1 FSx for ONTAP Stack (optional)

> **Cost warning**: FSx for ONTAP costs ~$500+/month minimum. Delete the stack promptly after PoC completion.

```bash
# Copy and customize the parameter file
cp cfn-params/fsxn.example.json cfn-params/fsxn.local.json
# vi cfn-params/fsxn.local.json  ← edit for your environment

# Deploy
aws cloudformation deploy \
  --template-file cloud/fsxn/template.yaml \
  --stack-name edge-to-cloud-fsxn-poc \
  --parameter-overrides \
    Environment=poc \
    VpcCidr=10.0.0.0/16 \
    SubnetCidr1=10.0.1.0/24 \
    SubnetCidr2=10.0.2.0/24 \
    FSxStorageCapacity=1024 \
    FSxThroughputCapacity=128 \
  --capabilities CAPABILITY_NAMED_IAM \
  --tags Project=edge-to-cloud-ai Environment=poc
```

Expected duration: ~30–45 minutes (FSx for ONTAP creation is time-consuming).

### 4.2 Ingestion Stack (required)

```bash
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides \
    Environment=poc \
    AlertEmail=alerts@example.com \
  --capabilities CAPABILITY_NAMED_IAM \
  --tags Project=edge-to-cloud-ai Environment=poc
```

With SORACOM cellular connectivity (optional):

> **What is SORACOM Operator ID?** A `OP00`-prefixed identifier found in the SORACOM console under "Operator Settings." It serves as the `ExternalId` for the AWS IAM role, restricting AssumeRole calls to your SORACOM account.

```bash
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides \
    Environment=poc \
    AlertEmail=alerts@example.com \
    SoracomOperatorId=OP00XXXXXXXX \
  --capabilities CAPABILITY_NAMED_IAM \
  --tags Project=edge-to-cloud-ai Environment=poc
```

Expected duration: ~3–5 minutes.

#### Post-Deploy Verification

```bash
# Check Outputs (S3 bucket name, Kinesis ARN, SNS Topic ARN, etc.)
aws cloudformation describe-stacks --stack-name edge-to-cloud-ai-poc \
  --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' --output table
```

> **SNS confirmation email**: If you specified `AlertEmail`, AWS sends a confirmation email. **You must click the link in that email to confirm the subscription** — otherwise alerts will not be delivered.

### 4.3 Use-Case Stacks (pick one or more)

#### ONTAP Telemetry Analytics

```bash
aws cloudformation deploy \
  --template-file usecases/ontap-telemetry-analytics/template.yaml \
  --stack-name edge-to-cloud-telemetry-poc \
  --parameter-overrides \
    SharedStackName=edge-to-cloud-ai-poc \
  --tags Project=edge-to-cloud-ai Environment=poc UseCase=ontap-telemetry
```

#### 3D Print Quality Monitoring

```bash
aws cloudformation deploy \
  --template-file usecases/3d-print-quality/template.yaml \
  --stack-name edge-to-cloud-print-quality-poc \
  --parameter-overrides \
    SharedStackName=edge-to-cloud-ai-poc \
    BedrockScreeningModel=jp.anthropic.claude-haiku-4-5-20251001-v1:0 \
    BedrockDetailModel=jp.anthropic.claude-sonnet-4-5-20250929-v1:0 \
    ConfidenceThreshold=0.7 \
  --capabilities CAPABILITY_NAMED_IAM \
  --tags Project=edge-to-cloud-ai Environment=poc UseCase=3d-print-quality
```

#### Visual Inspection

```bash
aws cloudformation deploy \
  --template-file usecases/visual-inspection/template.yaml \
  --stack-name edge-to-cloud-visual-inspection-poc \
  --parameter-overrides \
    SharedStackName=edge-to-cloud-ai-poc \
    BedrockScreeningModel=jp.anthropic.claude-haiku-4-5-20251001-v1:0 \
    BedrockDetailModel=jp.anthropic.claude-sonnet-4-5-20250929-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM \
  --tags Project=edge-to-cloud-ai Environment=poc UseCase=visual-inspection
```

### 4.4 Deploy Lambda Function Code

The CloudFormation templates contain placeholder Lambda code only. You must deploy the actual handler separately:

```bash
# For 3D Print Quality / Visual Inspection
cd cloud/ai/image_analyzer
zip -r /tmp/image_analyzer.zip handler.py requirements.txt
aws lambda update-function-code \
  --function-name edge-to-cloud-image-analyzer-edge-to-cloud-print-quality-poc \
  --zip-file fileb:///tmp/image_analyzer.zip

# If dependencies are needed, create a Lambda Layer:
# pip install -r requirements.txt -t python/
# zip -r /tmp/layer.zip python/
# aws lambda publish-layer-version --layer-name image-analyzer-deps \
#   --zip-file fileb:///tmp/layer.zip --compatible-runtimes python3.12
```

> **Note**: Until you run `update-function-code`, the Lambda function returns HTTP 501.

---

## 5. Parameter Reference

### cloud/fsxn/template.yaml

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `Environment` | String | `poc` | Environment name (`poc` / `production`) |
| `VpcCidr` | String | `10.0.0.0/16` | VPC CIDR block |
| `SubnetCidr1` | String | `10.0.1.0/24` | Subnet 1 (primary AZ) |
| `SubnetCidr2` | String | `10.0.2.0/24` | Subnet 2 (secondary AZ) |
| `FSxStorageCapacity` | Number | `1024` | Storage capacity in GiB (minimum 1024) |
| `FSxThroughputCapacity` | Number | `128` | Throughput capacity in MBps (128/256/512/1024/2048) |

### cloud/ingestion/template.yaml

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `Environment` | String | `poc` | Environment name (`poc` / `staging` / `production`) |
| `SoracomOperatorId` | String | `""` | SORACOM Operator ID (cellular connectivity only) |
| `AlertEmail` | String | `""` | Email address for anomaly alerts |

### usecases/ontap-telemetry-analytics/template.yaml

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `SharedStackName` | String | `edge-to-cloud-ai-poc` | Ingestion stack name (for CrossStack references) |

### usecases/3d-print-quality/template.yaml

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `SharedStackName` | String | `edge-to-cloud-ai-poc` | Ingestion stack name |
| `BedrockScreeningModel` | String | `jp.anthropic.claude-haiku-4-5-20251001-v1:0` | Stage 1 screening model |
| `BedrockDetailModel` | String | `jp.anthropic.claude-sonnet-4-5-20250929-v1:0` | Stage 2 detailed analysis model |
| `ConfidenceThreshold` | String | `0.7` | Minimum confidence to trigger alert |

### usecases/visual-inspection/template.yaml

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `SharedStackName` | String | `edge-to-cloud-ai-poc` | Ingestion stack name |
| `BedrockScreeningModel` | String | `jp.anthropic.claude-haiku-4-5-20251001-v1:0` | Stage 1 screening model |
| `BedrockDetailModel` | String | `jp.anthropic.claude-sonnet-4-5-20250929-v1:0` | Stage 2 detailed analysis model |

---

## 6. `deploy` vs `create-stack`

| Aspect | `aws cloudformation deploy` | `aws cloudformation create-stack` |
|--------|----------------------------|----------------------------------|
| Idempotent | Yes (updates existing stacks) | No (fails if stack exists) |
| Parameter passing | `--parameter-overrides Key=Value` | `--parameters file://params.json` |
| Change sets | Auto-created and executed | Manual `create-change-set` required |
| Recommended for | CI/CD, iterative deployment | One-shot creation with JSON param files |

This project recommends **`deploy`**. If you prefer `create-stack`:

```bash
# create-stack with parameter file
aws cloudformation create-stack \
  --template-body file://cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameters file://cfn-params/ingestion.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# Wait for completion
aws cloudformation wait stack-create-complete \
  --stack-name edge-to-cloud-ai-poc
```

> **Note**: `deploy` uses `--parameter-overrides Key=Value` format, while `create-stack` uses `--parameters` with JSON array format (the format used in `cfn-params/*.example.json` files).

---

## 7. VPC Endpoint Conflict Matrix

VPC endpoints required for private-subnet connectivity. When integrating into an existing VPC, avoid creating duplicates.

| VPC Endpoint | Type | Required By | Notes |
|-------------|------|-------------|-------|
| `com.amazonaws.<region>.fsx` | Interface | fsxn | FSx for ONTAP management API |
| `com.amazonaws.<region>.s3` | Gateway | ingestion, all use cases | Free, attach to route table |
| `com.amazonaws.<region>.kinesis-streams` | Interface | ingestion | Kinesis PutRecord |
| `com.amazonaws.<region>.kinesis-firehose` | Interface | ingestion | Firehose delivery |
| `com.amazonaws.<region>.bedrock-runtime` | Interface | 3d-print-quality, visual-inspection | Model invocation |
| `com.amazonaws.<region>.sns` | Interface | ingestion, all use cases | Alert delivery |
| `com.amazonaws.<region>.glue` | Interface | ontap-telemetry-analytics | Crawler execution |
| `com.amazonaws.<region>.logs` | Interface | all Lambda functions | CloudWatch Logs |
| `com.amazonaws.<region>.monitoring` | Interface | all use cases | CloudWatch Metrics |

### Integration Notes for Existing VPCs

1. **CIDR overlap**: `preflight-check.sh` auto-detects conflicts. Change `VpcCidr` if the default `10.0.0.0/16` collides with existing VPCs.
2. **Security groups**: FSx for ONTAP uses NFS (2049), SMB (445), and HTTPS (443) for internal communication.
3. **DNS resolution**: VPC DNS must be enabled (`EnableDnsSupport: true`).
4. **Route tables**: S3 Gateway endpoints must be explicitly associated with the target subnet route tables.
5. **SnapMirror ports**: The template opens 11104-11105/tcp to `0.0.0.0/0` (for cross-region SnapMirror). If using SnapMirror only from on-premises, restrict the source IP range.

---

## 8. Cost Estimates

### Monthly Cost Breakdown (ap-northeast-1, PoC configuration)

| Resource | Configuration | Est. Monthly Cost |
|----------|--------------|-------------------|
| FSx for ONTAP | 1 TiB SSD, 128 MBps, Multi-AZ | ~$500+ |
| Kinesis Data Stream | ON_DEMAND mode | ~$15–50 |
| Amazon Data Firehose | 5 MB buffer, 300s interval | ~$5–20 |
| S3 | Standard, a few GB | ~$1–10 |
| Lambda | 1000 invocations/day, 256 MB, 90s | ~$5–15 |
| Bedrock (Claude) | 1000 invocations/day | ~$10–100 |
| Glue Crawler | 1 run/day | ~$30/month |
| SNS | Hundreds of messages/month | <$1 |
| **Total (with FSx for ONTAP)** | | **~$570–730** |
| **Total (without FSx for ONTAP)** | | **~$70–230** |

> **Cost reduction tips:**
> - Delete the FSx for ONTAP stack after PoC completion
> - Switch Kinesis from ON_DEMAND to PROVISIONED for low-traffic workloads
> - Change Glue Crawler schedule from daily to weekly
> - Restrict Bedrock calls to Haiku only (use Sonnet only for low-confidence cases)

> **AWS Free Tier eligibility (new accounts, first 12 months):**
> - S3: 5 GB standard storage
> - Lambda: 1M requests/month + 400,000 GB-seconds
> - Kinesis: not eligible (ON_DEMAND has no free tier)
> - SNS: 1,000 email notifications/month

---

## 9. Day 2 Operations

### 9.1 Stack Updates

```bash
# After modifying a template, re-run deploy (idempotent)
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides Environment=poc AlertEmail=new-alerts@example.com \
  --capabilities CAPABILITY_NAMED_IAM
```

```bash
# Drift detection (detect manual changes outside CloudFormation)
aws cloudformation detect-stack-drift --stack-name edge-to-cloud-ai-poc
# Check result after a few minutes
aws cloudformation describe-stack-drift-detection-status \
  --stack-drift-detection-id <detection-id>
```

### 9.2 Monitoring Dashboard

Key metrics to watch after deployment:

| Metric | Namespace | Threshold Example |
|--------|-----------|-------------------|
| FSx for ONTAP capacity utilization | `EdgeToCloud/ONTAP` | > 80% warning |
| FSx for ONTAP write latency | `EdgeToCloud/ONTAP` | P95 > 5ms warning |
| Lambda error rate | `AWS/Lambda` | > 5% |
| Kinesis IteratorAge | `AWS/Kinesis` | > 60s |
| Anomaly detection rate | `EdgeToCloud/PrintQuality` | > 30% |

### 9.3 Log Inspection

```bash
# Tail Lambda logs
aws logs tail /aws/lambda/edge-to-cloud-image-analyzer-edge-to-cloud-print-quality-poc \
  --follow --since 1h

# Check stack events for failures
aws cloudformation describe-stack-events \
  --stack-name edge-to-cloud-ai-poc \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED` || ResourceStatus==`UPDATE_FAILED`]'
```

### 9.4 Backup & Recovery

- **S3**: Versioning enabled. Lifecycle rules transition to IA at 90 days, Glacier at 365 days.
- **FSx for ONTAP**: Enable automatic backups (Snapshot policies configured on the ONTAP side).
- **Kinesis**: 24-hour data retention (replay available).

### 9.5 Scaling

| Component | Scaling Method |
|-----------|---------------|
| Kinesis | Automatic with ON_DEMAND |
| Firehose | Adjust buffer size / interval |
| Lambda | Reserved concurrency settings |
| FSx for ONTAP | Incremental throughput / storage increases |

---

## 10. Troubleshooting

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `InsufficientCapabilities` | Missing `CAPABILITY_NAMED_IAM` | Add `--capabilities CAPABILITY_NAMED_IAM` |
| `Stack already exists` | Same-name stack present | Rename the stack or use `deploy` (updates in place) |
| `No export named ...` | Dependency stack not deployed | Deploy the Ingestion stack first |
| `CIDR block conflicts` | VPC CIDR overlaps with existing | Change the `VpcCidr` parameter |
| `ResourceNotFound (Bedrock)` | Model access not enabled | Enable model access in Bedrock console |
| `CREATE_FAILED (FSx)` | Insufficient AZs or quota exceeded | Check Service Quotas |

### Recovery After Rollback

```bash
# Check stack status
aws cloudformation describe-stacks \
  --stack-name edge-to-cloud-ai-poc \
  --query 'Stacks[0].StackStatus'

# Delete a ROLLBACK_COMPLETE stack and recreate
aws cloudformation delete-stack --stack-name edge-to-cloud-ai-poc
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-ai-poc
# → re-deploy
```

---

## 11. Cleanup

Delete stacks in **reverse order** of creation.

```bash
# ③ Use-case stacks (any order among themselves)
aws cloudformation delete-stack --stack-name edge-to-cloud-visual-inspection-poc
aws cloudformation delete-stack --stack-name edge-to-cloud-print-quality-poc
aws cloudformation delete-stack --stack-name edge-to-cloud-telemetry-poc

# Wait for completion
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-visual-inspection-poc
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-print-quality-poc
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-telemetry-poc

# ② Ingestion stack
aws cloudformation delete-stack --stack-name edge-to-cloud-ai-poc
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-ai-poc

# ① FSx for ONTAP stack (only if deployed)
aws cloudformation delete-stack --stack-name edge-to-cloud-fsxn-poc
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-fsxn-poc
```

> **Note**: The S3 bucket (`DataLakeBucket`) has `DeletionPolicy: Retain` and will persist after stack deletion. Remove it manually:
> ```bash
> aws s3 rb s3://edge-to-cloud-ai-poc-<ACCOUNT_ID> --force
> ```

---

## Related Documents

- [cfn-params/README.md](../../cfn-params/README.md) — Parameter file usage
- [cloud/fsxn/README.md](../../cloud/fsxn/README.md) — FSx for ONTAP configuration details
- [docs/en/security-design.md](./security-design.md) — Security design
- [docs/en/operations-design.md](./operations-design.md) — Operations design
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — Contribution guide
