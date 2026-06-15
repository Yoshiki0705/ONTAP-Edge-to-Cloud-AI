-- PoC Success Metrics Queries
-- Maps to requirements.md Success Criteria. Run to evaluate Go/No-Go.

-- ============================================================
-- M1: E2E Pipeline — events reaching ClickHouse
-- Target: data reaches ClickHouse from edge
-- ============================================================
SELECT
    event_type,
    count() AS event_count,
    min(timestamp) AS earliest,
    max(timestamp) AS latest,
    max(ingest_time) - max(timestamp) AS max_pipeline_lag_seconds
FROM kafka_events_raw
WHERE timestamp > now() - INTERVAL 24 HOUR
GROUP BY event_type
ORDER BY event_count DESC;

-- ============================================================
-- M2: AI Analysis Accuracy (from feedback loop)
-- Target: > 80% defect detection accuracy
-- ============================================================
SELECT
    count() AS total_feedback,
    countIf(correct) AS correct_count,
    round(countIf(correct) * 100.0 / count(), 1) AS accuracy_pct,
    -- Precision: of all AI-detected anomalies, how many were real?
    round(
        countIf(feedback_type = 'true_positive') * 100.0 /
        nullIf(countIf(feedback_type IN ('true_positive', 'false_positive')), 0), 1
    ) AS precision_pct,
    -- Recall: of all real anomalies, how many did AI catch?
    round(
        countIf(feedback_type = 'true_positive') * 100.0 /
        nullIf(countIf(feedback_type IN ('true_positive', 'false_negative')), 0), 1
    ) AS recall_pct
FROM feedback_events
WHERE timestamp > now() - INTERVAL 30 DAY;

-- ============================================================
-- M3: Dashboard Latency — ingest lag (p50, p95, p99)
-- Target: p95 < 500ms (Kafka → ClickHouse visibility)
-- ============================================================
SELECT
    quantile(0.50)(dateDiff('millisecond', timestamp, ingest_time)) AS p50_lag_ms,
    quantile(0.95)(dateDiff('millisecond', timestamp, ingest_time)) AS p95_lag_ms,
    quantile(0.99)(dateDiff('millisecond', timestamp, ingest_time)) AS p99_lag_ms
FROM kafka_events_raw
WHERE timestamp > now() - INTERVAL 1 HOUR;

-- ============================================================
-- M4: AI Analysis Latency (Bedrock response time)
-- Target: < 5000ms per image
-- ============================================================
SELECT
    quantile(0.50)(analysis_latency_ms) AS p50_ms,
    quantile(0.95)(analysis_latency_ms) AS p95_ms,
    max(analysis_latency_ms) AS max_ms,
    countIf(analysis_latency_ms > 5000) AS slow_count
FROM quality_events
WHERE timestamp > now() - INTERVAL 24 HOUR;

-- ============================================================
-- M5: Data completeness — payload reference coverage
-- Target: every quality_event has a resolvable payload_uri
-- ============================================================
SELECT
    count() AS total_quality_events,
    countIf(payload_uri IS NOT NULL) AS with_payload_uri,
    countIf(p.payload_uri != '') AS resolvable_in_manifest,
    round(countIf(p.payload_uri != '') * 100.0 / count(), 1) AS coverage_pct
FROM quality_events q
LEFT JOIN payload_manifest p ON q.source_event_id = p.event_id
WHERE q.timestamp > now() - INTERVAL 24 HOUR;

-- ============================================================
-- M6: Dead Letter rate — pipeline data quality
-- Target: < 1% malformed events
-- ============================================================
SELECT
    (SELECT count() FROM dead_letter_events WHERE ingest_time > now() - INTERVAL 24 HOUR) AS dead_letter_count,
    (SELECT count() FROM kafka_events_raw WHERE ingest_time > now() - INTERVAL 24 HOUR) AS success_count,
    round(
        (SELECT count() FROM dead_letter_events WHERE ingest_time > now() - INTERVAL 24 HOUR) * 100.0 /
        nullIf((SELECT count() FROM kafka_events_raw WHERE ingest_time > now() - INTERVAL 24 HOUR), 0), 2
    ) AS dead_letter_rate_pct;
