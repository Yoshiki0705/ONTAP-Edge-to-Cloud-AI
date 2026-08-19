# データスキーマ設計

> 作成日: 2026-05-29
> 対象: PoC #1 (3Dプリント品質監視) / PoC #2 (ONTAPテレメトリ)
> ステータス: Draft

---

## 1. 設計方針

| 方針 | 理由 |
|------|------|
| JSON を標準メッセージフォーマットとする | 汎用性が高く、ONTAP NFS 上のファイルとしても AWS サービス（Athena, Glue）でも直接読み取り可能 |
| S3 上は Parquet (分析用) + 原本 JSON/JPEG (アーカイブ) | Athena クエリ性能とデータ保全の両立 |
| パーティションは日付 + デバイスID | 時系列クエリとデバイス別フィルタの両方に対応 |
| スキーマバージョニングを導入 | 後方互換性を維持しつつフィールド追加を可能に |
| UTC タイムスタンプを基準とする | タイムゾーン混在を防止 |

---

## 2. メッセージエンベロープ（共通）

すべての IoT メッセージは以下の共通エンベロープに従う:

```json
{
  "schema_version": "1.0",
  "message_id": "uuid-v4",
  "device_id": "rpi5-001",
  "timestamp": "2026-05-29T10:30:00.000Z",
  "message_type": "image_capture | sensor_reading | ontap_telemetry | alert",
  "payload": { }
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `schema_version` | string | ✅ | セマンティックバージョン (MAJOR.MINOR) |
| `message_id` | string (UUID v4) | ✅ | メッセージの一意識別子 |
| `device_id` | string | ✅ | デバイス識別子 (命名規則: `{type}-{seq}`) |
| `timestamp` | string (ISO 8601) | ✅ | UTC タイムスタンプ |
| `message_type` | enum | ✅ | ペイロード種別 |
| `payload` | object | ✅ | メッセージ種別固有のデータ |

---

## 3. ペイロードスキーマ

### 3.1 画像キャプチャ (image_capture)

PoC #1: 3Dプリント品質監視で使用。

```json
{
  "schema_version": "1.0",
  "message_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "device_id": "rpi5-001",
  "timestamp": "2026-05-29T10:30:00.000Z",
  "message_type": "image_capture",
  "payload": {
    "image": {
      "s3_key": "raw/image_capture/year=2026/month=05/day=29/device=rpi5-001/20260529T103000Z_rpi5-001_print-monitor.jpg",
      "format": "jpeg",
      "resolution": "1920x1080",
      "size_bytes": 312000,
      "compression_quality": 80
    },
    "capture_context": {
      "trigger": "scheduled",
      "interval_seconds": 30,
      "camera_id": "cam-usb-001",
      "camera_model": "brio-4k"
    },
    "print_context": {
      "job_id": "job-20260529-001",
      "model_file": "bracket-v2.3mf",
      "layer_current": 42,
      "layer_total": 180,
      "elapsed_minutes": 35,
      "nozzle_temp_celsius": 210,
      "bed_temp_celsius": 60
    }
  }
}
```

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `image.s3_key` | string | ✅ | S3 上の画像パス |
| `image.format` | enum (jpeg/png) | ✅ | 画像フォーマット |
| `image.resolution` | string | ✅ | 解像度 (WxH) |
| `image.size_bytes` | integer | ✅ | ファイルサイズ |
| `image.compression_quality` | integer (1-100) | ✅ | JPEG 圧縮品質 |
| `capture_context.trigger` | enum | ✅ | scheduled / event / manual |
| `capture_context.interval_seconds` | integer | ○ | 定期撮影間隔 |
| `print_context.job_id` | string | ○ | 印刷ジョブID |
| `print_context.layer_current` | integer | ○ | 現在レイヤー |
| `print_context.nozzle_temp_celsius` | number | ○ | ノズル温度 |

### 3.2 AI分析結果 (analysis_result)

Bedrock Claude Vision / Rekognition の分析結果:

```json
{
  "schema_version": "1.0",
  "message_id": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
  "device_id": "rpi5-001",
  "timestamp": "2026-05-29T10:30:05.000Z",
  "message_type": "analysis_result",
  "payload": {
    "source_message_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "analyzer": {
      "service": "bedrock",
      "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
      "latency_ms": 4200
    },
    "result": {
      "status": "anomaly_detected",
      "confidence": 0.87,
      "anomalies": [
        {
          "type": "stringing",
          "severity": "medium",
          "location": "upper-left quadrant",
          "description": "Fine strings visible between support structures"
        }
      ],
      "recommendation": "Monitor next 5 layers. If stringing persists, consider reducing nozzle temperature by 5°C."
    }
  }
}
```

### 3.3 センサーデータ (sensor_reading)

環境センサー / 振動センサーの読み取り値:

```json
{
  "schema_version": "1.0",
  "message_id": "c3d4e5f6-a7b8-9012-cdef-345678901234",
  "device_id": "rpi5-002",
  "timestamp": "2026-05-29T10:30:00.000Z",
  "message_type": "sensor_reading",
  "payload": {
    "readings": [
      {
        "sensor_id": "dht22-001",
        "sensor_type": "temperature_humidity",
        "values": {
          "temperature_celsius": 24.5,
          "humidity_percent": 45.2
        },
        "unit_map": {
          "temperature_celsius": "°C",
          "humidity_percent": "%RH"
        }
      },
      {
        "sensor_id": "adxl345-001",
        "sensor_type": "accelerometer",
        "values": {
          "x_g": 0.012,
          "y_g": -0.003,
          "z_g": 1.001,
          "rms_g": 1.001
        },
        "unit_map": {
          "x_g": "g",
          "y_g": "g",
          "z_g": "g",
          "rms_g": "g"
        }
      }
    ],
    "aggregation": {
      "method": "mean",
      "window_seconds": 60,
      "sample_count": 100
    }
  }
}
```

### 3.4 ONTAP テレメトリ (ontap_telemetry)

PoC #2: ONTAP REST API から収集したパフォーマンスメトリクス:

```json
{
  "schema_version": "1.0",
  "message_id": "d4e5f6a7-b8c9-0123-defa-456789012345",
  "device_id": "rpi5-001",
  "timestamp": "2026-05-29T10:30:00.000Z",
  "message_type": "ontap_telemetry",
  "payload": {
    "cluster": {
      "name": "edge-cluster-01",
      "ontap_version": "9.15.1"
    },
    "metrics_type": "volume_performance",
    "collection_interval_seconds": 60,
    "volumes": [
      {
        "name": "inspection_images",
        "svm": "svm-iot",
        "metrics": {
          "iops_read": 120,
          "iops_write": 45,
          "iops_total": 165,
          "throughput_read_mbps": 15.2,
          "throughput_write_mbps": 5.8,
          "latency_read_us": 850,
          "latency_write_us": 1200,
          "capacity_used_bytes": 1073741824,
          "capacity_total_bytes": 4294967296,
          "capacity_used_percent": 25.0
        }
      }
    ],
    "node_metrics": {
      "cpu_utilization_percent": 35.2,
      "memory_utilization_percent": 62.1
    }
  }
}
```

---

## 4. S3 パーティション設計

### 4.1 バケット構造

```
s3://<bucket-name>/
├── raw/                              # 原本データ（変更不可）
│   ├── image_capture/
│   │   └── year=YYYY/month=MM/day=DD/device=<device-id>/
│   │       └── <timestamp>_<device-id>_<capture-type>.jpg
│   ├── sensor_reading/
│   │   └── year=YYYY/month=MM/day=DD/device=<device-id>/
│   │       └── <timestamp>_<device-id>.json
│   └── ontap_telemetry/
│       └── year=YYYY/month=MM/day=DD/cluster=<cluster-name>/
│           └── <timestamp>_<cluster-name>.json
├── processed/                        # ETL 処理済み（Parquet）
│   ├── image_analysis/
│   │   └── year=YYYY/month=MM/day=DD/
│   │       └── part-00000.parquet
│   ├── sensor_aggregated/
│   │   └── year=YYYY/month=MM/day=DD/
│   │       └── part-00000.parquet
│   └── ontap_metrics/
│       └── year=YYYY/month=MM/day=DD/
│           └── part-00000.parquet
└── curated/                          # BI/ML 用に最適化
    ├── print_quality_summary/
    │   └── year=YYYY/month=MM/
    │       └── summary.parquet
    └── ontap_health_score/
        └── year=YYYY/month=MM/
            └── health.parquet
