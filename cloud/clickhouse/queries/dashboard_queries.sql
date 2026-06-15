-- ClickHouse Dashboard Queries
-- For use with Grafana, Superset, or direct ClickHouse client

-- Q1: Quality trend (last 24h, per equipment)
SELECT
    toStartOfHour(timestamp) AS hour,
    equipment_id,
    count() AS total_inspections,
    countIf(verdict = 'anomaly_detected') AS anomalies,
    round(countIf(verdict = 'anomaly_detected') * 100.0 / count(), 1) AS anomaly_rate_pct
FROM quality_events
WHERE timestamp > now() - INTERVAL 24 HOUR
GROUP BY hour, equipment_id
ORDER BY hour DESC, equipment_id;

-- Q2: Recent anomalies with payload reference (for image lookup)
SELECT
    a.timestamp,
    a.equipment_id,
    a.anomaly_type,
    a.severity,
    p.payload_uri,
    p.size_bytes
FROM anomaly_events a
LEFT JOIN payload_manifest p ON a.trigger_event_id = p.event_id
WHERE a.timestamp > now() - INTERVAL 1 HOUR
ORDER BY a.timestamp DESC
LIMIT 20;

-- Q3: Sensor environment overview (last hour, 1-min resolution)
SELECT
    minute,
    sensor_id,
    avg_value_1 AS avg_temp_c,
    avg_value_2 AS avg_humidity_pct
FROM sensor_events_rollup_1m
WHERE minute > now() - INTERVAL 1 HOUR
ORDER BY minute DESC, sensor_id;

-- Q4: Payload manifest — recent files stored in ONTAP
SELECT
    timestamp,
    equipment_id,
    sensor_id,
    payload_type,
    payload_uri,
    size_bytes
FROM payload_manifest
WHERE timestamp > now() - INTERVAL 1 HOUR
ORDER BY timestamp DESC
LIMIT 50;

-- Q5: Dead letter events (debugging)
SELECT
    ingest_time,
    error_reason,
    source_topic,
    substring(raw_payload, 1, 200) AS payload_preview
FROM dead_letter_events
WHERE ingest_time > now() - INTERVAL 24 HOUR
ORDER BY ingest_time DESC
LIMIT 20;

-- Q6: Ingest rate (events per minute, last hour)
SELECT
    toStartOfMinute(timestamp) AS minute,
    count() AS events_per_minute,
    uniq(equipment_id) AS active_equipment
FROM kafka_events_raw
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY minute
ORDER BY minute DESC;
