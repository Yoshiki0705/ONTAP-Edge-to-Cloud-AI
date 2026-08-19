# Kafka Integration Design

> Created: 2026-06-15
> Status: Preparing (awaiting Managed Kafka deployment)

---

## 1. Overview

Design the connection from edge devices (Raspberry Pi) → Kafka → ClickHouse.
Kafka + ClickHouse are provided as a managed open source platform (on-premises VM deployment).

---

## 2. Deployment Topology

```
[Edge Site LAN]
+------------------------------------------------------+
|                                                      |
|  [Pi 5]        [Hypervisor host]                     |
|     |          +---------------------------+         |
|     |          | Kafka VM      (managed)   |         |
|     |          | ClickHouse VM (managed)   |         |
|     |          +---------------------------+         |
|     |                    |                           |
|     +----[LAN]-----------+                           |
|                          |                           |
|  [ONTAP storage system]  |                           |
|  NFS: vol_images   ------+                           |
|  S3: backup bucket (ClickHouse backup)               |
|                                                      |
+------------------------------------------------------+
```

### Network Requirements

| Connection | Protocol | Port | Direction |
|-----------|----------|------|----------|
| Pi → Kafka | TCP | 9092 (plaintext) or 9093 (TLS) | outbound |
| Pi → ONTAP NFS | TCP | 2049 | outbound |
| Kafka → ClickHouse | TCP | 9000/8123 | internal (inter-VM) |
| ClickHouse → ONTAP S3 | TCP | 443 (HTTPS) | backup |

---

## 3. Edge-Side Kafka Configuration

### 3.1 Connection Settings (.env)

```bash
# Set these when Kafka broker is available
KAFKA_ENABLED=true
KAFKA_BOOTSTRAP_SERVERS=<kafka-vm-ip>:9092

# If TLS is enabled (recommended)
# KAFKA_SECURITY_PROTOCOL=SSL
# KAFKA_SSL_CA_LOCATION=/etc/ssl/certs/kafka-ca.pem
```

### 3.2 Topic Design

| Topic | Partition Key | Content |
|-------|--------------|--------|
| `factory.events.raw` | `site_id-equipment_id` | All events (primary) |
| `factory.events.quality` | `event_id` | AI analysis results |
| `factory.events.anomaly` | `event_id` | Anomaly detections |
| `factory.events.dlq` | — | Processing failures |

### 3.3 Event Flow

```
Pi: simple_capture.py
  -> Save image to ONTAP NFS
  -> Publish payload_arrival event to Kafka (factory.events.raw)
  -> (optional) Invoke Lambda for AI analysis
  -> Publish quality_event to Kafka (factory.events.quality)

ClickHouse:
  -> Consume from kafka_events_raw table
  -> Materialized Views for rollup / anomaly detection
  -> payload_manifest table manages ONTAP file references
```

---

## 4. Disconnection Resilience

| State | Behavior |
|-------|----------|
| Kafka healthy | Events published immediately |
| Kafka unreachable | Buffer locally (`/tmp/kafka-buffer/`) as JSON files |
| Kafka recovered | `replay_buffer()` replays in chronological order |
| ONTAP healthy | Images/results always saved to ONTAP NFS (independent of Kafka state) |

**Important**: ONTAP writes are independent of Kafka state. Payload storage always succeeds; only metadata events depend on Kafka.

---

## 5. ONTAP S3 (ClickHouse Backup Target)

ONTAP S3 protocol used as ClickHouse backup destination:

```
# ONTAP configuration
# 1. Create S3 SVM
vserver create -vserver svm-s3 -subtype default

# 2. Enable S3 service
vserver object-store-server create -vserver svm-s3 -object-store-server s3-backup

# 3. Create bucket
vserver object-store-server bucket create -vserver svm-s3 -bucket clickhouse-backup

# 4. Create user + policy
vserver object-store-server user create -vserver svm-s3 -user clickhouse-backup-user
vserver object-store-server bucket policy statement create ...
```

---

## 6. Validation Plan

### Phase 1: Connectivity Verification (after Kafka deployment)

```bash
# Test Kafka connectivity from Pi
python3 -c "
from confluent_kafka import Producer
p = Producer({'bootstrap.servers': '<kafka-vm-ip>:9092'})
p.produce('test-topic', key='test', value='hello from pi')
p.flush()
print('OK')
"
```

### Phase 2: E2E Test

```bash
# Pi capture -> Kafka publish -> ClickHouse verification
KAFKA_ENABLED=true KAFKA_BOOTSTRAP_SERVERS=<ip>:9092 \
  python3 simple_capture.py --no-analyze

# Verify in ClickHouse
clickhouse-client --query "SELECT count() FROM kafka_events_raw WHERE source_id = 'rpi5-001'"
```

### Phase 3: Anomaly Detection Demo

```bash
# Continuous capture -> AI analysis -> anomaly detection -> ClickHouse dashboard
KAFKA_ENABLED=true S3_BUCKET=<bucket> \
  python3 simple_capture.py --loop
```

---

## 7. Open Items

| Item | Status | Dependency |
|------|--------|------------|
| Kafka VM IP address | Waiting | Managed platform deployment |
| TLS certificates | Waiting | PoC documentation approval |
| ONTAP S3 bucket creation | In progress | ONTAP access |
| ClickHouse table DDL | Being designed in Lakehouse project | v3 schema finalization |
