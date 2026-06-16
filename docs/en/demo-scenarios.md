# Demo Scenarios

> Created: 2026-06-16
> Scope: 3D Print Quality Monitoring PoC
> Goal: Convey value to stakeholders (internal engineers, partners, data platform teams)

---

## 0. Demo Design Principles

- **Value in 30 seconds**: Show "printing → anomaly occurs → instant alert"
- **Don't over-engineer**: Live demos can fail. Prepare both recorded and live versions
- **Tailor by audience**: Results for executives, mechanics for engineers

---

## Demo 1: 30-Second Quality Anomaly Detection (Main Demo)

### Goal
Show in 30 seconds: "When an anomaly occurs on an unattended 3D printer, AI automatically detects it and sends an alert."

### Cast
- Presenter (operates)
- Audience (internal engineers / partners / customers)

### Preparation
| Item | Status |
|------|--------|
| Pi + camera capturing the 3D printer | Running |
| `simple_capture.py --loop` running | Running |
| ClickHouse dashboard (Grafana) displayed | Screen share |
| Slack / SNS alert screen | Screen share |
| Means to trigger anomaly (remove filament or known-failure model) | Prepared |

### Timeline (30 seconds)

| Time | Action | Screen |
|------|--------|--------|
| 0-5s | "Printing normally. Camera captures every 60s, AI judges." | Dashboard shows green "normal" |
| 5-10s | Trigger anomaly (remove filament / switch to failure model) | Printer state changes |
| 10-25s | Next capture → ONTAP save → Lambda → Bedrock analysis | Red "anomaly_detected" appears |
| 25-30s | Slack alert notification arrives | Notification + anomaly image + recommended action |

### Key Points That Resonate
- **Data accumulates locally (ONTAP)** while only AI inference is in the cloud
- **No custom model training** (prompt only)
- **Anomaly image + recommended action** delivered together

### Fallback on Failure
- If live anomaly not detected → play recorded version
- Network issues → manually invoke Lambda with pre-captured image

---

## Demo 2: Disconnection Recovery (Resilience)

### Goal
Show that "data is not lost even when the factory network is unstable."

### Timeline (2 minutes)

| Time | Action | Expected Behavior |
|------|--------|-------------------|
| 0:00 | Confirm normal operation (publishing to Kafka) | Events flow into dashboard |
| 0:20 | Stop Kafka broker (`docker stop kafka` or VM stop) | Publish fails |
| 0:30 | Capture continues. Log shows "buffered" | JSON accumulates in local buffer |
| 0:50 | Show buffer directory (`ls /tmp/kafka-buffer/`) | Files increasing |
| 1:00 | Restart Kafka broker | Broker recovers |
| 1:10 | Run `replay_buffer()` (or auto-replay) | Buffer → Kafka in chronological order |
| 1:30 | Check dashboard | Disconnected data arrives without loss |
| 2:00 | Confirm dead_letter_events is empty | Zero data loss |

### Key Points That Resonate
- **ONTAP saves are unaffected by disconnection** (NFS is local LAN)
- **Kafka outage = auto-buffer → replay on recovery**
- **Idempotence (event_id dedup) means no duplicates on replay**

### Verification Command
```bash
# Confirm event counts match before/after disconnection
clickhouse-client --query "
  SELECT count(), uniqExact(event_id)
  FROM kafka_events_raw
  WHERE timestamp BETWEEN '<demo_start>' AND '<demo_end>'
"
# count() == uniqExact(event_id) means no duplicates
```

---

## Demo 3: Payload Reference (ONTAP ↔ Event Bridge)

### Goal
Show that "from a dashboard anomaly event, you can instantly trace back to the original image on ONTAP."

### Timeline (1 minute)

| Time | Action | Screen |
|------|--------|--------|
| 0:00 | Select an anomaly event on dashboard | anomaly_events row |
| 0:15 | JOIN payload_manifest to get payload_uri | `nfs://svm-iot/vol_images/.../image.jpg` |
| 0:30 | Open the actual image on ONTAP | Image showing the anomaly |
| 0:45 | Check how Bedrock judged the same image | quality_events verdict + confidence |

### Key Points That Resonate
- **Separation of metadata (light, fast) and payload (large)**
- **Traceability from event to original**
- **ONTAP is the source of truth for data**

### Verification Query
```sql
SELECT a.timestamp, a.anomaly_type, a.severity,
       p.payload_uri, q.confidence
FROM anomaly_events a
JOIN payload_manifest p ON a.trigger_event_id = p.event_id
JOIN quality_events q ON a.trigger_event_id = q.source_event_id
WHERE a.timestamp > now() - INTERVAL 1 HOUR
ORDER BY a.timestamp DESC;
```

---

## Demo 4: AI Accuracy Feedback Loop

### Goal
Show that "if the AI judgment is wrong, a human can correct it, and that becomes training data."

### Timeline (1.5 minutes)

| Time | Action | Screen |
|------|--------|--------|
| 0:00 | Show a false-positive example (normal but judged anomaly) | quality_events |
| 0:20 | Send feedback to feedback_recorder (correct=false) | API call |
| 0:40 | Recorded in feedback_events | ClickHouse |
| 1:00 | Run weekly accuracy report query | accuracy / precision / recall |
| 1:20 | Explain this label flows into training_features | Databricks Gold dataset |

### Key Points That Resonate
- **AI judgment is assistive, not final** (human in the loop)
- **Feedback directly connects to training dataset** (to Databricks)
- **Accuracy can be continuously measured and improved**

---

## Demo Environment Checklist

### Before Live Demo (30 min prior)
- [ ] Pi + camera running, capturing
- [ ] `simple_capture.py --loop` running
- [ ] Kafka broker running, ClickHouse ingestion confirmed
- [ ] Grafana dashboard displayable
- [ ] Slack / SNS notifications working
- [ ] Anomaly trigger prepared (filament or failure model)
- [ ] Recorded version ready to play (fallback)

### After Demo
- [ ] Tag demo-generated data with `is_synthetic` or demo tag
- [ ] Clear buffer (`/tmp/kafka-buffer/`)
- [ ] Reset dashboard to pre-demo state

---

## Demo Data vs Production Data

Distinguish demo data with the `is_synthetic` flag or a dedicated `site_id = "demo"`,
to avoid contaminating production quality metrics.

```bash
# Run with overridden site_id for demo
SITE_ID=demo python3 simple_capture.py --loop
```
