-- ClickHouse DDL: sensor_events_rollup_1m
-- 1-minute aggregation of sensor readings
-- Retention: 90 days

CREATE TABLE IF NOT EXISTS sensor_events_rollup_1m
(
    site_id         LowCardinality(String),
    equipment_id    LowCardinality(String),
    sensor_id       LowCardinality(String),
    minute          DateTime('UTC'),
    event_count     UInt32,
    -- Generic numeric aggregates (sensor-type agnostic)
    avg_value_1     Float64,  -- e.g., temperature
    min_value_1     Float64,
    max_value_1     Float64,
    avg_value_2     Float64,  -- e.g., humidity
    min_value_2     Float64,
    max_value_2     Float64
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(minute)
ORDER BY (site_id, equipment_id, sensor_id, minute)
TTL minute + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;

-- Note: MV for sensor_events_rollup requires parsing metadata JSON for readings.
-- This will be refined when actual sensor data format is confirmed during Phase 2 testing.
-- Placeholder MV:
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_raw_to_sensor_rollup
TO sensor_events_rollup_1m
AS
SELECT
    site_id,
    equipment_id,
    sensor_id,
    toStartOfMinute(timestamp) AS minute,
    count() AS event_count,
    avg(JSONExtractFloat(metadata, 'readings', 'temperature_celsius')) AS avg_value_1,
    min(JSONExtractFloat(metadata, 'readings', 'temperature_celsius')) AS min_value_1,
    max(JSONExtractFloat(metadata, 'readings', 'temperature_celsius')) AS max_value_1,
    avg(JSONExtractFloat(metadata, 'readings', 'humidity_percent')) AS avg_value_2,
    min(JSONExtractFloat(metadata, 'readings', 'humidity_percent')) AS min_value_2,
    max(JSONExtractFloat(metadata, 'readings', 'humidity_percent')) AS max_value_2
FROM kafka_events_raw
WHERE event_type = 'sensor_event'
GROUP BY site_id, equipment_id, sensor_id, minute;
