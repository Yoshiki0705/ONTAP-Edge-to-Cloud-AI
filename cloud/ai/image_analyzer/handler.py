"""Lambda handler for 3D print quality analysis using Bedrock Claude Vision.

Two-stage analysis for cost optimization:
  Stage 1: Claude Haiku (fast, cheap) - quick screening
  Stage 2: Claude Sonnet (accurate, expensive) - only if Haiku flags anomaly

Cost comparison (60-second intervals, 24/7):
  Single-stage Sonnet: ~$259/month
  Two-stage (Haiku + Sonnet on 10% flagged): ~$40/month

Environment variables:
    RESULT_BUCKET: S3 bucket for analysis results
    ALERT_TOPIC_ARN: SNS topic ARN for anomaly alerts
    SCREENING_MODEL_ID: Bedrock model for Stage 1 (default: Haiku)
    DETAIL_MODEL_ID: Bedrock model for Stage 2 (default: Sonnet)
    CONFIDENCE_THRESHOLD: Minimum confidence to trigger alert (default: 0.7)
    TWO_STAGE_ENABLED: Enable two-stage analysis (default: true)
"""

import base64
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

# AWS clients
s3_client = boto3.client("s3")
bedrock_client = boto3.client("bedrock-runtime")
sns_client = boto3.client("sns")
cloudwatch_client = boto3.client("cloudwatch")

# Configuration
RESULT_BUCKET = os.environ.get("RESULT_BUCKET", "")
ALERT_TOPIC_ARN = os.environ.get("ALERT_TOPIC_ARN", "")
SCREENING_MODEL_ID = os.environ.get(
    "SCREENING_MODEL_ID", "jp.anthropic.claude-haiku-4-5-20251001-v1:0"
)
DETAIL_MODEL_ID = os.environ.get(
    "DETAIL_MODEL_ID", "jp.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.7"))
TWO_STAGE_ENABLED = os.environ.get("TWO_STAGE_ENABLED", "true").lower() == "true"

# Analysis prompt for 3D print quality inspection
SCREENING_PROMPT = """Analyze this 3D print image quickly. Is there any visible defect?
Reply JSON only: {"has_defect": true|false, "confidence": 0.0-1.0, "defect_hint": "brief description or empty"}"""

DETAIL_PROMPT = """You are a 3D printing quality inspector. Analyze this image of a 3D print in progress.

Check for the following defects:
1. **Stringing** - thin strings of filament between parts
2. **Layer delamination** - layers separating or not adhering properly
3. **Warping** - edges lifting from the print bed
4. **Under-extrusion** - gaps or thin spots in layers
5. **Over-extrusion** - blobs or excess material
6. **Nozzle clogging** - inconsistent extrusion patterns
7. **Layer shifting** - misaligned layers
8. **Spaghetti** - filament tangling, print completely failed

Respond in JSON format:
{
  "status": "normal" | "anomaly_detected",
  "confidence": 0.0-1.0,
  "anomalies": [
    {
      "type": "stringing|delamination|warping|under_extrusion|over_extrusion|nozzle_clog|layer_shift|spaghetti",
      "severity": "low|medium|high|critical",
      "location": "description of where in the image",
      "description": "brief description of the issue"
    }
  ],
  "recommendation": "action to take",
  "overall_quality_score": 0-100
}

If the print looks normal with no defects, return status "normal" with an empty anomalies array and quality score above 80.
Be conservative - only flag clear defects, not minor cosmetic variations."""


