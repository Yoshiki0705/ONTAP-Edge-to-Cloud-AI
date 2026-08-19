> 🌐 Language: [日本語](../ja/s3ap-compatibility-matrix.md) | **English**

# FSx for ONTAP S3 Access Points — Compatibility and Constraints

> Last verified: 2026-08-19

## What this document is for

A single place recording **what works and what does not** with S3 access points (S3 AP)
attached to FSx for ONTAP volumes. Other documents link here instead of restating
constraints.

Every entry carries the basis for the claim.

| Basis | Meaning |
|-------|---------|
| **Documented** | Stated in AWS documentation, with the URL |
| **Project-tested** | Result from testing in a related project, with the date |
| **Unverified** | Confirmed by neither. Check it in your own environment |

---

## 1. AWS services usable through an S3 access point

Services for which AWS publishes an integration walkthrough.

| Service | Use | Basis |
|---------|-----|-------|
| Amazon Athena | SQL queries via the Glue Data Catalog | Documented |
| AWS Lambda | Serverless processing of files on the volume | Documented |
| AWS Glue | ETL with Spark, Python shell or Ray, writing results back to the same volume | Documented |
| Amazon Bedrock Knowledge Bases | RAG grounded in documents on the volume | Documented |
| Amazon EMR Serverless | PySpark and Spark SQL | Documented |
| Amazon CloudFront | HLS video delivery | Documented |
| AWS Transfer Family | Expose the volume externally as an SFTP, FTPS or FTP endpoint | Documented |

Source: [Using access points with AWS services](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html), which links each tutorial.

Bedrock Knowledge Bases takes the **access point alias** as its data source, accepting
the alias in place of a bucket name.
Source: [Build a RAG application using Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)

