> 🌐 Language: [日本語](../ja/flexible-ai-data-layer.md) | **English**

# Flexible AI Data Layer Patterns

> Last verified: 2026-08-19

Configurations for keeping the data layer an AI reads in a shape that any engine can read.
**What works today, what is in preview, and what is only an outline are not mixed.**

## Availability labels

Every item carries a label. Statements without one do not belong in this document.

| Label | Meaning | Obligation when writing |
|-------|---------|-------------------------|
| **Supported today** | Documented as generally available | Include the URL |
| **Public preview** | Explicitly stated as preview by AWS | URL plus a note that it is preview |
| **Conceptual** | An outline with no documented basis | Say it is an outline; do not assert how it would work |

**No performance figures or cost reduction percentages appear in this document.** Nothing here is
measured, so writing them would mislead.

## 1. File storage as the AI data layer

**Supported today.** Data on a file share is reachable over the S3 API without making a copy. The
AWS services usable this way are listed officially
([source](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)).

| What is possible | Availability | Source |
|---|---|---|
| SQL queries via the Glue Data Catalog | Supported today | [Athena tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html) |
| ETL (read, transform, write back to the same volume) | Supported today | [Glue tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html) |
| A RAG data source | Supported today | [Knowledge Bases tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html) |
| Spark workloads | Supported today | The list above |
| File handover over SFTP / FTPS | Supported today | [Transfer Family](https://docs.aws.amazon.com/en_us/transfer/latest/userguide/fsx-s3-access-points.html) |
| Video delivery | Supported today | The list above |

**The constraints are equally facts about today.** Because conditional writes are unsupported,
Iceberg or Delta tables cannot be placed on this layer and updated
([constraint list](s3ap-compatibility-matrix.md)). **That single point separates the sections that
follow.**

## 2. Open table formats

Do not talk about "Iceberg" as one thing. What is possible changes with the specification version and
with whether a managed offering is involved.

| Item | Availability | Source |
|---|---|---|
| Iceberg tables on object storage, read by several engines | Supported today | — |
| S3 Tables (a table bucket with built-in Iceberg support) | Supported today | [source](https://docs.aws.amazon.com/sagemaker-lakehouse-architecture/latest/userguide/lakehouse-s3-tables-integration.html) |
| Iceberg V3 deletion vectors and row lineage (Glue Data Catalog) | Supported today | [source](https://aws.amazon.com/sagemaker/lakehouse/features/) |
| The Iceberg V3 Variant type (S3 Tables) | Supported today | [source](https://aws.amazon.com/about-aws/whats-new/2026/07/amazon-s3-tables-variant-iceberg-v3/) |
| Continuously materialising a Kafka topic as an Iceberg table | Supported today | [MSK Express brokers](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables-streaming-msk.html) |
| Placing an Iceberg table directly on file storage and updating it | **Not possible** (no conditional writes) | [constraint list](s3ap-compatibility-matrix.md) |

**What follows for this architecture**: table-format data goes on the object storage side, while file
storage holds the originals — images, documents, waveforms. Both are read the same way over the S3
API.

## 3. Catalog interoperability

**This is about freedom to choose an engine, not about one platform being better.**

Between catalogs that implement the Iceberg REST specification, federation is emerging in which one
catalog's tables can be read and written from another.

| Item | Availability | Source |
|---|---|---|
| Reading from an external engine following the Iceberg REST specification | Supported today (depends on each catalog's implementation) | [Snowflake's account](https://www.snowflake.com/en/blog/engineering/snowflake-horizon-vs-databricks-unity-catalog-comparison/) |
| Writing to an Iceberg table managed by an external catalog | Supported today (per the provider's documentation) | [writes to externally managed tables](https://docs.snowflake.com/user-guide/tables-iceberg-externally-managed-writes) |
| Bidirectional federation between catalogs | Supported today (a procedure is published) | [bidirectional access tutorial](https://docs.snowflake.com/en/user-guide/tutorials/tables-iceberg-set-up-bidirectional-access-to-unity-catalog) |

**Choosing** follows from which engine does what. Stated symmetrically.

| Condition | Shape that suits | Trade-off |
|---|---|---|
| One engine covers everything | Consolidate onto one catalog | Adding an engine later requires migration |
| Several engines read the same data | Federation over Iceberg REST | Differences in permission models between catalogs are absorbed operationally |
| The engine may change in future | An open format plus an external catalog | Cannot rely on feature parity between catalogs |

**Where this repository stands**: whether an S3 access point can be registered as a Unity Catalog
external location is **unverified** ([databricks-integration](databricks-integration.md)). That
verdict decides between reading from file storage directly and going through an export.

## 4. Hybrid inference

Distributing inference between the edge and the cloud.

| Item | Availability | Source |
|---|---|---|
| ML inference at the edge, executing on the device | Supported today | [Greengrass ML inference](https://docs.aws.amazon.com/greengrass/v2/developerguide/perform-machine-learning-inference.html) |
| Distributing agents to a device fleet with local small models | Supported today (guidance published) | [source](https://docs.aws.amazon.com/solutions/deploying-ai-agents-to-device-fleets-using-aws-iot-greengrass/) |
| Hybrid inference spanning storage systems | Supported today (worked configuration published) | [source](https://aws.amazon.com/blogs/storage/hybrid-ml-inferencing-on-amazon-eks-with-amazon-fsx-for-netapp-ontap-and-on-premises-netapp/) |
| RAG under data residency requirements | Supported today (worked configuration published) | [source](https://aws.amazon.com/blogs/machine-learning/implement-rag-while-meeting-data-residency-requirements-using-aws-hybrid-and-edge-services/) |
| Automatically routing by estimated input difficulty | **Conceptual** | Studied in the literature ([survey](https://arxiv.org/html/2507.16731v1)), but neither implemented nor verified in this architecture |

**Four axes** decide it, detailed in [Pattern 09](aws-patterns/09-edge-agentic-ai.md): latency, data
sensitivity, model capability, cost. **Cut on sensitivity first.** The other three can be closed by
adjustment; sensitivity cannot.

## 5. Edge-to-cloud synchronization

**Synchronization has two axes.** Blurring them breaks the design.

| Axis | What it carries | Example mechanisms | Availability |
|---|---|---|---|
| File and block sync | The bytes of images, documents, waveforms | FlexCache, SnapMirror, DataSync | Supported today |
| Event stream sync | Metadata about when something happened | MQTT, Kafka | Supported today |

The two are designed independently. Payload over file sync, events over a stream, is how this
repository is arranged ([README](../../README_en.md)).

**Either alone is insufficient.** File sync alone gives no way to know what arrived; events alone
never carry the bytes.

Configurations that commit edge writes locally carry version requirements and a production caveat
([FlexCache write-back](iot-greengrass-flexcache-integration.md)).

## 6. Configurations that remain outlines

**The following are Conceptual. They are not written as generally available features.**

| Outline | Why it is Conceptual |
|---|---|
| Managing data on file storage from several catalogs at once, without copying | Conditional writes are unavailable, so table-format management cannot sit on this layer (§1) |
| Routing inference requests automatically between edge and cloud | The axes can be organised, but there is no implementation in this architecture (§4) |
| Reconciling agent memory with the source of truth automatically | Not designed ([Agentic AI on AWS](agentic-ai-on-aws.md) §7) |
| Generating catalog schemas from the OT namespace | The namespace design itself is unimplemented ([Pattern 08](aws-patterns/08-unified-namespace.md)) |

## 7. Open items

| Item | What it affects |
|---|---|
| Whether an S3 access point can be a Unity Catalog external location | The shape of §3 |
| ListObjectsV2 latency in this configuration | Crawl performance in §1 |
| How block-granularity FlexCache caching behaves for model delivery | The delivery shape in §4 |
| Differences in permission models across federated catalogs | Operational load in §3 |

## References

- [Using access points with AWS services](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)
- [S3 Tables in the SageMaker lakehouse architecture](https://docs.aws.amazon.com/sagemaker-lakehouse-architecture/latest/userguide/lakehouse-s3-tables-integration.html)
- [Streaming tables with Amazon MSK](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables-streaming-msk.html)
- [Hybrid ML inferencing with FSx for ONTAP and on-premises NetApp](https://aws.amazon.com/blogs/storage/hybrid-ml-inferencing-on-amazon-eks-with-amazon-fsx-for-netapp-ontap-and-on-premises-netapp/)
- Related: [pattern catalog](aws-patterns/README.md) /
  [Agentic AI on AWS](agentic-ai-on-aws.md) /
  [S3 AP compatibility and constraints](s3ap-compatibility-matrix.md)
