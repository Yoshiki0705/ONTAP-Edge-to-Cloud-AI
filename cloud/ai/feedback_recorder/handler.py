"""Lambda handler for recording AI analysis feedback.

Provides a simple API for operators to record whether AI predictions
were correct (True Positive/Negative) or incorrect (False Positive/Negative).

Invocation: Direct invoke or API Gateway (future)

Event format:
{
  "source_message_id": "uuid of the analyzed image",
  "correct": true|false,
  "actual_status": "normal"|"anomaly_detected",
  "anomaly_type": "stringing|delamination|...|none",
  "notes": "optional operator notes"
}

Environment variables:
    FEEDBACK_BUCKET: S3 bucket for feedback storage
"""

import json
import logging
import os
import uuid
from datetime import UTC, datetime

import boto3

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# Configure structured JSON logging for CloudWatch Logs Insights
for handler in logger.handlers:
    handler.setFormatter(
        logging.Formatter(
            '{"time":"%(asctime)s","level":"%(levelname)s","function":"%(funcName)s","message":"%(message)s"}'
        )
    )

s3_client = boto3.client("s3")
FEEDBACK_BUCKET = os.environ.get("FEEDBACK_BUCKET", "")


def handler(event: dict, context) -> dict:
    """Record operator feedback on AI analysis accuracy."""
    logger.info("Feedback received: %s", json.dumps(event)[:500])

    try:
        # Validate required fields
        source_message_id = event.get("source_message_id")
        correct = event.get("correct")
        actual_status = event.get("actual_status")

        if not source_message_id or correct is None or not actual_status:
            return {
                "statusCode": 400,
                "body": {"error": "Required: source_message_id, correct, actual_status"},
            }

        # Determine feedback type
        if correct:
            feedback_type = "true_positive" if actual_status == "anomaly_detected" else "true_negative"
        else:
            feedback_type = "false_positive" if actual_status == "normal" else "false_negative"

        # Build feedback record
        timestamp = datetime.now(UTC)
        feedback = {
            "feedback_id": str(uuid.uuid4()),
            "source_message_id": source_message_id,
            "timestamp": timestamp.isoformat(),
            "correct": correct,
            "actual_status": actual_status,
            "anomaly_type": event.get("anomaly_type", ""),
            "notes": event.get("notes", ""),
            "feedback_type": feedback_type,
        }

        # Store to S3
        key = (
            f"feedback/year={timestamp.year:04d}/month={timestamp.month:02d}/"
            f"day={timestamp.day:02d}/"
            f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{feedback['feedback_id'][:8]}.json"
        )

        bucket = FEEDBACK_BUCKET
        if not bucket:
            return {"statusCode": 500, "body": {"error": "FEEDBACK_BUCKET not configured"}}

        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(feedback, ensure_ascii=False, indent=2),
            ContentType="application/json",
            ServerSideEncryption="aws:kms",
        )

        logger.info("Feedback stored: %s (type=%s)", key, feedback_type)

        # Optionally publish a feedback_event to Kafka so ClickHouse can ingest
        # the ground-truth label (feeds feedback_events table → training_features).
        # Controlled by KAFKA_REST_PROXY_URL env var (Lambda → Kafka REST Proxy).
        kafka_published = _publish_feedback_to_kafka(feedback, event)

        return {
            "statusCode": 200,
            "body": {
                "feedback_id": feedback["feedback_id"],
                "feedback_type": feedback_type,
                "stored_at": f"s3://{bucket}/{key}",
                "kafka_published": kafka_published,
            },
        }

    except Exception as e:
        logger.error("Feedback recording failed: %s", e, exc_info=True)
        return {"statusCode": 500, "body": {"error": str(e)}}


def _publish_feedback_to_kafka(feedback: dict, event: dict) -> bool:
    """Publish a v3 feedback_event to Kafka via REST Proxy (optional).

    Lambda typically cannot reach an on-premises Kafka broker directly, so we
    use a Kafka REST Proxy endpoint when available. If not configured, the
    feedback is only stored in S3 (ClickHouse can batch-import from S3 instead).

    Returns:
        True if published to Kafka, False if skipped/failed (non-fatal).
    """
    rest_proxy_url = os.environ.get("KAFKA_REST_PROXY_URL", "")
    if not rest_proxy_url:
        return False

    # urlopen honours whatever scheme it is given, including file: and ftp:.
    # This URL comes from configuration rather than from an event, so the
    # realistic failure is a deployment typo rather than an attack, but a
    # file:// value would turn this call into a local file read whose contents
    # then get logged. Restricting the scheme costs nothing.
    if not rest_proxy_url.startswith(("http://", "https://")):
        logger.error(
            "KAFKA_REST_PROXY_URL must be http:// or https:// — skipping publish"
        )
        return False

    try:
        import urllib.request

        feedback_event = {
            "event_id": feedback["feedback_id"],
            "event_type": "feedback_event",
            "domain": os.environ.get("EVENT_DOMAIN", "manufacturing"),
            "event_category": "quality_inspection",
            "source_id": "feedback-recorder",
            "asset_type": event.get("asset_type", "3d_printer"),
            "asset_id": event.get("asset_id", "unknown"),
            "site_id": event.get("site_id", "unknown"),
            "line_id": event.get("line_id", "unknown"),
            "equipment_id": event.get("equipment_id", "unknown"),
            "sensor_id": event.get("sensor_id", "unknown"),
            "timestamp": feedback["timestamp"],
            "ingest_time": datetime.now(UTC).isoformat(),
            "schema_version": "2.0.0",
            "payload_uri": event.get("payload_uri"),
            "lineage_id": event.get("lineage_id", feedback["source_message_id"]),
            "processing_status": "completed",
            "metadata": {
                "target_event_id": feedback["source_message_id"],
                "ai_verdict": event.get("ai_verdict", ""),
                "human_label": "confirmed_defect" if feedback["actual_status"] == "anomaly_detected" else "confirmed_normal",
                "feedback_type": feedback["feedback_type"],
                "correct": feedback["correct"],
                "label_confidence": event.get("label_confidence", 1.0),
                "labeled_by": event.get("labeled_by", "operator"),
                "notes": feedback["notes"],
            },
        }

        payload = json.dumps({"records": [{"value": feedback_event}]}).encode("utf-8")
        req = urllib.request.Request(  # noqa: S310  scheme checked above
            f"{rest_proxy_url}/topics/factory.events.raw",
            data=payload,
            headers={"Content-Type": "application/vnd.kafka.json.v2+json"},
            method="POST",
        )
        # Scheme restricted to http/https above; URL comes from configuration,
        # not from the event. bandit blacklists the call itself and cannot see
        # the guard, so the waiver is recorded on the reported line.
        with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310  # noqa: S310
            ok = 200 <= resp.status < 300
            logger.info("Feedback published to Kafka: status=%s", resp.status)
            return ok
    except Exception as e:
        logger.warning("Kafka publish failed (non-fatal, S3 record exists): %s", e)
        return False
