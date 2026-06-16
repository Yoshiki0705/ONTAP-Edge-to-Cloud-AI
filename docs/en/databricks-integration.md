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
| A | Kafka → Spark Structured Streaming → Delta | Events (JSON) | Seconds~Minutes | Bronze table direct ingestion |
| B | ClickHouse → Parquet Export → ONTAP S3 → DataSync → S3 → UC | Aggregated features | Hours (batch) | Silver/Gold tables |
| C | ONTAP NFS → DataSync → S3 → Auto Loader → UC | Raw images, CSV | Minutes~Hours | Raw data long-term storage/analysis |

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
