-- ClickHouse DDL: quality_events
-- AI analysis results (deduplication by event_id using ReplacingMergeTree)
-- Retention: 365 days

CREATE TABLE IF NOT EXISTS quality_events
(
    event_id          String,
    source_event_id   String,      -- The payload_arrival event that triggered analysis
    site_id           LowCardinality(String),
    line_id           LowCardinality(String),
    equipment_id      LowCardinality(String),
    sensor_id         LowCardinality(String),
    timestamp         DateTime64(3, 'UTC'),
    ingest_time       DateTime64(3, 'UTC'),
    verdict           LowCardinality(String),  -- normal / anomaly_detected
    confidence        Float32,
    anomaly_types     Array(LowCardinality(String)),  -- ['stringing', 'layer_shift']
    max_severity      LowCardinality(String),  -- low / medium / high / critical
    analyzer_model    LowCardinality(String),
    analysis_latency_ms UInt32,
    payload_uri       Nullable(String),
    recommended_action LowCardinality(Nullable(String)),
    metadata_json     String
)
ENGINE = ReplacingMergeTree(ingest_time)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (event_id)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

-- Materialized View: Extract quality_events from kafka_events_raw
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_raw_to_quality
TO quality_events
AS
SELECT
    event_id,
    JSONExtractString(metadata, 'source_event_id') AS source_event_id,
    site_id,
    line_id,
    equipment_id,
    sensor_id,
    timestamp,
    ingest_time,
    JSONExtractString(metadata, 'verdict') AS verdict,
    JSONExtractFloat(metadata, 'confidence') AS confidence,
    JSONExtractArrayRaw(metadata, 'anomalies') AS anomaly_types,  -- simplified
    JSONExtractString(metadata, 'max_severity') AS max_severity,
    JSONExtractString(metadata, 'analyzer_model') AS analyzer_model,
    JSONExtractUInt(metadata, 'analysis_latency_ms') AS analysis_latency_ms,
    payload_uri,
    JSONExtractString(metadata, 'recommended_action') AS recommended_action,
    metadata AS metadata_json
FROM kafka_events_raw
WHERE event_type = 'quality_event';
