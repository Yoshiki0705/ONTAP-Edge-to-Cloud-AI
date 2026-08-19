"""Lambda handler: IoT Core MQTT → S3 Access Point (FSx for ONTAP) ingestion.

Receives MQTT messages from IoT Core rules engine and writes them directly
to FSx for ONTAP via S3 Access Points. Supports two modes:

1. Single-message mode: Each invocation writes one message (low latency)
2. Batch mode: Aggregates messages into Parquet files (cost optimized)

Batch mode collects messages in a time window using SQS as a buffer
between IoT Core and this Lambda (configured in CloudFormation).

Environment variables:
    S3AP_ACCESS_POINT_ARN: FSx for ONTAP S3 Access Point ARN
    DEVICE_PREFIX: Key prefix for device data (default: "ingest")
    BATCH_MODE: "true" for Parquet batch, "false" for single JSON (default: "false")
    LOG_LEVEL: Logging level (default: "INFO")
"""

import io
import json
import logging
import os
import uuid
from datetime import UTC, datetime

import boto3
from identifiers import (
    UnsafeIdentifierError,
    resolve_device_id,
    validate_device_id,
)

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# Structured JSON logging
for handler in logger.handlers:
    handler.setFormatter(
        logging.Formatter(
            '{"time":"%(asctime)s","level":"%(levelname)s",'
            '"function":"%(funcName)s","message":"%(message)s"}'
        )
    )

# AWS clients
s3_client = boto3.client("s3")

# Configuration
S3AP_ARN = os.environ.get("S3AP_ACCESS_POINT_ARN", "")
DEVICE_PREFIX = os.environ.get("DEVICE_PREFIX", "ingest")
BATCH_MODE = os.environ.get("BATCH_MODE", "false").lower() == "true"


def handler(event: dict, context) -> dict:
    """Lambda entry point.

    Invocation patterns:
    1. IoT Core rule action (direct): event = MQTT payload
    2. SQS batch (from IoT Core → SQS → Lambda): event = {"Records": [...]}
    """
    logger.info("Received event type: %s", _identify_event_type(event))

    try:
        if not S3AP_ARN:
            raise ValueError(
                "S3AP_ACCESS_POINT_ARN environment variable is required"
            )
        if "Records" in event:
            # SQS batch mode: multiple messages
            return _handle_sqs_batch(event)
        else:
            # Direct IoT Core rule invocation: single message
            return _handle_single_message(event)

    except UnsafeIdentifierError as e:
        # A publisher-supplied identifier that cannot be used as a key segment.
        # 400, not 500: the message is malformed, retrying will not help.
        logger.error("Rejected message with unsafe identifier: %s", e)
        return {"statusCode": 400, "body": {"error": str(e)}}
    except Exception as e:
        logger.error("Ingestion failed: %s", e, exc_info=True)
        return {"statusCode": 500, "body": {"error": str(e)}}


def _handle_single_message(event: dict) -> dict:
    """Handle a single MQTT message from IoT Core rule action."""
    timestamp = datetime.now(UTC)
    # Prefer the IoT Core client id / topic-derived id over the payload field:
    # only the former is authenticated. Validated before it reaches a key.
    device_id = resolve_device_id(event)

    # Build S3 key following directory design
    s3_key = _build_key(device_id, timestamp, "json")

    # Serialize message as JSON
    body = json.dumps(event, default=str, ensure_ascii=False).encode("utf-8")

    # Write to S3 AP
    response = s3_client.put_object(
        Bucket=S3AP_ARN,
        Key=s3_key,
        Body=body,
        ContentType="application/json",
        Metadata={
            "device-id": device_id,
            "ingest-time": timestamp.isoformat(),
            "source": "iot-core-rule",
        },
    )

    logger.info(
        "Single message written: key=%s, device=%s, size=%d",
        s3_key,
        device_id,
        len(body),
    )

    return {
        "statusCode": 200,
        "body": {
            "key": s3_key,
            "device_id": device_id,
            "size_bytes": len(body),
            "etag": response.get("ETag", ""),
        },
    }


