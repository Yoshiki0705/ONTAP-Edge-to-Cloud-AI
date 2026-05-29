# Data Schema Design

> Created: 2026-05-29  
> Scope: PoC #1 (3D Print Quality Monitoring) / PoC #2 (ONTAP Telemetry)  
> Status: Draft

---

## 1. Design Principles

| Principle | Rationale |
|-----------|-----------|
| JSON as standard message format | Compatibility with SORACOM / AWS IoT Core / Kinesis |
| S3 stores Parquet (analytics) + raw JSON/JPEG (archive) | Balance between Athena query performance and data preservation |
| Partition by date + device ID | Supports both time-series queries and per-device filtering |
| Introduce schema versioning | Enable field additions while maintaining backward compatibility |
| UTC timestamps as standard | Prevent timezone confusion |

---

## 2. Message Envelope (Common)

All IoT messages follow this common envelope:

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

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | ✅ | Semantic version (MAJOR.MINOR) |
| `message_id` | string (UUID v4) | ✅ | Unique message identifier |
| `device_id` | string | ✅ | Device identifier (naming: `{type}-{seq}`) |
| `timestamp` | string (ISO 8601) | ✅ | UTC timestamp |
| `message_type` | enum | ✅ | Payload type |
| `payload` | object | ✅ | Message-type-specific data |

---

## 3. Payload Schemas

### 3.1 Image Capture (image_capture)

Used in PoC #1: 3D Print Quality Monitoring.

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

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image.s3_key` | string | ✅ | Image path on S3 |
| `image.format` | enum (jpeg/png) | ✅ | Image format |
| `image.resolution` | string | ✅ | Resolution (WxH) |
| `image.size_bytes` | integer | ✅ | File size |
| `image.compression_quality` | integer (1-100) | ✅ | JPEG compression quality |
| `capture_context.trigger` | enum | ✅ | scheduled / event / manual |
| `capture_context.interval_seconds` | integer | ○ | Periodic capture interval |
| `print_context.job_id` | string | ○ | Print job ID |
| `print_context.layer_current` | integer | ○ | Current layer |
| `print_context.nozzle_temp_celsius` | number | ○ | Nozzle temperature |

### 3.2 AI Analysis Result (analysis_result)

Results from Bedrock Claude Vision / Rekognition analysis:

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

### 3.3 Sensor Data (sensor_reading)

Environmental sensor / vibration sensor readings:

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

### 3.4 ONTAP Telemetry (ontap_telemetry)

PoC #2: Performance metrics collected from ONTAP REST API:

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

## 4. S3 Partition Design

### 4.1 Bucket Structure

```
s3://<bucket-name>/
├── raw/                              # Original data (immutable)
│   ├── image_capture/
│   │   └── year=YYYY/month=MM/day=DD/device=<device-id>/
│   │       └── <timestamp>_<device-id>_<capture-type>.jpg
│   ├── sensor_reading/
│   │   └── year=YYYY/month=MM/day=DD/device=<device-id>/
│   │       └── <timestamp>_<device-id>.json
│   └── ontap_telemetry/
│       └── year=YYYY/month=MM/day=DD/cluster=<cluster-name>/
│           └── <timestamp>_<cluster-name>.json
├── processed/                        # ETL output (Parquet)
│   ├── image_analysis/
│   │   └── year=YYYY/month=MM/day=DD/
│   │       └── part-00000.parquet
│   ├── sensor_aggregated/
│   │   └── year=YYYY/month=MM/day=DD/
│   │       └── part-00000.parquet
│   └── ontap_metrics/
│       └── year=YYYY/month=MM/day=DD/
│           └── part-00000.parquet
└── curated/                          # Optimized for BI/ML
    ├── print_quality_summary/
    │   └── year=YYYY/month=MM/
    │       └── summary.parquet
    └── ontap_health_score/
        └── year=YYYY/month=MM/
            └── health.parquet
```

### 4.2 Partition Key Rationale

| Partition Key | Rationale |
|--------------|-----------|
| `year/month/day` | Primary axis for time-series queries. Enables Athena partition pruning to skip unnecessary data scans |
| `device` (raw layer) | Required for per-device data inspection and troubleshooting |
| `cluster` (ONTAP) | Filtering when supporting multiple ONTAP clusters |

### 4.3 File Naming Convention

```
# Images
{ISO8601_timestamp}_{device_id}_{capture_type}.{ext}
Example: 20260529T103000Z_rpi5-001_print-monitor.jpg

