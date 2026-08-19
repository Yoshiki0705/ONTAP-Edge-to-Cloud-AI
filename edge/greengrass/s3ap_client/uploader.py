"""S3 Access Point uploader with exponential backoff retry.

Writes data directly to FSx for ONTAP S3 Access Points using PutObject.
Handles transient failures with configurable retry and jitter.
"""

import logging
import random
import time
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .config import RetryConfig, S3APConfig

logger = logging.getLogger(__name__)


class S3APUploadError(Exception):
    """Raised when S3 AP upload fails after all retries."""

    def __init__(self, key: str, last_error: str, attempts: int) -> None:
        self.key = key
        self.last_error = last_error
        self.attempts = attempts
        super().__init__(
            f"Failed to upload '{key}' after {attempts} attempts: {last_error}"
        )


class S3APUploader:
    """Uploads data to FSx for ONTAP via S3 Access Points with retry."""

    def __init__(
        self,
        s3ap_config: S3APConfig,
        retry_config: RetryConfig,
        s3_client: Any | None = None,
    ) -> None:
        self._s3ap_config = s3ap_config
        self._retry_config = retry_config
        self._s3_client = s3_client or boto3.client(
            "s3", region_name=s3ap_config.region
        )

    def upload(
        self,
        key: str,
        body: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> dict:
        """Upload data to S3 AP with exponential backoff retry.

        Args:
            key: S3 object key (relative to AP root, e.g. "ingest/rpi5-001/year=2026/...")
            body: Raw bytes to upload
            content_type: MIME type
            metadata: Optional S3 user metadata (x-amz-meta-*)

        Returns:
            PutObject response dict on success

        Raises:
            S3APUploadError: After all retry attempts exhausted
            ValueError: If S3 AP ARN is not configured
        """
        bucket_or_arn = self._resolve_target()
        if not bucket_or_arn:
            raise ValueError(
                "S3 AP target not configured. "
                "Set S3AP_ACCESS_POINT_ARN or S3AP_ACCESS_POINT_ALIAS."
            )

        last_error = ""
        for attempt in range(1, self._retry_config.max_retries + 1):
            try:
                put_kwargs: dict[str, Any] = {
                    "Bucket": bucket_or_arn,
                    "Key": key,
                    "Body": body,
                    "ContentType": content_type,
                }
                if metadata:
                    put_kwargs["Metadata"] = metadata

                response = self._s3_client.put_object(**put_kwargs)
                logger.info(
                    "Upload success: key=%s, size=%d, attempt=%d",
                    key,
                    len(body),
                    attempt,
                )
                return response

            except (ClientError, BotoCoreError) as e:
                last_error = str(e)
                if attempt < self._retry_config.max_retries:
                    delay = self._calculate_backoff(attempt)
                    logger.warning(
                        "Upload failed (attempt %d/%d): %s. Retrying in %.1fs.",
                        attempt,
                        self._retry_config.max_retries,
                        last_error,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "Upload failed permanently after %d attempts: %s",
                        attempt,
                        last_error,
                    )

        raise S3APUploadError(
            key=key,
            last_error=last_error,
            attempts=self._retry_config.max_retries,
        )

    def _resolve_target(self) -> str:
        """Resolve the S3 AP target (ARN preferred, alias as fallback)."""
        if self._s3ap_config.access_point_arn:
            return self._s3ap_config.access_point_arn
        if self._s3ap_config.access_point_alias:
            return self._s3ap_config.access_point_alias
        return ""

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate delay with exponential backoff + jitter."""
        base = self._retry_config.base_delay_seconds
        max_delay = self._retry_config.max_delay_seconds
        # Exponential: base * 2^(attempt-1), capped at max
        delay = min(base * (2 ** (attempt - 1)), max_delay)
        # Add jitter (0-25% of delay)
        # Retry jitter spreads concurrent retries; not a secret, no CSPRNG needed.
        # The waiver must sit on the reported line, not above it, or bandit ignores it.
        jitter = delay * random.uniform(0, 0.25)  # nosec B311  # noqa: S311
        return delay + jitter

    def build_key(
        self,
        device_id: str,
        data_type: str,
        filename: str,
        timestamp: datetime | None = None,
    ) -> str:
        """Build Hive-partitioned S3 key for IoT data.

        Produces: ingest/{device_id}/year={Y}/month={M}/day={D}/hour={H}/{filename}

        Args:
            device_id: Device identifier
            data_type: Not used in path (preserved in metadata)
            filename: Filename (typically UUID-based)
            timestamp: UTC timestamp (defaults to now)

        Returns:
            S3 object key string
        """
        ts = timestamp or datetime.now(UTC)
        return (
            f"ingest/{device_id}/"
            f"year={ts.year}/month={ts.month:02d}/"
            f"day={ts.day:02d}/hour={ts.hour:02d}/"
            f"{filename}"
        )
