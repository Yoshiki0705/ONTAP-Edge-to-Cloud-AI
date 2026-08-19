# Operations Design: SLI/SLO, Observability, AI Evaluation, Runbook

> Created: 2026-05-29
> Scope: PoC #1 (3D Print Quality Monitoring) / PoC #2 (ONTAP Telemetry)
> Status: Draft
> Review personas: Observability/SRE Advocate, Data+AI Architect, Analytics Architect

---

## 1. SLI / SLO Definitions

### 1.1 Service Level Indicators (SLI)

| SLI | Definition | Measurement | Scope |
|-----|-----------|-------------|-------|
| Capture success rate | Proportion of successful capture attempts | `captures_success / captures_total` | Edge (Pi) |
| NFS write success rate | Proportion of successful NFS write attempts | `nfs_writes_success / nfs_writes_total` | Edge → ONTAP |
| Analysis response time | Time from image upload to alert issuance | Lambda Duration + Bedrock latency | Cloud |
| Alert delivery success rate | Proportion of SNS publishes successfully delivered | `sns_delivered / sns_published` | Cloud |
| Device uptime | Proportion of expected health reports received | `heartbeats_received / heartbeats_expected` | Edge |

### 1.2 Service Level Objectives (SLO)

| SLO | Target | Measurement Period | Error Budget |
|-----|--------|-------------------|--------------|
| Capture success rate | ≥ 99.5% | 30 days | 7.2 hours/month downtime allowed |
| NFS write success rate | ≥ 99.0% | 30 days | 14.4 hours/month (absorbed by local buffer) |
| Analysis response (p95) | ≤ 30 seconds | 30 days | 5% of requests may exceed 30s |
| Alert delivery success rate | ≥ 99.9% | 30 days | 43 seconds/month delivery failure allowed |
| Device uptime | ≥ 95.0% | 30 days | 36 hours/month downtime allowed |

### 1.3 SLO Violation Actions

| SLO | Action on Violation |
|-----|-------------------|
| Capture success < 99.5% | Check camera connection, reboot Pi, consider camera replacement |
| Upload success < 99.0% | Check NFS mount, verify ONTAP status, check network |
| Analysis response > 30s (p95) | Check Bedrock throttling, optimize image size |
| Device uptime < 95.0% | Check Pi hardware, power stability, OS updates |

---

## 2. Metrics Design

### 2.1 Business Metrics (CloudWatch Custom Metrics)

| Metric Name | Unit | Description | Alarm Condition |
|------------|------|-------------|----------------|
| `PrintQuality/AnomalyRate` | Percent | Anomaly detection rate (last 1 hour) | > 30% notify (possible printer issue) |
| `PrintQuality/QualityScore` | None (0-100) | Average quality score (last 1 hour) | < 50 notify |
| `PrintQuality/CaptureGap` | Seconds | Time since last capture | > 300s (5 min) device-down alert |
| `PrintQuality/CostPerImage` | USD | Analysis cost per image | > $0.02 cost anomaly alert |
| `ONTAP/CapacityUsedPercent` | Percent | Volume utilization | > 80% capacity warning |
| `ONTAP/LatencyP95` | Microseconds | Latency p95 | > 5000μs performance warning |

### 2.2 Technical Metrics (Existing CloudWatch)

| Metric | Source | Purpose |
|--------|--------|---------|
| Lambda Invocations/Errors/Duration | AWS/Lambda | Processing pipeline health |
| Kinesis IncomingRecords/Bytes | AWS/Kinesis | Data ingestion volume |
| S3 BucketSizeBytes/NumberOfObjects | AWS/S3 | Storage growth rate |
| SNS NumberOfMessagesPublished | AWS/SNS | Alert frequency |

### 2.3 Correlation ID Design

Include `message_id` in all logs and metrics for cross-service tracing:

```
[Pi: capture] message_id=abc-123 →
[ONTAP: NFS write] message_id=abc-123 →
[Lambda: analyze] message_id=abc-123 →
[Bedrock: invoke] message_id=abc-123 →
[SNS: alert] message_id=abc-123
```

