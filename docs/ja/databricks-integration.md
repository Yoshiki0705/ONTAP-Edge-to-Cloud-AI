# Databricks 連携設計

> 作成日: 2026-06-15
> ステータス: 設計完了（Lakehouse プロジェクトと同期）
> 関連: [fsxn-lakehouse-integrations/poc-templates/04-databricks-integration](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/tree/main/poc-templates/04-databricks-integration)

---

## 1. 概要

エッジデバイスが収集したデータを Databricks Lakehouse で AI/ML 学習データセットとして活用する連携設計。

**制約事項**: Unity Catalog は FSx for ONTAP S3 Access Points に直接アクセスできない（セッションポリシー制限）。このため、複数の代替パスを設計する。

---

## 2. データ接続パス

### 2.1 パス一覧

| # | パス | データ種別 | リアルタイム性 | 用途 |
|---|------|-----------|-------------|------|
| A | Kafka → Spark Structured Streaming → Delta | イベント (JSON) | 秒〜分 | Bronze テーブル直接取り込み |
| B | ClickHouse → Parquet Export → ONTAP S3 → DataSync → S3 → UC | 集計済み特徴量 | 時間 (バッチ) | Silver/Gold テーブル |
| C | ONTAP NFS → DataSync → S3 → Auto Loader → UC | 生画像, CSV | 分〜時間 | 生データの長期保管・分析 |

### 2.2 パス A: Kafka → Structured Streaming → Delta (推奨: リアルタイム)

```
[Edge Pi]                   [Kafka]              [Databricks]
simple_capture.py  ─event─> factory.events.raw ─> Spark Structured Streaming
                                                      |
                                                      v
                                                 bronze.sensor_events (Delta)
                                                 bronze.quality_events (Delta)
                                                 bronze.payload_manifest (Delta)
```

**Databricks ノートブック例**:

