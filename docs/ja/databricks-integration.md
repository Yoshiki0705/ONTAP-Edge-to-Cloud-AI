# Databricks 連携設計

> 作成日: 2026-06-15
> ステータス: 設計完了（Lakehouse プロジェクトと同期）
> 関連: [fsxn-lakehouse-integrations/poc-templates/04-databricks-integration](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/tree/main/poc-templates/04-databricks-integration)
> Edge ↔ Lakehouse 同期記録: [14_edge_lakehouse_sync.md](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/blob/main/integrations/manufacturing-data-platform/docs/ja/14_edge_lakehouse_sync.md) — スキーマ・トピック・責任分担の同期状況

---

## 1. 概要

エッジデバイスが収集したデータを Databricks Lakehouse で AI/ML 学習データセットとして活用する連携設計。

**前提（未検証）**: Unity Catalog の External Location に FSx for ONTAP の S3 Access Point を
登録して直接読ませられるかは、**このプロジェクトでは検証していない**。以前は
「セッションポリシーの制限により不可」と記載していたが、その機構を裏付ける一次情報を
確認できなかったため断定を取り下げた。

- Databricks 側のドキュメントは External Location を「S3 のパス + storage credential」として
  定義しており、access point を受け付けるか否かの明示的な記述は見つからない
  （[Connect to an AWS S3 external location](https://docs.databricks.com/aws/en/connect/storage/amazon-s3)）
- 判定は登録を実際に試すことでしか得られない。結果が出るまで、以下の代替パスは
  「access point 直結が使えない場合に成立する経路」として読むこと

未確認項目としての追跡は [S3 AP 互換性と制約](./s3ap-compatibility-matrix.md) の §6 にある。

---

## 2. データ接続パス

### 2.1 パス一覧

| # | パス | データ種別 | リアルタイム性 | 用途 |
|---|------|-----------|-------------|------|
| A | Kafka → Spark Structured Streaming → Delta | イベント (JSON) | 秒〜分 † | Bronze テーブル直接取り込み |
| B | ClickHouse → Parquet Export → ONTAP S3 → DataSync → S3 → UC | 集計済み特徴量 | 時間 (バッチ) | Silver/Gold テーブル |
| C | ONTAP NFS → DataSync → S3 → Auto Loader → UC | 生画像, CSV | 分〜時間 | 生データの長期保管・分析 |
| D | Kafka → Lakebase (LTAP) | イベント (JSON) | ミリ秒〜秒 | Operational DB + 分析統合 (将来候補) |

> † パス A のレイテンシは Real-Time Mode for SDP (GA) により最小 5ms まで短縮可能。セクション 2.6 参照。

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

### 2.5 パス D: Kafka → Lakebase — LTAP (将来候補)

> **ステータス**: 設計検討中 — Lakebase は GA だが Kafka → Lakebase コネクタの具体的ドキュメント公開待ち
> **前提**: DAIS 2026 (2026-06-16) で発表された LTAP (Lake Transactional/Analytical Processing)
> **参考**: [LTAP プレスリリース](https://www.databricks.com/company/newsroom/press-releases/databricks-launches-ltap-first-lake-transactionalanalytical) / [Lakebase Search](https://www.databricks.com/blog/announcing-lakebase-search-agent-native-retrieval-built-lakebase-postgres)

#### LTAP 概要

LTAP は Databricks が提唱する新しいアーキテクチャパターンで、トランザクション処理（OLTP）と分析処理（OLAP）を単一プラットフォーム上で統合する。本リポジトリのエッジ → クラウドフローにおいて、Kafka → Lakebase 直接書き込みパスを将来の代替シナリオとして位置づける。

| コンポーネント | 役割 | ステータス |
|---|---|---|
| Lakebase | Postgres 互換 operational DB（Databricks 管理） | GA |
| Lakehouse//RT | ミリ秒クエリエンジン（Reyden エンジン） | Preview |
| Lakebase Search | ハイブリッド vector + full-text 検索 | Beta |

#### データフロー (想定)

```
[Edge Pi]                   [Kafka]              [Databricks LTAP]
simple_capture.py  ─event─> factory.events.raw ─> Kafka Connector (TBD)
                                                      |
                                                      v
                                                 Lakebase (Postgres 互換)
                                                      |
                                            ┌─────────┴─────────┐
                                            v                   v
                                     Lakehouse//RT          Delta Lake
                                   (ミリ秒クエリ)       (バッチ分析・ML)
```

#### パス A (Structured Streaming → Delta) との比較

| 観点 | パス A: Kafka → Structured Streaming → Delta | パス D: Kafka → Lakebase (LTAP) |
|------|----------------------------------------------|--------------------------------|
| レイテンシ | 秒〜分（マイクロバッチ） | ミリ秒〜秒（想定） |
| クエリエンジン | Spark SQL / Photon | Lakehouse//RT (Reyden) / Postgres 互換 |
| データモデル | Delta テーブル (append-only Bronze) | Postgres テーブル (UPDATE/DELETE 可) |
| 用途 | バッチ分析、ML 学習データ生成 | Operational AI、リアルタイムダッシュボード、API サーブ |
| 成熟度 | GA (検証済み) | Lakebase GA / Lakehouse//RT Preview |
| コスト構造 | DBU (Streaming) + S3 ストレージ | Lakebase インスタンス + Lakehouse//RT (未定) |

#### 本プロジェクトへの影響

- **エッジ側に変更なし**: ローカル ONTAP + Kafka トピック構成はそのまま維持
- **クラウド側の代替パス**: 既存パス A (Structured Streaming → Delta) を置き換えるのではなく、並列オプションとして追加
- **Operational AI シナリオ**: リアルタイム品質判定 API や Lakebase Search による画像メタデータ検索など、Delta 単独では難しいユースケースに対応可能

#### 検証必要事項

| 項目 | 確認観点 | 現状 |
|------|---------|------|
| Kafka → Lakebase コネクタ | 接続方式、設定、スループット | ドキュメント公開待ち |
| 順序保証 | パーティション内の順序が Lakebase 書き込みで保持されるか | 未検証 |
| 障害時挙動 | Lakebase 書き込み失敗時の Kafka offset 管理 | 未検証 |
| スキーマ互換性 | v3 イベントスキーマの Postgres テーブルへのマッピング | 設計必要 |
| Delta Lake 同期 | Lakebase → Delta Lake への自動フェデレーション | LTAP の自動同期メカニズム確認必要 |
| Lakehouse//RT 性能 | ミリ秒クエリの実効レイテンシ（Preview 制約） | GA 待ち |
| コスト | Lakebase + Lakehouse//RT の料金体系 | 未公開の可能性あり |
| ネットワーク | オンプレミス Kafka → Databricks Lakebase 間の接続 | PrivateLink or VPN 経由 |

#### 採用判断基準

以下の条件が満たされた段階で PoC 検証を開始する:

1. Kafka → Lakebase コネクタのドキュメントが公開され、設定方法が明確になる
2. Lakehouse//RT が GA になる（Preview 段階では本番採用不可）
3. 既存パス A では満たせないレイテンシ要件または Operational AI 要件が顕在化する

#### 制約事項

- Lakehouse//RT は **Preview** — 本番採用は GA 待ち
- LTAP に**オンプレミスオプションはない** — クラウド側のみ影響
- エッジ側の設計（ローカル ONTAP + Kafka）は変更しない
- 既存パス A/B/C は LTAP 採用後も**併存**する（置き換えではない）

---

### 2.6 Lakeflow / Zerobus Ingest 影響評価

> **評価日**: 2026-06-20 (GA ステータス反映)
> **背景**: DAIS 2026 (2026-06-16) で Databricks が「Lakeflow: A new era of agentic data engineering」を発表
> **参考**: [Lakeflow ブログ](https://www.databricks.com/blog/lakeflow-new-era-agentic-data-engineering) / [Zerobus Ingest ドキュメント](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/zerobus-overview) / [Real-Time Mode ドキュメント](https://docs.databricks.com/aws/en/structured-streaming/real-time) / [Real-Time Mode GA 発表](https://www.databricks.com/de/blog/announcing-general-availability-real-time-mode-apache-spark-structured-streaming-databricks)

#### 影響のある新機能

| # | 機能 | 概要 | ステータス | 本プロジェクトへの影響 |
|---|------|------|-----------|---------------------|
| 1 | Zerobus Ingest | Push 型サーバーレス取り込み API。Kafka/MSK なしで直接 Delta テーブルへ書き込み | GA | エッジデバイスからの取り込みパスの追加候補 |
| 2 | Real-Time Mode (SDP) | Spark Structured Streaming の 5ms レイテンシモード | GA (DBR 16.2+) | 既存パス A のレイテンシ改善パス |
| 3 | Lakeflow Connect (100+ コネクタ) | エンタープライズデータソースへのマネージド接続 | GA (コネクタ依存) | 新コネクタの利用可能性確認 |
| 4 | Agentic Data Engineering | Unity Catalog 上で AI エージェントがパイプラインコンテキストを活用 | Preview | データ品質 × エージェントの接点 |

#### Zerobus Ingest と MSK/Confluent Kafka の比較

| 観点 | Zerobus Ingest | MSK / Confluent Kafka (現行設計) |
|------|---------------|----------------------------------|
| アーキテクチャ | Push 型 API → Delta テーブル直接書き込み | Pub/Sub メッセージバス → Consumer が Pull |
| インフラ管理 | サーバーレス（パーティション/ブローカー不要） | ブローカー/パーティション管理必要 |
| インターフェース | gRPC SDK / REST API / OpenTelemetry | Kafka プロトコル (confluent-kafka-python) |
| スループット | 100 MB/s per stream, 10+ GB/s per table | クラスタ構成依存 |
| 順序保証 | ストリーム単位で保証 | パーティション単位で保証 |
| マルチコンシューマ | 不可（Delta テーブルが唯一のシンク） | 可（複数 Consumer Group） |
| 用途の幅 | Databricks 取り込み専用 | 汎用イベントバス（ClickHouse, Lambda 等へも配信） |
| デプロイ | Databricks ワークスペース内（クラウド） | オンプレミス VM (本プロジェクト) or マネージド |
| コスト | Jobs Serverless SKU (DBU 課金) | VM 固定費 or マネージドサービス月額 |

**本プロジェクトにおける判断**:

本プロジェクトでは Kafka が**汎用イベントバス**として機能し、ClickHouse・Lambda・Databricks 等の複数コンシューマにイベントを配信している。Zerobus Ingest は Databricks への取り込みに特化しているため、Kafka の**代替ではなく**、Databricks 向け取り込みの**追加オプション**として位置づける。

Zerobus Ingest が適するシナリオ:
- Databricks のみがコンシューマである新規データソースの追加時
- Kafka を経由せず直接 Delta テーブルへ書き込みたい場合（例: OpenTelemetry データ）
- エッジデバイス数が大幅に増加し、Kafka ブローカーの負荷分散が課題になった場合の補完

#### Real-Time Mode (SDP) と既存パス A のレイテンシ比較

| 観点 | パス A 現行: Kafka → Structured Streaming (マイクロバッチ) | パス A 改善: Kafka → Real-Time Mode (SDP) |
|------|--------------------------------------------------------|------------------------------------------|
| レイテンシ | 秒〜分（トリガー間隔依存） | 5 ミリ秒〜（end-to-end） |
| 実行モデル | マイクロバッチ（定期トリガー） | 長時間実行バッチ + 連続処理 |
| ランタイム | DBR 標準 | DBR 16.2+ |
| ユースケース | バッチ分析、ML データ生成 | 不正検知、リアルタイムパーソナライゼーション、品質即時判定 |
| 成熟度 | GA | GA (DBR 16.2+) |
| 追加コスト | なし（現行と同じ DBU） | 同じ DBU 体系 |

**パス A への影響**:

Real-Time Mode は GA に到達しており、既存パス A (Kafka → Structured Streaming → Delta) のトリガーモードを Real-Time Mode に変更するだけで、コードを大幅に書き換えずにミリ秒レイテンシを実現できる。これは Path D (LTAP: Kafka → Lakebase) の一部ユースケースをカバーし得る。

#### パス D (LTAP) との関係整理

```
                          [Kafka]
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
    Path A (現行)     Path A (改善)     Path D (将来)
    Structured        Real-Time Mode    Kafka → Lakebase
    Streaming         for SDP
    (秒〜分)          (5ms〜)           (ms〜秒、想定)
        |                 |                 |
        v                 v                 v
    Delta Table       Delta Table       Lakebase (Postgres)
    (分析・ML)        (分析・ML・即時)   (Operational AI)
```

| シナリオ | 推奨パス | 理由 |
|---------|---------|------|
| ML 学習データ生成 | Path A (現行) | マイクロバッチで十分、コスト効率良 |
| 準リアルタイム分析ダッシュボード | Path A (Real-Time Mode) | Delta テーブル + Photon で高速クエリ |
| 即時品質判定 API サーブ | Path D (LTAP) | Postgres 互換 API で UPDATE/DELETE + ミリ秒応答 |
| OpenTelemetry メトリクス取り込み | Zerobus Ingest (直接) | Kafka 不要、OTLP ネイティブ対応 |

#### 採用ゲート条件

| 機能 | ゲート条件 | アクション |
|------|-----------|-----------|
| Zerobus Ingest | エッジデバイスの Databricks 専用取り込みニーズが顕在化 | SDK 検証 (gRPC + Python) |
| Real-Time Mode | 既存 Path A パイプラインでのレイテンシ要件顕在化 (GA 済み) | トリガーモード変更の PoC |
| Lakeflow Connect | 新コネクタで ONTAP / NFS 直接接続が可能になった場合 | DataSync 代替として評価 |
| Agentic Data Engineering | Unity Catalog リネージ × AI Agent の具体的 API 公開 | データ品質パイプライン改善に適用検討 |

#### 制約事項

- Zerobus Ingest は **Databricks 専用** — Kafka のような汎用マルチコンシューマ配信は不可
- Real-Time Mode は **GA** (DBR 16.2+) — 本番採用可能
- Lakeflow は **Databricks マネージド** — オンプレミス非対応
- エッジ側の Kafka Producer 設計には変更を加えない（クラウド側受信のみの影響）
- 「Lakeflow/Zerobus が Kafka を上回る」等のベンダー対決表現は不適切 — 用途に応じて選択

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
| LTAP (Kafka → Lakebase) コネクタ検証 | ドキュメント公開待ち | Lakebase GA / コネクタ仕様公開 |
| Lakehouse//RT GA 評価 | Preview — GA 待ち | Databricks ロードマップ |