**CloudWatch Logs Insights query example:**
```
fields @timestamp, @message
| filter message_id = "abc-123"
| sort @timestamp asc
```

---

## 3. AI Accuracy Feedback Loop

### 3.1 Problem

AI analysis accuracy may degrade over time (printer changes, filament changes, lighting changes). Continuous accuracy evaluation and feedback is required.

### 3.2 Feedback Loop Design

```
[Image Capture] → [AI Analysis] → [Result Storage]
                                        ↓
                                [Operator Review]
                                        ↓
                                [Feedback Recording]
                                ├── Correct (True Positive / True Negative)
                                └── Incorrect (False Positive / False Negative)
                                        ↓
                                [Weekly Accuracy Report]
                                        ↓
                                [Prompt Improvement / Threshold Adjustment]
```

### 3.3 Feedback Record Schema

```json
{
  "feedback_id": "uuid",
  "source_message_id": "message_id of analyzed image",
  "timestamp": "2026-05-29T12:00:00Z",
  "ai_prediction": {
    "status": "anomaly_detected",
    "confidence": 0.87,
    "anomaly_type": "stringing"
  },
  "human_judgment": {
    "correct": false,
    "actual_status": "normal",
    "notes": "Lighting reflection misidentified as stringing"
  },
  "feedback_type": "false_positive"
}
```

### 3.4 Accuracy Metrics (Weekly Calculation)

| Metric | Formula | Target |
|--------|---------|--------|
| Precision | TP / (TP + FP) | ≥ 90% |
| Recall | TP / (TP + FN) | ≥ 80% |
| F1 Score | 2 × (P × R) / (P + R) | ≥ 85% |
| False Positive Rate | FP / (FP + TN) | ≤ 10% |

### 3.5 Actions on Accuracy Degradation

| Situation | Action |
|-----------|--------|
| FP rate > 10% | Strengthen "conservative detection" in prompt, raise confidence threshold |
| Recall < 80% | Add missed pattern examples to prompt |
| New defect type appears | Add new type to prompt, add test cases |
| Environment change (lighting, camera position) | Re-test with calibration images |

---

## 4. Data Lineage + Medallion Architecture

### 4.1 Medallion Mapping

| Project Layer | Medallion | Description |
|--------------|-----------|-------------|
| `raw/` | Bronze | Original data. Immutable. As-arrived format |
| `processed/` | Silver | Cleansed and structured. Parquet conversion, schema applied |
| `curated/` | Gold | Optimized for business use. Aggregations, summaries, ML features |

### 4.2 Data Lineage Tracking

```
[Bronze: raw/image_capture/]
    │ message_id: abc-123
    │ s3_key: raw/image_capture/year=2026/.../image.jpg
    ↓
[Silver: processed/image_analysis/]
    │ source_message_id: abc-123 (← reference to Bronze)
    │ analyzer: bedrock/claude-sonnet-4.5
    │ result: anomaly_detected
    ↓
[Gold: curated/print_quality_summary/]
    │ aggregation: daily summary
    │ source: processed/image_analysis/ (date partition)
    ↓
[Action: SNS Alert / Dashboard / Feedback]
```

### 4.3 Lineage Metadata

Each record includes:

| Field | Layer | Description |
|-------|-------|-------------|
| `message_id` | Bronze | Original unique ID |
| `source_message_id` | Silver | Reference to Bronze record |
| `processing_timestamp` | Silver/Gold | Processing datetime |
| `processing_job_id` | Silver/Gold | Glue Job Run ID |
| `schema_version` | All layers | Schema version |

---

## 5. Runbook

### 5.1 Alert: Device Down (CaptureGap > 5 minutes)

