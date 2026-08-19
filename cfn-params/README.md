# CloudFormation Parameter Files

Parameter files in the standard `--parameters` JSON array format for `aws cloudformation create-stack` / `update-stack`.

## Usage

These files are the single place parameter values live. `usecases/*/params/poc.json` used to
hold byte-identical copies of three of them; that directory is gone, because two files with
the same content are one file that gets updated and one that does not.

Both commands accept them, in the same JSON array format:

```bash
# create-stack / update-stack
aws cloudformation create-stack \
  --template-body file://cloud/fsxn/template.yaml \
  --stack-name edge-to-cloud-fsxn-poc \
  --parameters file://cfn-params/fsxn.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# deploy — file:// works here too
aws cloudformation deploy \
  --template-file cloud/fsxn/template.yaml \
  --stack-name edge-to-cloud-fsxn-poc \
  --parameter-overrides file://cfn-params/fsxn.example.json \
  --capabilities CAPABILITY_NAMED_IAM
```

> **Correction**: this file previously stated that `deploy --parameter-overrides` does
> **not** accept `file://`, and told readers to convert every value to `Key=Value` by hand.
> That is wrong for AWS CLI v2. Verified against `aws-cli/2.36.5`: `aws cloudformation
> deploy help` documents three accepted JSON shapes for `--parameter-overrides`, including
> the `[{"ParameterKey": …, "ParameterValue": …}]` form used here. The claim also
> contradicted the deploy commands in the use-case guides, which have always passed
> `file://`. It may have held for AWS CLI v1; it does not hold for the version this
> repository documents.

One constraint from the same help text is real and worth keeping: only `ParameterKey` and
`ParameterValue` are accepted inside each entry. `UsePreviousValue` or `ResolvedValue` make
the command throw. `scripts/check_cfn_params_contract.py` checks that, along with the keys
matching the template's declared parameters.

## Files

| File | Template | Description |
|------|----------|-------------|
| `fsxn.example.json` | `cloud/fsxn/template.yaml` | VPC + FSx for ONTAP file system |
| `ingestion.example.json` | `cloud/ingestion/template.yaml` | S3 data lake, Kinesis, IAM roles |
| `iot-ingestion.example.json` | `cloud/iot_ingestion/template.yaml` | AWS IoT Core rule + ingestion Lambda |
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