```python
# Bronze: Kafka → Delta (Structured Streaming)
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

### 2.3 パス B: ClickHouse Export → Databricks (バッチ、ML 特徴量)

```
[ClickHouse]                             [ONTAP S3]           [S3]          [Databricks]
training_features_export  ─Parquet─>  clickhouse-export/  ─DataSync─>  s3://bucket/  ─UC─> silver.training_features
```

**ClickHouse エクスポート**:

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

**Databricks 側**:

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

### 2.4 パス C: ONTAP NFS → DataSync → S3 → Auto Loader (生データ)

```
[ONTAP NFS]                    [DataSync]         [S3]              [Databricks]
/vol_images/2026/06/15/*.jpg  ─sync─>  s3://bucket/raw/images/  ─Auto Loader─> bronze.raw_images
/vol_telemetry/*.csv          ─sync─>  s3://bucket/raw/csv/     ─Auto Loader─> bronze.raw_telemetry
```

**DataSync タスク** (Lakehouse プロジェクトの `datasync-task.yaml` を再利用):

```bash
aws cloudformation deploy \
  --template-file datasync-task.yaml \
  --stack-name edge-to-cloud-databricks-sync \
  --parameter-overrides \
    SvmArn=<SVM_ARN> \
    TargetBucket=<BUCKET_NAME> \
    SourceSubdirectory=/vol_images \
  --capabilities CAPABILITY_IAM
```

---

## 3. Unity Catalog 設計

### 3.1 カタログ構造

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
-- S3 バケット (DataSync 先) を External Location として登録
CREATE EXTERNAL LOCATION IF NOT EXISTS edge_data_synced
URL 's3://<bucket>/raw/'
WITH (STORAGE CREDENTIAL edge_to_cloud_credential);

-- ClickHouse エクスポート先
CREATE EXTERNAL LOCATION IF NOT EXISTS clickhouse_export
URL 's3://<bucket>/clickhouse-export/'
WITH (STORAGE CREDENTIAL edge_to_cloud_credential);
```

### 3.3 権限設計

```sql
-- データエンジニア: Bronze/Silver の読み書き
GRANT USE CATALOG ON CATALOG manufacturing_poc TO `data-engineers`;
GRANT USE SCHEMA ON SCHEMA manufacturing_poc.bronze TO `data-engineers`;
GRANT USE SCHEMA ON SCHEMA manufacturing_poc.silver TO `data-engineers`;
GRANT CREATE TABLE, MODIFY ON SCHEMA manufacturing_poc.bronze TO `data-engineers`;
GRANT CREATE TABLE, MODIFY ON SCHEMA manufacturing_poc.silver TO `data-engineers`;

-- データサイエンティスト: Silver/Gold の読み取り + ML スキーマ
GRANT USE SCHEMA ON SCHEMA manufacturing_poc.silver TO `data-scientists`;
GRANT USE SCHEMA ON SCHEMA manufacturing_poc.gold TO `data-scientists`;
GRANT SELECT ON SCHEMA manufacturing_poc.silver TO `data-scientists`;
GRANT SELECT ON SCHEMA manufacturing_poc.gold TO `data-scientists`;
GRANT USE SCHEMA ON SCHEMA manufacturing_poc.ml TO `data-scientists`;
GRANT ALL PRIVILEGES ON SCHEMA manufacturing_poc.ml TO `data-scientists`;

-- BI ユーザー: Gold の読み取りのみ
GRANT USE SCHEMA ON SCHEMA manufacturing_poc.gold TO `bi-users`;
GRANT SELECT ON SCHEMA manufacturing_poc.gold TO `bi-users`;
```

---

## 4. データ品質 (DLT Expectations)

```python
# Delta Live Tables パイプライン例
import dlt
from pyspark.sql import functions as F

@dlt.table(
    name="bronze_quality_events",
    comment="AI quality analysis results from edge pipeline"
)
@dlt.expect_or_drop("valid_event_id", "event_id IS NOT NULL")
@dlt.expect_or_drop("valid_timestamp", "timestamp IS NOT NULL")
@dlt.expect("confidence_range", "confidence BETWEEN 0.0 AND 1.0")
@dlt.expect("known_verdict", "verdict IN ('normal', 'anomaly_detected')")
def bronze_quality_events():
    return (
        spark.readStream
        .format("delta")
        .table("manufacturing_poc.bronze.kafka_events")
        .filter(F.col("event_type") == "quality_event")
    )
```

---

## 5. ML パイプライン設計

### 5.1 Gold 学習データセット生成

```python
# Gold: Training dataset (features + labels + payload references)
gold_training = (
    spark.table("manufacturing_poc.silver.training_features")
    .join(
        spark.table("manufacturing_poc.bronze.payload_manifest"),
        on="event_id",
        how="left"
    )
    .select(
        "event_id",
        "equipment_id",
        "timestamp",
        "confidence",
        "anomaly_types",
        "max_severity",
        "payload_uri",
        "temperature_celsius",
        "humidity_percent",
        # Label (from feedback loop)
        "human_label",
        "label_confidence",
    )
)

gold_training.write.format("delta").mode("overwrite").saveAsTable(
    "manufacturing_poc.gold.training_dataset"
)
```

### 5.2 MLflow 統合

```python
import mlflow

with mlflow.start_run(run_name="quality-classifier-v1"):
    # Log parameters
    mlflow.log_param("model_type", "random_forest")
    mlflow.log_param("features", ["confidence", "anomaly_count", "temp", "humidity"])
    mlflow.log_param("data_source", "manufacturing_poc.gold.training_dataset")
    mlflow.log_param("lineage_id_filter", "session-2026-06-*")

    # Train and log model
    model = train_quality_model(gold_training)
    mlflow.sklearn.log_model(model, "quality_classifier")

    # Register in Unity Catalog
    mlflow.register_model(
        f"runs:/{mlflow.active_run().info.run_id}/quality_classifier",
        "manufacturing_poc.ml.quality_classifier"
    )
```

---

## 6. リネージ追跡

Unity Catalog のリネージ機能により、以下が自動追跡される:

```
Edge capture (Pi)
  → Kafka event (event_id: AAA)
    → bronze.kafka_events (row)
      → silver.training_features (derived row)
        → gold.training_dataset (joined with label)
          → ml.quality_classifier (model training input)
```

**payload_uri** により、任意の学習データから元画像 (ONTAP NFS 上) に遡ることが可能。

---

## 7. コスト見積 (PoC)

| コンポーネント | 見積 | 備考 |
|--------------|------|------|
| DataSync (10 GB/日) | ~$0.125/日 | 画像 + CSV の日次同期 |
| S3 (同期コピー, 300GB) | ~$7/月 | Standard IA 利用可能 |
| Databricks Compute | ~$50-100/月 | All-Purpose cluster (PoC 規模) |
| Kafka → Databricks Streaming | DBU 消費 | PoC では数 DBU/時間 |

---

## 8. 未決事項

| 項目 | 状態 | 依存 |
|------|------|------|
| Databricks Workspace 作成 | 未実施 | AWS Marketplace or 直接契約 |
| Storage Credential 作成 | 未実施 | S3 バケット + IAM ロール |
| Kafka → Databricks 直接接続のネットワーク設計 | 設計中 | Kafka VM ↔ Databricks VPC |
| ClickHouse → S3 Export の自動化 (cron or ClickHouse scheduled) | 設計済み | ClickHouse デプロイ後 |
| DataSync Agent (ONTAP NFS → S3) | Lakehouse プロジェクトで検証済み | FSx for ONTAP 環境 |
