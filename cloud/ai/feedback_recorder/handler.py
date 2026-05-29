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
from datetime import datetime, timezone

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
        timestamp = datetime.now(timezone.utc)
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

        return {
            "statusCode": 200,
            "body": {
                "feedback_id": feedback["feedback_id"],
                "feedback_type": feedback_type,
                "stored_at": f"s3://{bucket}/{key}",
            },
        }

    except Exception as e:
        logger.error("Feedback recording failed: %s", e, exc_info=True)
        return {"statusCode": 500, "body": {"error": str(e)}}