```

### 4.2 パーティション選択の根拠

| パーティションキー | 理由 |
|------------------|------|
| `year/month/day` | 時系列クエリの基本軸。Athena のパーティションプルーニングで不要データのスキャンを回避 |
| `device` (raw層) | デバイス別のデータ確認・トラブルシュートに必要 |
| `cluster` (ONTAP) | 複数 ONTAP クラスタ対応時のフィルタリング |

### 4.3 ファイル命名規則

```
# 画像
{ISO8601_timestamp}_{device_id}_{capture_type}.{ext}
例: 20260529T103000Z_rpi5-001_print-monitor.jpg

# JSON メッセージ
{ISO8601_timestamp}_{device_id}.json
例: 20260529T103000Z_rpi5-001.json

# Parquet (ETL出力)
part-{sequence}.parquet
例: part-00000.parquet
```

---

## 5. Glue Data Catalog テーブル定義

### 5.1 データベース

```
Database: edge_to_cloud_ai
```

### 5.2 テーブル一覧

| テーブル名 | ソース | フォーマット | パーティション |
|-----------|--------|------------|--------------|
| `raw_image_metadata` | raw/image_capture/ | JSON (メタデータのみ) | year, month, day, device |
| `raw_sensor_readings` | raw/sensor_reading/ | JSON | year, month, day, device |
| `raw_ontap_telemetry` | raw/ontap_telemetry/ | JSON | year, month, day, cluster |
| `processed_image_analysis` | processed/image_analysis/ | Parquet | year, month, day |
| `processed_sensor_aggregated` | processed/sensor_aggregated/ | Parquet | year, month, day |
| `processed_ontap_metrics` | processed/ontap_metrics/ | Parquet | year, month, day |
| `curated_print_quality` | curated/print_quality_summary/ | Parquet | year, month |
| `curated_ontap_health` | curated/ontap_health_score/ | Parquet | year, month |

### 5.3 Athena クエリ例

```sql
-- 直近7日間の印刷品質異常サマリー
SELECT
  date_format(from_iso8601_timestamp(timestamp), '%Y-%m-%d') AS date,
  count(*) AS total_captures,
  count_if(result.status = 'anomaly_detected') AS anomalies,
  round(count_if(result.status = 'anomaly_detected') * 100.0 / count(*), 1) AS anomaly_rate_pct
