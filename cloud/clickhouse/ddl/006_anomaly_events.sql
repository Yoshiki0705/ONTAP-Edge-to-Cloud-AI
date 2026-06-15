-- ClickHouse DDL: anomaly_events
-- Anomaly detections (threshold breaches, AI alerts)
-- Retention: 365 days

CREATE TABLE IF NOT EXISTS anomaly_events
(
    event_id          String,
    trigger_event_id  String,
    site_id           LowCardinality(String),
    equipment_id      LowCardinality(String),
    sensor_id         LowCardinality(String),
    timestamp         DateTime64(3, 'UTC'),
    anomaly_type      LowCardinality(String),
    severity          LowCardinality(String),
    threshold_breached String,
    action_taken      LowCardinality(String),
    alert_channel     LowCardinality(Nullable(String))
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (site_id, equipment_id, timestamp)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

-- Materialized View: Extract anomaly_events from kafka_events_raw
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_raw_to_anomaly
TO anomaly_events
AS
SELECT
    event_id,
    JSONExtractString(metadata, 'trigger_event_id') AS trigger_event_id,
    site_id,
    equipment_id,
    sensor_id,
    timestamp,
    JSONExtractString(metadata, 'anomaly_type') AS anomaly_type,
    JSONExtractString(metadata, 'severity') AS severity,
    JSONExtractString(metadata, 'threshold_breached') AS threshold_breached,
    JSONExtractString(metadata, 'action_taken') AS action_taken,
    JSONExtractString(metadata, 'alert_channel') AS alert_channel
FROM kafka_events_raw
WHERE event_type = 'anomaly_event';
