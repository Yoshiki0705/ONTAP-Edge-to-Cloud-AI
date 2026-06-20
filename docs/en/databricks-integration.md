# Databricks Integration Design

> Created: 2026-06-15
> Status: Design Complete (synchronized with Lakehouse project)
> Related: [fsxn-lakehouse-integrations/poc-templates/04-databricks-integration](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/tree/main/poc-templates/04-databricks-integration)
> Edge ↔ Lakehouse sync record: [14_edge_lakehouse_sync.md](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/blob/main/integrations/manufacturing-data-platform/docs/en/14_edge_lakehouse_sync.md) — Schema / topic / responsibility-matrix sync status

---

## 1. Overview

Integration design for using edge-collected data as AI/ML training datasets in Databricks Lakehouse.

**Constraint**: Unity Catalog cannot directly access FSx for ONTAP S3 Access Points (session policy limitation). Multiple alternative paths are designed.

---

## 2. Data Connection Paths

### 2.1 Path Summary

| # | Path | Data Type | Real-time | Use Case |
|---|------|-----------|-----------|----------|
| A | Kafka → Spark Structured Streaming → Delta | Events (JSON) | Seconds~Minutes † | Bronze table direct ingestion |
| B | ClickHouse → Parquet Export → ONTAP S3 → DataSync → S3 → UC | Aggregated features | Hours (batch) | Silver/Gold tables |
| C | ONTAP NFS → DataSync → S3 → Auto Loader → UC | Raw images, CSV | Minutes~Hours | Raw data long-term storage/analysis |
| D | Kafka → Lakebase (LTAP) | Events (JSON) | Milliseconds~Seconds | Operational DB + analytics convergence (future candidate) |

> † Path A latency can be reduced to ~5ms with Real-Time Mode for SDP (GA). See section 2.6.

### 2.2 Path A: Kafka → Structured Streaming → Delta (Recommended: Real-time)

```
[Edge Pi]                   [Kafka]              [Databricks]
simple_capture.py  -event-> factory.events.raw -> Spark Structured Streaming
                                                      |
                                                      v
                                                 bronze.sensor_events (Delta)
                                                 bronze.quality_events (Delta)
                                                 bronze.payload_manifest (Delta)
```

**Databricks notebook example**:

```python
# Bronze: Kafka -> Delta (Structured Streaming)
from pyspark.sql import functions as F

kafka_df = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "<KAFKA_BROKER>:9092")
    .option("subscribe", "factory.events.raw")
    .option("startingOffsets", "latest")
    .load()
)

# Parse JSON payload
parsed_df = (
    kafka_df
    .select(F.from_json(F.col("value").cast("string"), event_schema).alias("event"))
    .select("event.*")
    .withColumn("_ingested_at", F.current_timestamp())
)

# Write to Bronze Delta table
(
    parsed_df.writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", "/mnt/checkpoints/bronze_events")
    .toTable("manufacturing_poc.bronze.kafka_events")
)
```

### 2.3 Path B: ClickHouse Export → Databricks (Batch, ML features)

```
[ClickHouse]                             [ONTAP S3]           [S3]          [Databricks]
training_features_export  -Parquet->  clickhouse-export/  -DataSync->  s3://bucket/  -UC-> silver.training_features
```

**ClickHouse export**:

```sql
-- ClickHouse: Export training features as Parquet to ONTAP S3
INSERT INTO FUNCTION s3(
    'https://<ontap-s3-endpoint>/clickhouse-export/training_features/batch_{_partition_id}.parquet',
    '<access_key>', '<secret_key>',
    'Parquet'
)
SELECT * FROM training_features_export
WHERE export_timestamp > now() - INTERVAL 1 DAY;
```

**Databricks side**:

```python
# Silver: Read exported Parquet from synced S3
silver_features = spark.read.parquet("s3://<bucket>/clickhouse-export/training_features/")

# Write to Silver Delta table with schema enforcement
(
    silver_features.write
    .format("delta")
    .mode("merge")  # Upsert by event_id
    .option("mergeSchema", "true")
    .saveAsTable("manufacturing_poc.silver.training_features")
)
```

### 2.4 Path C: ONTAP NFS → DataSync → S3 → Auto Loader (Raw data)

