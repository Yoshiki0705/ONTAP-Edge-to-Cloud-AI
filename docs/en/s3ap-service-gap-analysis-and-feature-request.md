> 🌐 Language: [日本語](../ja/s3ap-service-gap-analysis-and-feature-request.md) | **English**

# S3 Access Points (FSx for ONTAP) — IoT/Edge Service Gap Analysis & Feature Request

> Created: 2026-07-27
> Project: edge-to-cloud-ai
> Purpose: Identify AWS IoT/edge services that support S3 standard buckets but NOT S3 Access Points (especially FSx for ONTAP S3 AP), and prepare feature requests for AWS Support

---

## 1. Gap Analysis Results

### 1.1 Service Compatibility Matrix

| # | Service | S3 Standard Bucket | S3 AP ARN | S3 AP Alias | Notes |
|---|---------|:---:|:---:|:---:|------|
| 1 | **AWS IoT Greengrass Stream Manager** | ✅ (S3 Export destination) | ❌ | Unverified | S3ExportTaskDefinition requires bucketName. ARN format not accepted |
| 2 | **Amazon Data Firehose** | ✅ (S3 Destination) | ❌ | Unverified | ExtendedS3DestinationConfiguration BucketARN only accepts `arn:aws:s3:::example-bucket` format |
| 3 | **AWS IoT Core Rules Engine (S3 Action)** | ✅ (bucket parameter) | ❌ | Unverified | S3 rule action requires `bucket` (bucket name string) |
| 4 | **AWS IoT SiteWise (Cold Tier Storage)** | ✅ (S3 bucket specified) | ❌ | Unverified | `put-storage-configuration` `s3ResourceArn` accepts S3 bucket ARN only |
| 5 | **AWS IoT SiteWise (Buffered Destination)** | ✅ (S3 bucket) | ❌ | Unverified | Edge data temporary buffer specifies S3 bucket |
| 6 | **AWS IoT SiteWise (Bulk Export)** | ✅ (S3 bucket) | ❌ | Unverified | Asset model/data bulk export destination is S3 bucket |

### 1.2 S3 AP Alias Workaround Feasibility

