-- ClickHouse DDL: dead_letter_events
-- Events that failed validation (schema errors, malformed JSON)
-- Retention: 30 days (for debugging, then auto-purge)

CREATE TABLE IF NOT EXISTS dead_letter_events
(
    ingest_time     DateTime64(3, 'UTC'),
    raw_payload     String,
    error_reason    String,
    source_topic    LowCardinality(String),
    kafka_offset    UInt64,
    kafka_partition UInt32
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ingest_time)
ORDER BY (ingest_time)
TTL ingest_time + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;
