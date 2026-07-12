# CloudFormation Parameter Files

Parameter files in the standard `--parameters` JSON array format for `aws cloudformation create-stack` / `update-stack`.

## Usage

```bash
# create-stack (uses --parameters with JSON file)
aws cloudformation create-stack \
  --template-body file://cloud/fsxn/template.yaml \
  --stack-name edge-to-cloud-fsxn-poc \
  --parameters file://cfn-params/fsxn.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# deploy (uses --parameter-overrides with Key=Value pairs — NOT file://)
# NOTE: `deploy` does NOT accept file:// for parameter-overrides.
# Instead, convert to Key=Value format:
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
  --capabilities CAPABILITY_NAMED_IAM
```

> **Important**: `aws cloudformation deploy --parameter-overrides` only accepts `Key=Value` pairs, not `file://`. The JSON files here are for `create-stack --parameters` or `update-stack --parameters`.

## Files

| File | Template | Description |
|------|----------|-------------|
| `fsxn.example.json` | `cloud/fsxn/template.yaml` | VPC + FSx for ONTAP file system |
| `ingestion.example.json` | `cloud/ingestion/template.yaml` | S3 data lake, Kinesis, IAM roles |
| `ontap-telemetry-analytics.example.json` | `usecases/ontap-telemetry-analytics/template.yaml` | Glue crawler + CloudWatch alarms |
| `3d-print-quality.example.json` | `usecases/3d-print-quality/template.yaml` | Image analysis Lambda + alarms |
| `visual-inspection.example.json` | `usecases/visual-inspection/template.yaml` | Visual inspection Lambda + alarms |

## Customization

1. Copy the `.example.json` file to a local name (e.g., `fsxn.local.json`)
2. Edit parameter values for your environment
3. Files matching `*.local.json` are gitignored

## Deployment Order

```
1. cloud/fsxn/template.yaml          (optional — only if FSx for ONTAP needed)
2. cloud/ingestion/template.yaml     (shared infra — required)
3. usecases/*/template.yaml          (any use case — depends on #2)
```
