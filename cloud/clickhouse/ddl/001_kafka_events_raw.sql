-- ClickHouse DDL: kafka_events_raw
-- Raw event ingestion from Kafka (factory.events.raw topic)
-- Engine: MergeTree (not ReplacingMergeTree — dedup handled at query time with FINAL on quality_events)
-- Retention: 30 days via TTL

CREATE TABLE IF NOT EXISTS kafka_events_raw
(
    event_id          String,
    event_type        LowCardinality(String),
    domain            LowCardinality(String),
    event_category    LowCardinality(String),
    source_id         LowCardinality(String),
    asset_type        LowCardinality(String),
    asset_id          String,
    site_id           LowCardinality(String),
    line_id           LowCardinality(String),
    equipment_id      LowCardinality(String),
    sensor_id         LowCardinality(String),
    timestamp         DateTime64(3, 'UTC'),
    ingest_time       DateTime64(3, 'UTC'),
    schema_version    LowCardinality(String),
    payload_uri       Nullable(String),
    payload_type      LowCardinality(Nullable(String)),
    content_type      LowCardinality(Nullable(String)),
    checksum          Nullable(String),
    size_bytes        Nullable(UInt64),
    lineage_id        String,
    processing_status LowCardinality(String),
    metadata          String,  -- JSON string, parsed by Materialized Views
    -- Governance: distinguishes synthetic test data from real production data
    is_synthetic      Bool DEFAULT false
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (site_id, equipment_id, timestamp, event_id)
TTL timestamp + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;