def _handle_sqs_batch(event: dict) -> dict:
    """Handle SQS batch of MQTT messages, write as Parquet or NDJSON."""
    records = event.get("Records", [])
    if not records:
        return {"statusCode": 200, "body": {"message": "No records"}}

    timestamp = datetime.now(UTC)

    # Parse SQS messages (body contains the original MQTT payload)
    messages = []
    for record in records:
        try:
            body = json.loads(record["body"])
            messages.append(body)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Skipping malformed SQS record: %s", e)

    if not messages:
        return {"statusCode": 200, "body": {"message": "No valid messages"}}

    # Determine device_id from first message (batch assumed same device or mixed)
    device_id = resolve_device_id(messages[0], fallback="mixed")

    if BATCH_MODE and _parquet_available():
        return _write_parquet_batch(messages, device_id, timestamp)
    else:
        return _write_ndjson_batch(messages, device_id, timestamp)


def _write_parquet_batch(
    messages: list[dict], device_id: str, timestamp: datetime
) -> dict:
    """Write batch as Parquet file to S3 AP."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    s3_key = _build_key(device_id, timestamp, "parquet")

    # Convert messages to Arrow table
    # Flatten top-level fields; nested dicts become JSON strings
    flat_messages = []
    for msg in messages:
        flat = {}
        for k, v in msg.items():
            if isinstance(v, (dict, list)):
                flat[k] = json.dumps(v, default=str)
            else:
                flat[k] = v
        flat_messages.append(flat)

    table = pa.Table.from_pylist(flat_messages)

    # Write Parquet to buffer
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    parquet_bytes = buf.getvalue()

    # Upload to S3 AP
    response = s3_client.put_object(
        Bucket=S3AP_ARN,
        Key=s3_key,
        Body=parquet_bytes,
        ContentType="application/x-parquet",
        Metadata={
            "device-id": device_id,
            "ingest-time": timestamp.isoformat(),
            "record-count": str(len(messages)),
            "source": "iot-core-sqs-batch",
            "format": "parquet",
        },
    )

    logger.info(
        "Parquet batch written: key=%s, records=%d, size=%d",
        s3_key,
        len(messages),
        len(parquet_bytes),
    )

    return {
        "statusCode": 200,
        "body": {
            "key": s3_key,
            "device_id": device_id,
            "record_count": len(messages),
            "size_bytes": len(parquet_bytes),
            "format": "parquet",
            "etag": response.get("ETag", ""),
        },
    }


def _write_ndjson_batch(
    messages: list[dict], device_id: str, timestamp: datetime
) -> dict:
    """Write batch as newline-delimited JSON to S3 AP."""
    s3_key = _build_key(device_id, timestamp, "ndjson")

    # Serialize as NDJSON
    lines = [
        json.dumps(msg, default=str, ensure_ascii=False) for msg in messages
    ]
    body = ("\n".join(lines) + "\n").encode("utf-8")

    # Upload to S3 AP
    response = s3_client.put_object(
        Bucket=S3AP_ARN,
        Key=s3_key,
        Body=body,
        ContentType="application/x-ndjson",
        Metadata={
            "device-id": device_id,
            "ingest-time": timestamp.isoformat(),
            "record-count": str(len(messages)),
            "source": "iot-core-sqs-batch",
            "format": "ndjson",
        },
    )

    logger.info(
        "NDJSON batch written: key=%s, records=%d, size=%d",
        s3_key,
        len(messages),
        len(body),
    )

    return {
        "statusCode": 200,
        "body": {
            "key": s3_key,
            "device_id": device_id,
            "record_count": len(messages),
            "size_bytes": len(body),
            "format": "ndjson",
            "etag": response.get("ETag", ""),
        },
    }


def _build_key(device_id: str, timestamp: datetime, extension: str) -> str:
    """Build Hive-partitioned S3 key.

    Pattern: {prefix}/{device_id}/year={Y}/month={M}/day={D}/hour={H}/{uuid}.{ext}

    Re-validates `device_id` so the invariant holds at the point of use, not
    only at the two call sites that currently resolve it.
    """
    validate_device_id(device_id)
    file_id = uuid.uuid4().hex[:12]
    return (
        f"{DEVICE_PREFIX}/{device_id}/"
        f"year={timestamp.year}/month={timestamp.month:02d}/"
        f"day={timestamp.day:02d}/hour={timestamp.hour:02d}/"
        f"{file_id}.{extension}"
    )


def _parquet_available() -> bool:
    """Check if pyarrow is available (included in Lambda layer)."""
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


def _identify_event_type(event: dict) -> str:
    """Identify event source for logging."""
    if "Records" in event:
        return f"SQS batch ({len(event['Records'])} records)"
    if "device_id" in event or "source_id" in event:
        return "IoT Core direct"
    return "unknown"
