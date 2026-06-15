-- ClickHouse DDL: Kafka Table Engine (source for kafka_events_raw)
-- Connects ClickHouse to Kafka topic factory.events.raw
-- NOTE: Replace <KAFKA_BROKER> with actual broker address after Instaclustr deployment

CREATE TABLE IF NOT EXISTS kafka_events_queue
(
    event_id          String,
    event_type        String,
    domain            String,
    event_category    String,
    source_id         String,
    asset_type        String,
    asset_id          String,
    site_id           String,
    line_id           String,
    equipment_id      String,
    sensor_id         String,
    timestamp         String,  -- ISO 8601 string, converted in MV
    ingest_time       String,
    schema_version    String,
    payload_uri       Nullable(String),
    payload_type      Nullable(String),
    content_type      Nullable(String),
    checksum          Nullable(String),
    size_bytes        Nullable(UInt64),
    lineage_id        String,
    processing_status String,
    metadata          String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = '<KAFKA_BROKER>:9092',
    kafka_topic_list = 'factory.events.raw',
    kafka_group_name = 'clickhouse-consumer-group',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 1,
    kafka_max_block_size = 1048576;

-- Materialized View: Kafka queue → kafka_events_raw (with type conversion)
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_kafka_to_raw
TO kafka_events_raw
AS
SELECT
    event_id,
    event_type,
    domain,
    event_category,
    source_id,
    asset_type,
    asset_id,
    site_id,
    line_id,
    equipment_id,
    sensor_id,
    parseDateTimeBestEffort(timestamp) AS timestamp,
    parseDateTimeBestEffort(ingest_time) AS ingest_time,
    schema_version,
    payload_uri,
    payload_type,
    content_type,
    checksum,
    size_bytes,
    lineage_id,
    processing_status,
    metadata
FROM kafka_events_queue;