# JSON messages
{ISO8601_timestamp}_{device_id}.json
Example: 20260529T103000Z_rpi5-001.json

# Parquet (ETL output)
part-{sequence}.parquet
Example: part-00000.parquet
```

---

## 5. Glue Data Catalog Table Definitions

### 5.1 Database

```
Database: edge_to_cloud_ai
```

### 5.2 Table List

| Table Name | Source | Format | Partitions |
|-----------|--------|--------|-----------|
| `raw_image_metadata` | raw/image_capture/ | JSON (metadata only) | year, month, day, device |
| `raw_sensor_readings` | raw/sensor_reading/ | JSON | year, month, day, device |
| `raw_ontap_telemetry` | raw/ontap_telemetry/ | JSON | year, month, day, cluster |
| `processed_image_analysis` | processed/image_analysis/ | Parquet | year, month, day |
| `processed_sensor_aggregated` | processed/sensor_aggregated/ | Parquet | year, month, day |
| `processed_ontap_metrics` | processed/ontap_metrics/ | Parquet | year, month, day |
| `curated_print_quality` | curated/print_quality_summary/ | Parquet | year, month |
| `curated_ontap_health` | curated/ontap_health_score/ | Parquet | year, month |

### 5.3 Athena Query Examples

```sql
-- Print quality anomaly summary for last 7 days
SELECT
  date_format(from_iso8601_timestamp(timestamp), '%Y-%m-%d') AS date,
  count(*) AS total_captures,
  count_if(result.status = 'anomaly_detected') AS anomalies,
  round(count_if(result.status = 'anomaly_detected') * 100.0 / count(*), 1) AS anomaly_rate_pct
FROM processed_image_analysis
WHERE year = '2026' AND month = '05' AND day >= '23'
GROUP BY 1
ORDER BY 1 DESC;

-- ONTAP volume capacity trend (daily)
SELECT
  date_format(from_iso8601_timestamp(timestamp), '%Y-%m-%d') AS date,
  volumes[1].name AS volume_name,
  avg(volumes[1].metrics.capacity_used_percent) AS avg_used_pct,
  max(volumes[1].metrics.capacity_used_percent) AS max_used_pct
FROM processed_ontap_metrics
WHERE year = '2026' AND month = '05'
GROUP BY 1, 2
ORDER BY 1;

-- Per-device sensor anomaly detection
SELECT
  device_id,
  timestamp,
  readings[1].values.temperature_celsius AS temp
FROM raw_sensor_readings
WHERE year = '2026' AND month = '05'
  AND readings[1].values.temperature_celsius > 40.0
ORDER BY timestamp DESC
LIMIT 100;

-- Weekly AI accuracy report (calculated from feedback data)
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

## 6. Data Lifecycle

| Layer | Retention | Storage Class | Purpose |
|-------|-----------|--------------|---------|
| **raw/** | 90 days (S3 Standard) → 1 year (S3 IA) → 3 years (Glacier) | S3 Lifecycle Policy | Original preservation, audit, reprocessing |
| **processed/** | 1 year (S3 Standard) → 3 years (S3 IA) | S3 Lifecycle Policy | Daily analytics, dashboards |
| **curated/** | Indefinite (S3 Standard) | — | BI, ML training data, reports |

### Lifecycle Policy (Example)

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

## 7. Data Quality Checks

| Check | Implementation Point | Action |
|-------|---------------------|--------|
| JSON schema validation | Lambda (at ingestion) | Route invalid messages to DLQ |
| Image file size (0 byte / exceeds limit) | Lambda (at ingestion) | Alert + re-capture request |
| Sensor value physical validity (temp: -40~85°C) | Lambda (at ingestion) | Out-of-range values get `quality_flag: "suspect"` |
| Timestamp validity (future date, >24h old) | Lambda (at ingestion) | Add `quality_flag: "timestamp_suspect"` |
| Duplicate message detection (message_id) | Kinesis deduplication / DynamoDB | Discard duplicates |
| Parquet file zero rows | Glue Job post-processing | CloudWatch Alarm |

---

## 8. Schema Evolution Rules

| Rule | Description |
|------|-------------|
| Field additions are backward-compatible | New fields added as optional. Existing consumers unaffected |
| Field removal is deprecated-first | Mark deprecated → remove after 2 versions |
| Type changes are prohibited | Add new field name, deprecate old field |
| `schema_version` increment | MINOR: field addition. MAJOR: breaking change (new table created) |
| Glue Schema Registry | Future: register Avro/JSON Schema for automated validation |