FROM processed_image_analysis
WHERE year = '2026' AND month = '05' AND day >= '23'
GROUP BY 1
ORDER BY 1 DESC;

-- ONTAP ボリューム容量トレンド（日次）
SELECT
  date_format(from_iso8601_timestamp(timestamp), '%Y-%m-%d') AS date,
  volumes[1].name AS volume_name,
  avg(volumes[1].metrics.capacity_used_percent) AS avg_used_pct,
  max(volumes[1].metrics.capacity_used_percent) AS max_used_pct
FROM processed_ontap_metrics
WHERE year = '2026' AND month = '05'
GROUP BY 1, 2
ORDER BY 1;

-- デバイス別センサー異常値検出
SELECT
  device_id,
  timestamp,
  readings[1].values.temperature_celsius AS temp
FROM raw_sensor_readings
WHERE year = '2026' AND month = '05'
  AND readings[1].values.temperature_celsius > 40.0
ORDER BY timestamp DESC
LIMIT 100;

-- 週次 AI 精度レポート（フィードバックデータから算出）
SELECT
  date_format(from_iso8601_timestamp(timestamp), '%Y-W%v') AS week,
  count(*) AS total_feedback,
  count_if(correct = true) AS correct_count,
  count_if(feedback_type = 'true_positive') AS tp,
  count_if(feedback_type = 'false_positive') AS fp,
  count_if(feedback_type = 'true_negative') AS tn,
  count_if(feedback_type = 'false_negative') AS fn,
  round(count_if(correct = true) * 100.0 / count(*), 1) AS accuracy_pct,
  round(count_if(feedback_type = 'true_positive') * 100.0 /
    nullif(count_if(feedback_type = 'true_positive') + count_if(feedback_type = 'false_positive'), 0), 1) AS precision_pct,
  round(count_if(feedback_type = 'true_positive') * 100.0 /
    nullif(count_if(feedback_type = 'true_positive') + count_if(feedback_type = 'false_negative'), 0), 1) AS recall_pct