> **Note**: the Bedrock-side documentation for S3 data sources states that only general
> purpose S3 buckets are supported, while the FSx for ONTAP guide gives the alias-based
> procedure ([Bedrock-side page](https://docs.aws.amazon.com/bedrock/latest/userguide/s3-data-source-connector.html)).
> Follow the FSx for ONTAP guide when building.

For Athena, the access point needs an **internet** network origin, and query results are
written to an S3 bucket rather than to the FSx for ONTAP volume.
Source: [Query files with SQL using Amazon Athena](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html)

---

## 2. Prerequisites and structural constraints

Constraints specific to FSx for ONTAP that do not apply to access points on S3 buckets.

| Constraint | Detail | Basis |
|------------|--------|-------|
| ONTAP version | Can only be created on and attached to file systems running **9.17.1 or later** | Documented |
| Region | The access point must be in the same Region as the volume | Documented |
| Account | The same AWS account must own the file system and the access point; you cannot attach to a volume owned by another account | Documented |
| Volume | Attachable only to a mounted volume, meaning one with a junction path. This applies to DP volumes too | Documented |
| Public access | Block public access is enforced by default and cannot be disabled | Documented |
| Naming | An access point name cannot end in `-ext-s3alias`, which is reserved for the alias | Documented |

Sources: [Access points naming rules, restrictions, and limitations](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-point-for-fsxn-restrictions-limitations-naming-rules.html) /
[Creating access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-access-points.html) /
[Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)

### Authorization is evaluated in two layers

A request has to pass both S3 and the file system.

1. S3 evaluates the caller's IAM policies, the access point resource policy, VPC endpoint
   policies and service control policies
2. A request that passes is re-evaluated by the file system against the permissions of the
   UNIX or Windows user associated with the access point

An IAM allow is therefore not sufficient: if that file system user has no permission on the
file, the request is denied. The file system user identity is specified when the access
point is created.

Source: [Managing access point access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)

### Permissions needed to create one

`fsx:CreateAndAttachS3AccessPoint`, `s3:CreateAccessPoint` and `s3:GetAccessPoint`, plus
`s3:PutAccessPointPolicy` if a policy is created at the same time.
Source: [Creating an access point](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/fsxn-creating-access-points.html)

---

## 3. Data operation constraints

Constraints tested in a related project
([fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations)),
tested in May 2026.

| Constraint | Impact | Workaround | Basis |
|------------|--------|-----------|-------|
| No conditional writes (If-None-Match) | Delta Lake, Iceberg and Hudi transactional writes do not work | Read-only analytics, or write on the S3 side | Project-tested |
| No S3 event notifications | No object-created event to trigger ingestion | FPolicy → Lambda, scheduled polling, ONTAP REST API | Project-tested |
| No SnapMirror S3 | No replication from an ONTAP S3 bucket to S3 | AWS DataSync (NFS → S3) | Project-tested |
| ListObjectsV2 latency | Slower than native S3 on small directories | Pre-generate file lists, use larger files, cache results | Project-tested |
| SSE-FSX only | SSE-S3, SSE-KMS and SSE-C are unavailable | Use the default SSE-FSX | Project-tested |
| No object versioning | S3 versioning is unavailable | ONTAP Snapshot | Project-tested |
| Presigned URLs | Support is not stated in the documentation | Use IAM-based access on paths that matter | Unverified |

For the exhaustive list of supported S3 API operations, see
[Access point compatibility](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-service-api-support.html).
Files reached through an S3 AP return a `StorageClass` of `FSX_ONTAP`
([source](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-usage-examples.html)).

> **On numbers**: "slower" above carries no multiplier. The related project records one,
> but its measurement environment — ONTAP version, file count, directory shape, throughput
> capacity — differs from this one, so quoting it here would misrepresent it. Measure in
> your own configuration.

---

## 4. Services that require an S3 bucket name

Services observed to require an S3 bucket name or bucket ARN as their destination and not
to accept an access point ARN. **None of these has been tested in this project.**

| Service | Format required | Basis |
|---------|-----------------|-------|
| AWS IoT Greengrass Stream Manager | `bucket` in `S3ExportTaskDefinition` (a bucket name) | Unverified |
| Amazon Data Firehose | `BucketARN` in `ExtendedS3DestinationConfiguration` | Unverified |
| AWS IoT Core rules engine S3 action | `bucket` (a bucket name) | Unverified |
| AWS IoT SiteWise Cold Tier Storage | `s3ResourceArn` in `put-storage-configuration` | Unverified |
| AWS IoT SiteWise Buffered Destination | An S3 bucket | Unverified |
| AWS IoT SiteWise Bulk Export | An S3 bucket | Unverified |

> **How to read "unverified"**: this is not a claim that they do not work. It records that
> no statement about accepting an access point ARN was found in each service's
> documentation and that this project has not tried it. Confirm before relying on it for a
> design decision.

### Whether the alias works around it

AWS introduced the
[access point alias](https://aws.amazon.com/about-aws/whats-new/2021/07/amazon-s3-access-points-aliases-allow-application-requires-s3-bucket-name-easily-use-access-point/)
in 2021 for applications that require an S3 bucket name.

- Bedrock Knowledge Bases accepts the alias in place of a bucket name (**documented**, §1)
- Whether the alias passes for the six services above is **unverified**
- The alias ends in `-ext-s3alias`; whether it survives a service's bucket-name validation
  depends on that service's implementation

---

## 5. Affected designs and alternative paths

| Design | Alternative path | Constraint of the alternative |
|--------|------------------|-------------------------------|
| Greengrass sending directly to an S3 AP | A custom component calling boto3 PutObject | Offline buffering, retry, bandwidth control and multipart management have to be written by hand instead of using Stream Manager |
| IoT Core telemetry stored directly on an S3 AP | Via a Lambda rule action | Adds Lambda invocation cost and latency |
| Firehose Parquet conversion delivered to an S3 AP | Aggregate in Lambda and PutObject, or materialize into an Iceberg table with MSK Express brokers streaming tables | Firehose's managed conversion and buffering are unavailable |
| SiteWise time series stored on an S3 AP | Via an S3 bucket plus DataSync | Two copies of the data, and added delay |
| Handing files to external partners | AWS Transfer Family over an S3 AP (**documented**) | — |

---

## 6. Open items

Not confirmed in this project. Remove a row once it is.

| # | Item | How to confirm |
|---|------|----------------|
| 1 | Whether an access point ARN or alias passes for the six services in §4 | Configure each and record the result |
| 2 | How presigned URLs behave | Look for a statement in the documentation; measure if there is none |
| 3 | Whether an S3 AP can be registered as a Unity Catalog external location | Attempt the registration (see [Databricks integration](./databricks-integration.md)) |
| 4 | ListObjectsV2 latency in this configuration | Measure locally and record the conditions alongside the number |

---

## Related documents

- [IoT Greengrass + FlexCache integration](./iot-greengrass-flexcache-integration.md) — write paths and FlexCache
- [Databricks integration design](./databricks-integration.md) — Unity Catalog connection paths
- [Deployment guide](./deployment-guide.md) — actual build steps
- [AWS pattern catalog](./aws-patterns/README.md) — how these constraints bear on each design
- [FAQ](./faq.md)