AWS announced [S3 Access Points Aliases](https://aws.amazon.com/about-aws/whats-new/2021/07/amazon-s3-access-points-aliases-allow-application-requires-s3-bucket-name-easily-use-access-point/) in 2021, allowing some applications that require bucket names to use AP Aliases instead. However:

- **FSx for ONTAP S3 AP Alias format is `{ap-name}-{random}-s3alias`** — some services may reject this in bucket name validation
- **Alias is NOT guaranteed to work across all services** — AWS docs confirm compatibility with "Amazon EMR, Amazon Storage Gateway, and Amazon Athena". IoT service compatibility is unverified
- **FSx for ONTAP S3 AP supports a subset of S3 APIs only** — PutObject, GetObject, ListObjectsV2, DeleteObject, etc.

### 1.3 Impact Scope

| Affected Architecture Pattern | Workaround | Workaround Downsides |
|------------------------------|------------|---------------------|
| Greengrass → direct FSx for ONTAP data ingest | Custom component with boto3 PutObject | Stream Manager's managed offline buffer/retry/bandwidth control unavailable |
| IoT Core telemetry → direct FSx for ONTAP storage | Lambda rule action intermediary | Added Lambda cost + cold start latency |
| Firehose Parquet conversion → direct FSx for ONTAP delivery | Lambda aggregation + PutObject, or S3 bucket intermediary | Firehose's managed Parquet/buffering features unavailable |
| SiteWise time-series → direct FSx for ONTAP storage | S3 bucket + DataSync | Double storage, increased latency |

---

## 2. AWS Support Feature Request Drafts

### Case 1: AWS IoT Greengrass Stream Manager — S3 Access Points Support

**Subject**: Feature Request — S3 Access Points (FSx for ONTAP) support in Stream Manager S3 Export

**Current Behavior**: Stream Manager S3ExportTaskDefinition accepts only S3 bucket name (`bucket`). S3 Access Point ARN cannot be specified.

**Requested Behavior**: Allow S3 AP ARN as S3 Export destination in Stream Manager.

**Business Impact**:
- IoT workloads generate millions of small files (1KB-1MB) → S3 PUT billing is substantial
- FSx for ONTAP eliminates per-API-call charges (capacity-billed) and provides inline dedup/compression
- Without S3 AP support, must reimplement Stream Manager's offline buffer, retry, multipart upload management
- Estimated 40-60% storage efficiency improvement with ONTAP for IoT small file patterns
- FlexCache enables multi-site low-latency data delivery without additional data copies

**Use Cases**:
1. Manufacturing quality inspection: Camera → Stream Manager → FSx for ONTAP S3 AP → Bedrock Vision analysis
2. Predictive maintenance: Sensor Parquet batches → FSx for ONTAP → SageMaker training via S3 AP
3. Edge AI model delivery: Origin models → FlexCache → NFS to edge GPU devices

---

### Case 2: Amazon Data Firehose — S3 Access Points Support

**Subject**: Feature Request — S3 Access Points (FSx for ONTAP) as Firehose delivery destination

**Current Behavior**: Firehose S3 Destination (`BucketARN`) only accepts `arn:aws:s3:::example-bucket` format.

**Requested Behavior**: Accept S3 Access Point ARN as delivery destination.

**Business Impact**:
- IoT Core → Firehose → S3 is the standard IoT data lake pattern
- When FSx for ONTAP is the data platform, S3 bucket becomes unnecessary intermediary
- 100+ devices × 1msg/sec × 30 days = ~260M messages. S3 PUT + DataSync + FSx storage = 3-layer cost
- Direct Firehose → FSx for ONTAP S3 AP would eliminate S3 layer → ~50% storage cost reduction

---

### Case 3: AWS IoT Core Rules Engine S3 Action — S3 Access Points Support

**Subject**: Feature Request — S3 Access Points (FSx for ONTAP) in IoT Core S3 rule action

**Current Behavior**: S3 rule action `bucket` parameter accepts bucket name string only.

**Requested Behavior**: Accept S3 AP ARN or Alias in the destination parameter.

**Business Impact**:
- Eliminates need for Lambda intermediary → saves Lambda invocation costs
- 100 devices × 1msg/sec = 86,400 Lambda invocations/day that could be $0 with native S3 AP support
- Simplifies architecture: IoT Core → S3 AP → FSx for ONTAP (no Lambda, no S3 bucket)

---

### Case 4: AWS IoT SiteWise — Cold Tier / Buffered Destination / Bulk Export S3 AP Support

**Subject**: Feature Request — S3 Access Points (FSx for ONTAP) for SiteWise storage/export

**Current Behavior**: All three features (Cold Tier, Buffered Destination, Bulk Export) accept S3 bucket ARN only.

**Requested Behavior**: Accept S3 AP ARN for all storage/export destination configurations.

**Business Impact**:
- Manufacturing OPC-UA time-series data and file data (images/docs) unified on single FSx for ONTAP volume
- FlexCache delivers OT data to other factory engineering teams without additional data pipeline
- Eliminates S3 → DataSync → FSx for ONTAP hop for cold tier data

---

## 3. Submission Process

### Recommended Steps

1. **AWS Support Center** → Create case → Technical support → General guidance
2. **Title format**: `Feature Request — S3 Access Points (FSx for ONTAP) support in [Service]`
3. **Include**: Current behavior, requested behavior, quantified business impact, multiple use cases, workaround limitations
4. **Supplement with**: Architecture diagrams, region/version info, related resource ARNs

### Priority Order

| Priority | Service | Rationale |
|----------|---------|-----------|
| 1 | Amazon Data Firehose | Most common IoT data lake pipeline. Broadest impact |
| 2 | IoT Core S3 Rule Action | Basic serverless IoT pattern. Immediate cost savings via Lambda elimination |
| 3 | Greengrass Stream Manager | Core edge write feature. Offline buffer difficult to self-implement |
| 4 | IoT SiteWise | Manufacturing-specific but critical for OT/IT convergence |

### Escalation Paths

- **TAM/Account Manager**: Direct service team feedback (Enterprise Support)
- **AWS re:Post**: Public discussion for community upvotes
- **GitHub roadmaps**: Create issues on relevant public roadmaps

---

## 4. Verification Plan: S3 AP Alias Testing

Parallel to feature requests, verify whether S3 AP Alias works as a "bucket name" substitute in these services.

| Test | Method | Expected |
|------|--------|----------|
| Greengrass Stream Manager + AP Alias | Set AP Alias in `bucket` field | Validation pass or error |
| IoT Core S3 Action + AP Alias | Set AP Alias in rule `bucket` | Validation pass or error |
| Firehose + AP Alias | Set `arn:aws:s3:::{alias}` in BucketARN | Delivery success or error |
| SiteWise + AP Alias | Set Alias-format ARN in s3ResourceArn | Configuration success or error |

Results should be appended to support cases to reinforce the feature request justification.

---

## Related Documents

- [IoT Greengrass + FlexCache Integration Scenarios](./iot-greengrass-flexcache-integration.md)
- [S3 AP + FlexCache / SnapMirror Design Considerations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/blob/main/docs/en/s3ap-flexcache-snapmirror-considerations.md)