FROM feedback
GROUP BY 1
ORDER BY 1 DESC
LIMIT 12;
```

---

## 6. データライフサイクル

| 層 | 保持期間 | ストレージクラス | 用途 |
|----|---------|----------------|------|
| **raw/** | 90日 (S3 Standard) → 1年 (S3 IA) → 3年 (Glacier) | S3 Lifecycle Policy | 原本保全、監査、再処理 |
| **processed/** | 1年 (S3 Standard) → 3年 (S3 IA) | S3 Lifecycle Policy | 日常分析、ダッシュボード |
| **curated/** | 無期限 (S3 Standard) | — | BI、ML学習データ、レポート |

### ライフサイクルポリシー (例)

```json
{
  "Rules": [
    {
      "ID": "raw-lifecycle",
      "Filter": { "Prefix": "raw/" },
      "Status": "Enabled",
      "Transitions": [
        { "Days": 90, "StorageClass": "STANDARD_IA" },
        { "Days": 365, "StorageClass": "GLACIER" }
      ],
      "Expiration": { "Days": 1095 }
    },
    {
      "ID": "processed-lifecycle",
      "Filter": { "Prefix": "processed/" },
      "Status": "Enabled",
      "Transitions": [
        { "Days": 365, "StorageClass": "STANDARD_IA" }
      ],
      "Expiration": { "Days": 1095 }
    }
  ]
}
```

---

## 7. データ品質チェック

| チェック項目 | 実装場所 | アクション |
|------------|---------|-----------|
| JSON スキーマバリデーション | Lambda (取り込み時) | 不正メッセージを DLQ に退避 |
| 画像ファイルサイズ (0 byte / 上限超過) | Lambda (取り込み時) | アラート + 再撮影リクエスト |
| センサー値の物理的妥当性 (温度: -40〜85°C) | Lambda (取り込み時) | 範囲外は `quality_flag: "suspect"` を付与 |
| タイムスタンプの妥当性 (未来日付、24h以上前) | Lambda (取り込み時) | `quality_flag: "timestamp_suspect"` を付与 |
| 重複メッセージ検出 (message_id) | Kinesis deduplication / DynamoDB | 重複は破棄 |
| Parquet ファイルの行数ゼロ | Glue Job 後処理 | CloudWatch Alarm |

---

## 8. スキーマ進化ルール

| ルール | 説明 |
|--------|------|
| フィールド追加は後方互換 | 新フィールドは optional として追加。既存の consumer は影響なし |
| フィールド削除は非推奨 | deprecated マーク → 2バージョン後に削除 |
| 型変更は禁止 | 新フィールド名で追加し、旧フィールドを deprecated に |
| `schema_version` のインクリメント | MINOR: フィールド追加。MAJOR: 破壊的変更（新テーブル作成） |
| Glue Schema Registry | 将来的に Avro/JSON Schema を登録し、自動バリデーション |