```
Symptom: No captures received for 5+ minutes
Impact: Cannot detect anomalies during printing

Steps:
1. Check device online status in SORACOM console
   → Offline: Go to Step 2
   → Online: Go to Step 3

2. [Device Offline]
   a. Check power (USB-C connection, LED status)
   b. Check network (Ethernet LED, cellular LED)
   c. Attempt SSH via SORACOM Napter
   d. Cannot connect → On-site response (reboot or replace)

3. [Device Online but no captures]
   a. SSH connect: ssh iot-operator@<PI_IP>
   b. Check service: systemctl status edge-camera
   c. Check logs: journalctl -u edge-camera --since "5 min ago"
   d. Check camera: v4l2-ctl --list-devices
   e. Check disk: df -h /var/lib/edge-camera
   f. Identify issue → restart or fix config

Recovery confirmation: CaptureGap returns to ≤ 60 seconds in CloudWatch
```

### 5.2 Alert: Lambda Errors Spike (> 3 in 5 minutes)

```
Symptom: Image analysis Lambda producing consecutive errors
Impact: Anomaly detection stopped, no alerts being sent

Steps:
1. Check Lambda error logs in CloudWatch Logs
   → Bedrock throttling: Go to Step 2
   → S3 access denied: Go to Step 3
   → Timeout: Go to Step 4

2. [Bedrock throttling]
   a. Check model throttling status in Bedrock console
   b. Temporary → Wait for auto-recovery (5-10 min)
   c. Persistent → Consider Provisioned Throughput or extend capture interval

3. [S3 access denied]
   a. Verify IAM role policy
   b. Check S3 bucket policy
   c. Check KMS key policy

4. [Timeout]
   a. Check image sizes (too large?)
   b. Verify Lambda memory/timeout settings
   c. Check Bedrock response times

Recovery confirmation: Lambda Errors metric returns to 0
```

### 5.3 Alert: High Anomaly Rate (> 30% in 1 hour)

```
Symptom: Anomaly detection rate exceeds 30% in one hour
Impact: Possible real printer problem

Steps:
1. Review recent analysis results (S3 processed/image_analysis/)
   → Same anomaly_type repeating: Go to Step 2
   → Diverse anomaly_types: Go to Step 3

2. [Same type repeating]
   a. Visually inspect printer status
   b. Anomaly is real → Stop printer, address root cause
   c. False positive → Record feedback, consider prompt adjustment

3. [Diverse anomaly types]
   a. Check for camera position/lighting changes
   b. Check for filament changes
   c. Environment change → Run calibration

Recovery confirmation: Anomaly rate returns to ≤ 10%
```

### 5.4 Alert: ONTAP Capacity Warning (> 80%)

```
Symptom: ONTAP volume utilization exceeds 80%
Impact: May impact new image storage

Steps:
1. Check capacity details via ONTAP REST API
   curl -k -u svc-iot-telemetry https://<ONTAP>/api/storage/volumes?fields=space

2. Check old data
   a. Raw images > 90 days old → Verify migrated to S3
   b. Migrated → Delete old files from ONTAP
   c. Not migrated → Run SnapMirror sync first, then delete

3. If capacity addition needed
   a. Check volume auto-grow settings
   b. Check aggregate free space
   c. Add disks or expand volume as needed

Recovery confirmation: Utilization returns to ≤ 70%
```

### 5.5 Alert: Kafka Consumer Lag Increasing (lag > 10000)

```
Symptom: ClickHouse Kafka consumer lag keeps growing
Impact: Dashboard loses real-time freshness, data delay

Steps:
1. Check consumer lag in ClickHouse
   SELECT * FROM system.kafka_consumers WHERE table = 'kafka_events_queue';

2. Isolate the cause
   -> ClickHouse ingestion slow: go to Step 3
   -> Too many producers: go to Step 4

3. [ClickHouse ingestion slow]
   a. Check ClickHouse CPU/memory usage
   b. Check Materialized View execution time (system.query_log)
   c. Increase kafka_num_consumers (requires restart)
   d. Tune kafka_max_block_size

4. [Too many producers]
   a. Check edge device capture interval
   b. Look for unexpected high-frequency publishing
   c. Extend capture interval if needed

Recovery confirmation: consumer lag returns to <= 1000
```

### 5.6 Alert: Dead Letter Spike (> 1%/hour)

