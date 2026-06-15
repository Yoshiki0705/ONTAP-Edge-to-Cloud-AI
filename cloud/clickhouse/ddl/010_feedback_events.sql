-- ClickHouse DDL: feedback_events
-- Human feedback on AI verdicts (ground-truth labels for model improvement)
-- Source: feedback_recorder Lambda → Kafka (event_type = 'feedback_event')
-- Used to: (1) measure AI accuracy, (2) provide labels for ML training
-- Retention: no TTL (ground-truth labels are valuable long-term)

CREATE TABLE IF NOT EXISTS feedback_events
(
    event_id          String,           -- This feedback event's ID
    target_event_id   String,           -- The quality_event being corrected
    site_id           LowCardinality(String),
    equipment_id      LowCardinality(String),
    timestamp         DateTime64(3, 'UTC'),
    ingest_time       DateTime64(3, 'UTC'),
    ai_verdict        LowCardinality(String),     -- What the AI said
    human_label       LowCardinality(String),     -- confirmed_normal / confirmed_defect / mislabeled
    feedback_type     LowCardinality(String),     -- true_positive / false_positive / true_negative / false_negative
    correct           Bool,                        -- Was the AI correct?
    label_confidence  Float32,
    labeled_by        String,
    notes             Nullable(String)
)
ENGINE = ReplacingMergeTree(ingest_time)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (target_event_id)
SETTINGS index_granularity = 8192;

-- Materialized View: Extract feedback_events from kafka_events_raw
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_raw_to_feedback
TO feedback_events
AS
SELECT
    event_id,
    JSONExtractString(metadata, 'target_event_id') AS target_event_id,
    site_id,
    equipment_id,
    timestamp,
    ingest_time,
    JSONExtractString(metadata, 'ai_verdict') AS ai_verdict,
    JSONExtractString(metadata, 'human_label') AS human_label,
    JSONExtractString(metadata, 'feedback_type') AS feedback_type,
    JSONExtractBool(metadata, 'correct') AS correct,
    JSONExtractFloat(metadata, 'label_confidence') AS label_confidence,
    JSONExtractString(metadata, 'labeled_by') AS labeled_by,
    JSONExtractString(metadata, 'notes') AS notes
FROM kafka_events_raw
WHERE event_type = 'feedback_event';