```
[ONTAP NFS]                    [DataSync]         [S3]              [Databricks]
/vol_images/2026/06/15/*.jpg  -sync->  s3://bucket/raw/images/  -Auto Loader-> bronze.raw_images
/vol_telemetry/*.csv          -sync->  s3://bucket/raw/csv/     -Auto Loader-> bronze.raw_telemetry
```

---

### 2.5 Path D: Kafka → Lakebase — LTAP (Future Candidate)

> **Status**: Design exploration — Lakebase is GA but Kafka → Lakebase connector documentation pending
> **Context**: LTAP (Lake Transactional/Analytical Processing) announced at DAIS 2026 (2026-06-16)
> **References**: [LTAP Press Release](https://www.databricks.com/company/newsroom/press-releases/databricks-launches-ltap-first-lake-transactionalanalytical) / [Lakebase Search](https://www.databricks.com/blog/announcing-lakebase-search-agent-native-retrieval-built-lakebase-postgres)

#### LTAP Overview

LTAP is a new architecture pattern from Databricks that converges transactional processing (OLTP) and analytical processing (OLAP) on a single platform. In the context of this repository's edge-to-cloud flow, the Kafka → Lakebase direct-write path is positioned as a future alternative scenario.

| Component | Role | Status |
|---|---|---|
| Lakebase | Postgres-compatible operational DB (Databricks-managed) | GA |
| Lakehouse//RT | Millisecond query engine (Reyden engine) | Preview |
| Lakebase Search | Hybrid vector + full-text search | Beta |

#### Data Flow (Projected)

```
[Edge Pi]                   [Kafka]              [Databricks LTAP]
simple_capture.py  -event-> factory.events.raw -> Kafka Connector (TBD)
                                                      |
                                                      v
                                                 Lakebase (Postgres-compatible)
                                                      |
                                            +---------+---------+
                                            v                   v
                                     Lakehouse//RT          Delta Lake
                                   (ms-latency queries)  (batch analytics/ML)
```

#### Comparison with Path A (Structured Streaming → Delta)

| Aspect | Path A: Kafka → Structured Streaming → Delta | Path D: Kafka → Lakebase (LTAP) |
|--------|----------------------------------------------|--------------------------------|
| Latency | Seconds~Minutes (micro-batch) | Milliseconds~Seconds (projected) |
| Query Engine | Spark SQL / Photon | Lakehouse//RT (Reyden) / Postgres-compatible |
| Data Model | Delta tables (append-only Bronze) | Postgres tables (UPDATE/DELETE capable) |
| Use Case | Batch analytics, ML training data generation | Operational AI, real-time dashboards, API serving |
| Maturity | GA (validated) | Lakebase GA / Lakehouse//RT Preview |
| Cost Structure | DBU (Streaming) + S3 storage | Lakebase instance + Lakehouse//RT (TBD) |

#### Impact on This Project

- **No edge-side changes**: Local ONTAP + Kafka topic design remains unchanged
- **Cloud-side alternative path**: Added as a parallel option, not replacing existing Path A (Structured Streaming → Delta)
- **Operational AI scenarios**: Enables use cases difficult with Delta alone — real-time quality verdict APIs, image metadata search via Lakebase Search

#### Verification Required

| Item | Verification Aspect | Current Status |
|------|---------------------|----------------|
| Kafka → Lakebase connector | Connection method, configuration, throughput | Awaiting documentation |
| Ordering guarantees | Whether partition ordering is preserved in Lakebase writes | Unverified |
| Failure behavior | Kafka offset management on Lakebase write failures | Unverified |
| Schema compatibility | Mapping v3 event schema to Postgres tables | Design needed |
| Delta Lake sync | Auto-federation from Lakebase → Delta Lake | LTAP sync mechanism to be confirmed |
| Lakehouse//RT performance | Effective ms-latency under Preview constraints | Awaiting GA |
| Cost | Lakebase + Lakehouse//RT pricing model | Possibly unpublished |
| Network | On-premises Kafka → Databricks Lakebase connectivity | PrivateLink or VPN required |

#### Adoption Criteria

PoC validation will begin when the following conditions are met:

1. Kafka → Lakebase connector documentation is published with clear configuration guidance
2. Lakehouse//RT reaches GA (Preview not suitable for production adoption)
3. Latency or Operational AI requirements emerge that existing Path A cannot satisfy

#### Constraints

- Lakehouse//RT is **Preview** — production adoption requires GA
- LTAP has **no on-premises option** — cloud-side only impact
- Edge-side design (local ONTAP + Kafka) remains unchanged
- Existing Paths A/B/C **coexist** with LTAP (not replaced)

---

### 2.6 Lakeflow / Zerobus Ingest Impact Assessment

> **Assessment date**: 2026-06-20 (GA status reflected)
> **Context**: Databricks announced "Lakeflow: A new era of agentic data engineering" at DAIS 2026 (2026-06-16)
> **References**: [Lakeflow blog](https://www.databricks.com/blog/lakeflow-new-era-agentic-data-engineering) / [Zerobus Ingest docs](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/zerobus-overview) / [Real-Time Mode docs](https://docs.databricks.com/aws/en/structured-streaming/real-time) / [Real-Time Mode GA announcement](https://www.databricks.com/de/blog/announcing-general-availability-real-time-mode-apache-spark-structured-streaming-databricks)

#### Relevant New Capabilities

| # | Capability | Summary | Status | Impact on This Project |
|---|-----------|---------|--------|------------------------|
| 1 | Zerobus Ingest | Push-based serverless ingestion API. Writes directly to Delta tables without Kafka/MSK | GA | Additional ingestion path candidate for edge devices |
| 2 | Real-Time Mode (SDP) | 5ms latency mode for Spark Structured Streaming | GA (DBR 16.2+) | Latency improvement path for existing Path A |
| 3 | Lakeflow Connect (100+ connectors) | Managed connections to enterprise data sources | GA (connector-dependent) | Check availability of new connectors |
| 4 | Agentic Data Engineering | AI agents leverage pipeline context via Unity Catalog | Preview | Data quality × agent intersection |

#### Zerobus Ingest vs MSK/Confluent Kafka

| Aspect | Zerobus Ingest | MSK / Confluent Kafka (current design) |
|--------|---------------|----------------------------------------|
| Architecture | Push API → direct Delta table writes | Pub/Sub message bus → Consumer pulls |
| Infrastructure | Serverless (no partitions/brokers) | Broker/partition management required |
| Interfaces | gRPC SDK / REST API / OpenTelemetry | Kafka protocol (confluent-kafka-python) |
| Throughput | 100 MB/s per stream, 10+ GB/s per table | Cluster-configuration dependent |
| Ordering | Guaranteed per stream | Guaranteed per partition |
| Multi-consumer | Not supported (Delta table is sole sink) | Supported (multiple Consumer Groups) |
| Scope | Databricks ingestion only | General-purpose event bus (ClickHouse, Lambda, etc.) |
| Deployment | Within Databricks workspace (cloud) | On-premises VM (this project) or managed |
| Cost | Jobs Serverless SKU (DBU billing) | VM fixed cost or managed service monthly |

**Decision for this project**:

In this project, Kafka serves as a **general-purpose event bus** delivering events to multiple consumers (ClickHouse, Lambda, Databricks, etc.). Zerobus Ingest specializes in Databricks ingestion, so it is positioned as an **additional option** for Databricks-specific ingestion, **not a Kafka replacement**.

Scenarios where Zerobus Ingest is suitable:
- Adding a new data source where Databricks is the sole consumer
- Writing directly to Delta tables without Kafka intermediation (e.g., OpenTelemetry data)
- Supplementing Kafka when edge device count scales significantly and broker load-balancing becomes an issue

#### Real-Time Mode (SDP) vs Existing Path A Latency

| Aspect | Path A current: Kafka → Structured Streaming (micro-batch) | Path A improved: Kafka → Real-Time Mode (SDP) |
|--------|-----------------------------------------------------------|-----------------------------------------------|
| Latency | Seconds~Minutes (trigger interval dependent) | 5 milliseconds~ (end-to-end) |
| Execution model | Micro-batch (periodic trigger) | Long-running batch + continuous processing |
| Runtime | Standard DBR | DBR 16.2+ |
| Use cases | Batch analytics, ML data generation | Fraud detection, real-time personalization, immediate quality verdicts |
| Maturity | GA | GA (DBR 16.2+) |
| Additional cost | None (same DBU as current) | Same DBU model |

**Impact on Path A**:

Since Real-Time Mode has reached GA, the existing Path A (Kafka → Structured Streaming → Delta) pipeline can achieve millisecond latency by simply switching the trigger mode — without major code rewrites. This potentially covers some use cases that Path D (LTAP: Kafka → Lakebase) targets.

#### Relationship with Path D (LTAP)

```
                          [Kafka]
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
    Path A (current)  Path A (improved)  Path D (future)
    Structured        Real-Time Mode     Kafka → Lakebase
    Streaming         for SDP
    (sec~min)         (5ms~)             (ms~sec, projected)
        |                 |                 |
        v                 v                 v
    Delta Table       Delta Table        Lakebase (Postgres)
    (analytics/ML)    (analytics/ML/     (Operational AI)
                       immediate)
```

| Scenario | Recommended Path | Rationale |
|----------|-----------------|-----------|
| ML training data generation | Path A (current) | Micro-batch sufficient, cost-efficient |
| Near-real-time analytics dashboard | Path A (Real-Time Mode) | Delta tables + Photon for fast queries |
| Immediate quality verdict API serving | Path D (LTAP) | Postgres-compatible API with UPDATE/DELETE + ms response |
| OpenTelemetry metrics ingestion | Zerobus Ingest (direct) | No Kafka needed, native OTLP support |

#### Adoption Gate Conditions

| Capability | Gate Condition | Action |
|-----------|---------------|--------|
| Zerobus Ingest | Databricks-only ingestion need materializes for edge devices | SDK validation (gRPC + Python) |
| Real-Time Mode | Latency requirement emerges for existing Path A pipeline (already GA) | Trigger mode change PoC |
| Lakeflow Connect | New connector enables direct ONTAP/NFS connection | Evaluate as DataSync alternative |
| Agentic Data Engineering | Concrete API published for Unity Catalog lineage × AI Agent | Assess for data quality pipeline improvement |

#### Constraints

- Zerobus Ingest is **Databricks-only** — no general-purpose multi-consumer delivery like Kafka
- Real-Time Mode is **GA** (DBR 16.2+) — ready for production adoption
- Lakeflow is **Databricks-managed** — no on-premises option
- Edge-side Kafka Producer design remains unchanged (cloud-side receiving only)
- Vendor-versus framing of Lakeflow/Zerobus against Kafka is inappropriate — choose based on use case

---

## 3. Unity Catalog Design

### 3.1 Catalog Structure

```
catalog: manufacturing_poc
|
+-- schema: bronze
|   +-- table: kafka_events          (from Kafka Structured Streaming)
|   +-- table: sensor_events         (filtered from kafka_events)
|   +-- table: quality_events        (filtered from kafka_events)
|   +-- table: payload_manifest      (filtered from kafka_events)
|   +-- table: raw_images            (from DataSync + Auto Loader)
|   +-- table: raw_telemetry_csv     (from DataSync + Auto Loader)
|
+-- schema: silver
|   +-- table: training_features     (from ClickHouse export, cleansed)
|   +-- table: quality_trends        (aggregated from quality_events)
|   +-- table: equipment_health      (from telemetry, scored)
|
+-- schema: gold
|   +-- table: training_dataset      (features + labels + payload refs)
|   +-- table: quality_summary       (executive dashboard)
|   +-- table: predictive_maintenance (ML predictions)
|
+-- schema: ml
    +-- model: quality_classifier    (MLflow registered model)
    +-- feature_table: print_features (Feature Store)
```

### 3.2 External Location

```sql
-- Register synced S3 bucket as External Location
CREATE EXTERNAL LOCATION IF NOT EXISTS edge_data_synced
URL 's3://<bucket>/raw/'
WITH (STORAGE CREDENTIAL edge_to_cloud_credential);

-- ClickHouse export destination
CREATE EXTERNAL LOCATION IF NOT EXISTS clickhouse_export
URL 's3://<bucket>/clickhouse-export/'
WITH (STORAGE CREDENTIAL edge_to_cloud_credential);
```

### 3.3 Permission Design

```sql
-- Data engineers: Bronze/Silver read/write
GRANT USE CATALOG ON CATALOG manufacturing_poc TO `data-engineers`;
GRANT CREATE TABLE, MODIFY ON SCHEMA manufacturing_poc.bronze TO `data-engineers`;
GRANT CREATE TABLE, MODIFY ON SCHEMA manufacturing_poc.silver TO `data-engineers`;

-- Data scientists: Silver/Gold read + ML schema
GRANT SELECT ON SCHEMA manufacturing_poc.silver TO `data-scientists`;
GRANT SELECT ON SCHEMA manufacturing_poc.gold TO `data-scientists`;
GRANT ALL PRIVILEGES ON SCHEMA manufacturing_poc.ml TO `data-scientists`;

-- BI users: Gold read only
GRANT SELECT ON SCHEMA manufacturing_poc.gold TO `bi-users`;
```

---

## 4. Data Quality (DLT Expectations)

```python
import dlt
from pyspark.sql import functions as F

@dlt.table(name="bronze_quality_events")
@dlt.expect_or_drop("valid_event_id", "event_id IS NOT NULL")
@dlt.expect_or_drop("valid_timestamp", "timestamp IS NOT NULL")
@dlt.expect("confidence_range", "confidence BETWEEN 0.0 AND 1.0")
@dlt.expect("known_verdict", "verdict IN ('normal', 'anomaly_detected')")
def bronze_quality_events():
    return (
        spark.readStream.format("delta")
        .table("manufacturing_poc.bronze.kafka_events")
        .filter(F.col("event_type") == "quality_event")
    )
```

---

## 5. ML Pipeline Design

### 5.1 Gold Training Dataset

```python
gold_training = (
    spark.table("manufacturing_poc.silver.training_features")
    .join(spark.table("manufacturing_poc.bronze.payload_manifest"), on="event_id", how="left")
    .select("event_id", "equipment_id", "timestamp", "confidence",
            "anomaly_types", "max_severity", "payload_uri",
            "temperature_celsius", "humidity_percent",
            "human_label", "label_confidence")
)
gold_training.write.format("delta").mode("overwrite").saveAsTable(
    "manufacturing_poc.gold.training_dataset"
)
```

### 5.2 MLflow Integration

```python
import mlflow

with mlflow.start_run(run_name="quality-classifier-v1"):
    mlflow.log_param("model_type", "random_forest")
    mlflow.log_param("data_source", "manufacturing_poc.gold.training_dataset")
    model = train_quality_model(gold_training)
    mlflow.sklearn.log_model(model, "quality_classifier")
    mlflow.register_model(
        f"runs:/{mlflow.active_run().info.run_id}/quality_classifier",
        "manufacturing_poc.ml.quality_classifier"
    )
```

---

## 6. Lineage Tracking

Unity Catalog automatically tracks:

```
Edge capture (Pi)
  -> Kafka event (event_id: AAA)
    -> bronze.kafka_events (row)
      -> silver.training_features (derived)
        -> gold.training_dataset (joined with label)
          -> ml.quality_classifier (training input)
```

**payload_uri** enables tracing from any training record back to the original image on ONTAP NFS.

---

## 7. Cost Estimate (PoC)

| Component | Estimate | Notes |
|-----------|----------|-------|
| DataSync (10 GB/day) | ~$0.125/day | Daily image + CSV sync |
| S3 (synced copy, 300GB) | ~$7/month | Standard IA eligible |
| Databricks Compute | ~$50-100/month | All-Purpose cluster (PoC scale) |
| Kafka → Databricks Streaming | DBU consumption | Few DBU/hour for PoC |

---

## 8. Open Items

| Item | Status | Dependency |
|------|--------|-----------|
| Databricks Workspace creation | Not started | AWS Marketplace or direct contract |
| Storage Credential creation | Not started | S3 bucket + IAM role |
| Kafka → Databricks network design | In design | Kafka VM ↔ Databricks VPC |
| ClickHouse → S3 export automation | Designed | After ClickHouse deployment |
| DataSync Agent (ONTAP NFS → S3) | Validated in Lakehouse project | FSx for ONTAP environment |
| LTAP (Kafka → Lakebase) connector validation | Awaiting documentation | Lakebase GA / connector spec published |
| Lakehouse//RT GA evaluation | Preview — awaiting GA | Databricks roadmap |