```
Symptom: Sudden increase in dead_letter_events writes
Impact: Events not processed normally (schema mismatch)

Steps:
1. Inspect dead letter contents
   SELECT error_reason, count() FROM dead_letter_events
   WHERE ingest_time > now() - INTERVAL 1 HOUR
   GROUP BY error_reason ORDER BY count() DESC;

2. Identify error cause
   -> JSON parse error: go to Step 3
   -> Type conversion error: go to Step 4

3. [JSON parse error]
   a. Check edge-side event_schema.py version
   b. Check schema_version field value
   c. Identify malformed producer (filter by source_id)
   d. Update the device's code

4. [Type conversion error]
   a. Inspect raw_payload for unexpected field types
   b. Reconcile with ClickHouse DDL schema
   c. Consider ALTER TABLE if schema evolution needed

Recovery confirmation: dead_letter rate returns to <= 1%
```

### 5.7 Alert: ClickHouse to ONTAP S3 Export Failure

```
Symptom: Daily training_features_export fails
Impact: Feature supply to Databricks stops, ML training data goes stale

Steps:
1. Check export script logs
   journalctl -u clickhouse-export --since "1 day ago"

2. Isolate failure cause
   -> ONTAP S3 connection error: go to Step 3
   -> ClickHouse query error: go to Step 4

3. [ONTAP S3 connection error]
   a. Verify ONTAP S3 LIF connectivity (curl -k https://<ONTAP_S3_LIF>:443)
   b. Check S3 credentials (access_key/secret_key) validity
   c. Check bucket policy
   d. If certificate error, verify CA certificate

4. [ClickHouse query error]
   a. Verify training_features_export table exists
   b. Run export query manually
   c. Check disk capacity and memory

Recovery confirmation: Next day's export succeeds, Parquet arrives in Databricks
```

### 5.8 Escalation Flow

```
[Alert Triggered]
    │
    ▼ (0-5 min)
[L1: Automated Response]
    Owner: System (auto-recovery scripts)
    Scope: Transient errors, auto-retry resolvable
    │
    │ Auto-recovery failed
    ▼ (5-15 min)
[L2: Operator Response]
    Owner: On-duty operator (notified via Slack)
    Scope: Manual actions per Runbook
    Tools: SSH, SORACOM Napter, AWS Console
    │
    │ Cannot resolve with Runbook
    ▼ (15-60 min)
[L3: Engineer Response]
    Owner: Development engineer (phone/PagerDuty)
    Scope: Code fixes, config changes, infra changes
    │
    │ Critical incident (data loss, security)
    ▼ (immediate)
[L4: Manager Decision]
    Owner: Project manager
    Scope: Service stop decision, customer notification, root cause priority
```

| Level | Response Time Target | Notification | Authority |
|-------|---------------------|-------------|-----------|
| L1 | Immediate (auto) | — | Auto scripts |
| L2 | Within 15 min | Slack | Service restart, device reboot |
| L3 | Within 1 hour | Phone/PagerDuty | Code fix, config change |
| L4 | Immediate (critical) | Phone | Service stop, customer notification |

> **PoC Phase**: Only L1-L2 operational. L3-L4 formalized at production migration.

---

## 6. Future Iceberg Migration Criteria

Currently operating with Parquet + Hive-style partitions. Consider Apache Iceberg migration when:

| Trigger Condition | Reason |
|-------------------|--------|
| Record-level Update/Delete needed | GDPR compliance, error correction |
| Concurrent writes occur | Multiple devices writing to same table |
| Frequent schema changes | Field additions/type changes more than monthly |
| Time travel (historical data access) needed | Audit, reproducibility verification |
| Data volume exceeds 1TB | Metadata management efficiency |
| Multiple query engines access data | Athena + Redshift + EMR |

**Why Iceberg is NOT needed now:**
- Append-only workload (image metadata, sensor data)
- Single write source (Amazon Data Firehose / Glue ETL)
- Small data volume (PoC: several GB/month)
- Single query engine (Athena only)
