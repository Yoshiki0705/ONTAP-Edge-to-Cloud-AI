> 🌐 Language: [日本語](../../ja/aws-patterns/README.md) | **English**

# AWS pattern catalog

> Last verified: 2026-08-19

Nine designs for connecting data produced at the edge to AWS analytics and AI services, written to
the same shape. Pick the one closest to your requirements, then read its assumptions and
constraints before adopting it.

## How to read these

Each pattern opens with a **maturity** label. Three values.

| Label | Meaning |
|-------|---------|
| **Implemented** | Deployable code exists in this repository. Which stages of the path have code is stated in each document's implementation table |
| **Design only** | The design is written but no code exists here. Where AWS publishes a walkthrough, that is stated |
| **Concept** | An outline only, including parts with no documented basis |

**This catalog carries no monetary figures.** It names what drives cost and leaves the estimates in
the [deployment guide](../deployment-guide.md). It carries no unmeasured performance figures either.

## The patterns

| # | Pattern | Path | Maturity |
|---|---------|------|----------|
| [01](01-edge-ai-bedrock.md) | Edge AI + Amazon Bedrock | Edge → local storage → FSx for ONTAP → Bedrock → agentic workflow | Implemented (partly) |
| [02](02-edge-ai-sagemaker.md) | Edge AI + SageMaker | Edge cameras → ONTAP → FSx for ONTAP → SageMaker training → inference | Design only |
| [03](03-industrial-iot-analytics.md) | Industrial IoT analytics | Sensors → Kafka → MSK → data lake → Glue → Athena | Implemented (partly) |
| [04](04-near-realtime-manufacturing.md) | Near real-time manufacturing analytics | Kafka → ClickHouse → object storage → Databricks | Implemented (partly) |
| [05](05-agentic-rag.md) | Agentic RAG | Documents → ONTAP → FSx for ONTAP → Bedrock Knowledge Bases → retrieval | Design only (official walkthrough) |
| [06](06-video-analytics.md) | Video analytics | Edge cameras → ONTAP → FSx for ONTAP → Rekognition → OpenSearch | Design only |
| [07](07-digital-twin.md) | Digital twin | IoT devices → IoT Core → time-series database → Bedrock → visualization | Implemented (partly) |
| [08](08-unified-namespace.md) | Unified namespace / industrial data fabric | OT equipment → a single message bus → cloud | Design only |
| [09](09-edge-agentic-ai.md) | Edge agentic AI | Device fleet → local SLM → escalation to a cloud LLM | Design only (official guidance) |

## How to choose

The decision follows from what you want to solve first.

| What you want first | Patterns to read |
|---|---|
| A quality verdict from an image | [01](01-edge-ai-bedrock.md) (generative AI) / [02](02-edge-ai-sagemaker.md) (train your own model) / [06](06-video-analytics.md) (video and search) |
| Sensor data stored and queried with SQL | [03](03-industrial-iot-analytics.md) |
| Dashboard latency in seconds | [04](04-near-realtime-manufacturing.md) |
| Existing document assets available to an AI | [05](05-agentic-rag.md) |
| Equipment state as a time series, with generated explanations | [07](07-digital-twin.md) |
| OT data scattered per device, needing a namespace first | [08](08-unified-namespace.md) |
| Decisions made at the edge because the network is unreliable | [09](09-edge-agentic-ai.md) |

**Order of reading**: [08](08-unified-namespace.md) is worth reading first only when collection
itself is not in place. If data already lands somewhere, 01 or 03 gets something running sooner.

## Assumptions that cut across all patterns

Common constraints, not repeated in each document.

- **S3 access point constraints**: no conditional writes, no event notifications, no object
  versioning; ONTAP 9.17.1 or later; same Region, same account, junction path required. The list
  and its basis are in [S3 AP compatibility and constraints](../s3ap-compatibility-matrix.md)
- **Security controls**: IAM, network isolation, encryption and audit are collected in the
  [security design](../security-design.md)
- **Event schema**: [data schema design](../data-schema-design.md)
- **Design questions for agentic workflows**: [Agentic AI on AWS](../agentic-ai-on-aws.md)
- **Candidate future configurations**: [Flexible AI Data Layer](../flexible-ai-data-layer.md)

## Mapping to the repository layout

This catalog holds designs. What runs lives here.

| What you are looking for | Location |
|---|---|
| CloudFormation / SAM templates | [`cloud/`](../../../cloud/) — shared infrastructure, FSx for ONTAP, IoT ingestion, AI |
| Deployable use cases | [`usecases/`](../../../usecases/) |
| Edge code | [`edge/`](../../../edge/) |
| ClickHouse schema | [`cloud/clickhouse/ddl/`](../../../cloud/clickhouse/ddl/) |
| A demo that runs with no physical hardware | [`local-demo/`](../../../local-demo/) |
| Terraform | Not implemented. A roadmap item |

## Open items

Also stated in each pattern's constraints; collected here where they cut across.

| Item | Patterns affected |
|---|---|
| Whether Greengrass Stream Manager, Data Firehose, the IoT Core S3 action or SiteWise accept an S3 access point | 01, 03, 07, 08 |
| Whether an S3 access point can be registered as a Unity Catalog external location | 04 |
| How block-granularity FlexCache caching behaves for model delivery | 02, 09 |
| ListObjectsV2 latency in this configuration | 03, 05, 06 |