def handler(event: dict, context) -> dict:
    """Lambda entry point.

    Supports two invocation patterns:
    1. S3 event notification (via EventBridge)
    2. Direct invocation with bucket/key in event body
    """
    logger.info("Received event: %s", json.dumps(event, default=str)[:500])

    try:
        bucket, key = _extract_s3_info(event)
        logger.info("Processing image: s3://%s/%s", bucket, key)

        # Download image from S3
        image_bytes = _download_image(bucket, key)
        logger.info("Image downloaded: %d bytes", len(image_bytes))

        # Analyze with Bedrock Claude Vision (two-stage)
        analysis_result = _analyze_image(image_bytes)
        logger.info(
            "Analysis complete: status=%s, confidence=%.2f, stage=%s",
            analysis_result.get("status", "unknown"),
            analysis_result.get("confidence", 0),
            analysis_result.get("_stage", "unknown"),
        )

        # Store result
        result_key = _store_result(bucket, key, analysis_result)

        # Send alert if anomaly detected with high confidence
        alert_sent = False
        if (
            analysis_result.get("status") == "anomaly_detected"
            and analysis_result.get("confidence", 0) >= CONFIDENCE_THRESHOLD
        ):
            _send_alert(bucket, key, analysis_result)
            alert_sent = True

        # Publish business metrics
        _publish_metrics(analysis_result)

        return {
            "statusCode": 200,
            "body": {
                "status": analysis_result.get("status"),
                "confidence": analysis_result.get("confidence"),
                "anomaly_count": len(analysis_result.get("anomalies", [])),
                "result_key": result_key,
                "alert_sent": alert_sent,
            },
        }

    except Exception as e:
        logger.error("Processing failed: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "body": {"error": str(e)},
        }


def _extract_s3_info(event: dict) -> tuple[str, str]:
    """Extract S3 bucket and key from event."""
    # Direct invocation
    if "bucket" in event and "key" in event:
        return event["bucket"], event["key"]

    # S3 event notification (via EventBridge)
    if "detail" in event:
        detail = event["detail"]
        bucket = detail.get("bucket", {}).get("name", "")
        key = detail.get("object", {}).get("key", "")
        if bucket and key:
            return bucket, key

    # S3 event notification (direct)
    if "Records" in event:
        record = event["Records"][0]
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        return bucket, key

    raise ValueError(f"Cannot extract S3 info from event: {list(event.keys())}")


