-- ClickHouse DDL: training_features_export
-- Curated features for Databricks ML pipeline export
-- No TTL (retained for reproducibility)
-- Export method: SELECT ... INTO OUTFILE or S3() table function → Parquet

CREATE TABLE IF NOT EXISTS training_features_export
(
    lineage_id        String,
    event_id          String,
    site_id           LowCardinality(String),
    equipment_id      LowCardinality(String),
    timestamp         DateTime64(3, 'UTC'),
    -- Quality features
    verdict           LowCardinality(String),
    confidence        Float32,
    anomaly_types     Array(String),
    max_severity      LowCardinality(String),
    -- Context features
    payload_uri       String,
    payload_type      LowCardinality(String),
    size_bytes        UInt64,
    -- Sensor context (nearest reading)
    temperature_celsius Nullable(Float32),
    humidity_percent    Nullable(Float32),
    -- Export metadata
    export_timestamp  DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = MergeTree
ORDER BY (lineage_id, event_id)
SETTINGS index_granularity = 8192;

-- Example export query (to S3/ONTAP S3 as Parquet for Databricks):
-- INSERT INTO FUNCTION s3(
--     'https://<ontap-s3-endpoint>/clickhouse-export/training_features/{_partition_id}.parquet',
--     '<access_key>', '<secret_key>',
--     'Parquet'
-- )
-- SELECT * FROM training_features_export
-- WHERE export_timestamp > now() - INTERVAL 1 DAY;
