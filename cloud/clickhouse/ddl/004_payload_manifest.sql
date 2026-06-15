-- ClickHouse DDL: payload_manifest
-- Bridge between structured events and raw payloads stored in ONTAP
-- Enables: "show me the image for this anomaly event"
-- Retention: 365 days

CREATE TABLE IF NOT EXISTS payload_manifest
(
    event_id        String,
    site_id         LowCardinality(String),
    equipment_id    LowCardinality(String),
    sensor_id       LowCardinality(String),
    timestamp       DateTime64(3, 'UTC'),
    payload_uri     String,
    payload_type    LowCardinality(String),
    content_type    LowCardinality(String),
    checksum        Nullable(String),
    size_bytes      UInt64,
    lineage_id      String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (site_id, timestamp, payload_uri)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;

-- Materialized View: Auto-populate from payload_arrival events
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_raw_to_manifest
TO payload_manifest
AS
SELECT
    event_id,
    site_id,
    equipment_id,
    sensor_id,
    timestamp,
    payload_uri,
    payload_type,
    content_type,
    checksum,
    size_bytes,
    lineage_id
FROM kafka_events_raw
WHERE event_type = 'payload_arrival'
  AND payload_uri IS NOT NULL;