def _download_image(bucket: str, key: str) -> bytes:
    """Download image from S3."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def _analyze_image(image_bytes: bytes) -> dict:
    """Analyze image using two-stage Bedrock Claude Vision.

    Stage 1 (Haiku): Quick screening - is there a defect? (cheap)
    Stage 2 (Sonnet): Detailed analysis - what defect, severity, action (expensive)

    If TWO_STAGE_ENABLED is false, goes directly to Stage 2.
    """
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    if TWO_STAGE_ENABLED:
        # Stage 1: Quick screening with Haiku
        screening_result = _invoke_model(
            image_base64, SCREENING_PROMPT, SCREENING_MODEL_ID, max_tokens=128
        )

        try:
            screening = json.loads(_extract_json(screening_result))
        except (json.JSONDecodeError, ValueError):
            # If screening fails to parse, fall through to detailed analysis
            screening = {"has_defect": True, "confidence": 0.5}

        logger.info(
            "Stage 1 (screening): has_defect=%s, confidence=%.2f",
            screening.get("has_defect"),
            screening.get("confidence", 0),
        )

        # If no defect detected with high confidence, skip Stage 2
        if not screening.get("has_defect") and screening.get("confidence", 0) >= 0.8:
            return {
                "status": "normal",
                "confidence": screening.get("confidence", 0.9),
                "anomalies": [],
                "recommendation": "No defects detected. Print proceeding normally.",
                "overall_quality_score": 90,
                "_stage": "screening_only",
            }

    # Stage 2: Detailed analysis with Sonnet
    detail_result = _invoke_model(
        image_base64, DETAIL_PROMPT, DETAIL_MODEL_ID, max_tokens=1024
    )

    try:
        result = json.loads(_extract_json(detail_result))
        result["_stage"] = "detailed"
    except (json.JSONDecodeError, ValueError):
        result = {
            "status": "normal",
            "confidence": 0.5,
            "anomalies": [],
            "recommendation": "Analysis inconclusive. Manual review recommended.",
            "overall_quality_score": 50,
            "_stage": "parse_error",
        }

    return result


def _invoke_model(image_base64: str, prompt: str, model_id: str, max_tokens: int = 1024) -> str:
    """Invoke a Bedrock model with an image and prompt."""
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    }

    response = bedrock_client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(request_body),
    )

    response_body = json.loads(response["body"].read())
    return response_body["content"][0]["text"]


def _extract_json(text: str) -> str:
    """Extract JSON from model response (handles markdown code blocks)."""
    if "```json" in text:
        return text.split("```json")[1].split("```")[0].strip()
    if "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()


def _store_result(source_bucket: str, source_key: str, result: dict) -> str:
    """Store analysis result to S3."""
    timestamp = datetime.now(UTC)
    result_key = (
        f"processed/image_analysis/"
        f"year={timestamp.year:04d}/month={timestamp.month:02d}/"
        f"day={timestamp.day:02d}/"
        f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}.json"
    )

    result_document = {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "timestamp": timestamp.isoformat(),
        "message_type": "analysis_result",
        "payload": {
            "source_image": {
                "bucket": source_bucket,
                "key": source_key,
            },
            "analyzer": {
                "service": "bedrock",
                # Which model produced this verdict depends on whether Stage 2
                # ran. `_stage` is set by _analyze_image: "screening_only"
                # means only SCREENING_MODEL_ID was invoked.
                "model_id": (
                    SCREENING_MODEL_ID
                    if result.get("_stage") == "screening_only"
                    else DETAIL_MODEL_ID
                ),
                "stage": result.get("_stage", "unknown"),
            },
            "result": result,
        },
    }

    target_bucket = RESULT_BUCKET or source_bucket
    s3_client.put_object(
        Bucket=target_bucket,
        Key=result_key,
        Body=json.dumps(result_document, ensure_ascii=False, indent=2),
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
    )

    logger.info("Result stored: s3://%s/%s", target_bucket, result_key)
    return result_key


def _send_alert(bucket: str, key: str, result: dict) -> None:
    """Send anomaly alert via SNS."""
    if not ALERT_TOPIC_ARN:
        logger.warning("ALERT_TOPIC_ARN not configured, skipping alert")
        return

    anomalies = result.get("anomalies", [])
    severity_list = [a.get("severity", "unknown") for a in anomalies]
    max_severity = "critical" if "critical" in severity_list else (
        "high" if "high" in severity_list else "medium"
    )

    subject = f"[{max_severity.upper()}] 3D Print Anomaly Detected"
    message_lines = [
        "Anomaly detected in 3D print monitoring",
        "",
        f"Image: s3://{bucket}/{key}",
        f"Confidence: {result.get('confidence', 0):.0%}",
        f"Quality Score: {result.get('overall_quality_score', 'N/A')}/100",
        "",
        f"Anomalies ({len(anomalies)}):",
    ]

    for anomaly in anomalies:
        message_lines.append(
            f"  - [{anomaly.get('severity', '?')}] {anomaly.get('type', '?')}: "
            f"{anomaly.get('description', 'No description')}"
        )

    message_lines.extend([
        "",
        f"Recommendation: {result.get('recommendation', 'Review manually')}",
    ])

    sns_client.publish(
        TopicArn=ALERT_TOPIC_ARN,
        Subject=subject[:100],  # SNS subject limit
        Message="\n".join(message_lines),
    )
    logger.info("Alert sent: %s", subject)

def _publish_metrics(result: dict) -> None:
    """Publish business metrics to CloudWatch."""
    try:
        is_anomaly = 1.0 if result.get("status") == "anomaly_detected" else 0.0
        quality_score = result.get("overall_quality_score", 50)

        cloudwatch_client.put_metric_data(
            Namespace="EdgeToCloud/PrintQuality",
            MetricData=[
                {
                    "MetricName": "AnomalyDetected",
                    "Value": is_anomaly,
                    "Unit": "Count",
                },
                {
                    "MetricName": "QualityScore",
                    "Value": float(quality_score),
                    "Unit": "None",
                },
            ],
        )
        logger.debug("Business metrics published: anomaly=%s, score=%s", is_anomaly, quality_score)
    except Exception as e:
        logger.warning("Failed to publish metrics (non-fatal): %s", e)
