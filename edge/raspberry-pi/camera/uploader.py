"""Upload module for sending captured images to SORACOM/AWS.

Handles image upload via SORACOM unified endpoint with retry logic.
Falls back to local buffer when network is unavailable.
"""

import base64
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

from buffer import MessageBuffer
from config import AppConfig, UploadConfig

logger = logging.getLogger(__name__)


class Uploader:
    """Handles uploading captured data to SORACOM endpoint."""

    def __init__(self, config: AppConfig, buffer: MessageBuffer) -> None:
        self._upload_config = config.upload
        self._device_config = config.device
        self._buffer = buffer
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def upload_image(
        self,
        image_bytes: bytes,
        capture_metadata: dict,
        print_context: dict | None = None,
    ) -> bool:
        """Upload a captured image with metadata.

        Args:
            image_bytes: JPEG image data
            capture_metadata: Metadata from capture (timestamp, resolution, etc.)
            print_context: Optional 3D print context information

        Returns:
            True if upload succeeded, False if buffered for retry
        """
        message = self._build_message(image_bytes, capture_metadata, print_context)

        # Try direct upload
        success = self._try_upload(message)
        if success:
            return True

        # Buffer for later retry
        image_path = self._save_image_locally(image_bytes, capture_metadata)
        self._buffer.enqueue(
            message_type="image_capture",
            metadata=message,
            image_path=str(image_path) if image_path else None,
        )
        logger.warning(
            "Upload failed, buffered locally. Pending: %d",
            self._buffer.pending_count(),
        )
        return False

    def flush_buffer(self) -> int:
        """Attempt to upload buffered messages.

        Returns:
            Number of successfully flushed messages
        """
        pending = self._buffer.peek()
        if not pending:
            return 0

        flushed = 0
        for entry in pending:
            message = entry["metadata"]

            # If image was saved locally, re-read it
            if entry["image_path"] and Path(entry["image_path"]).exists():
                image_bytes = Path(entry["image_path"]).read_bytes()
                message["payload"]["image"]["data_base64"] = base64.b64encode(
                    image_bytes
                ).decode("ascii")

            if self._try_upload(message):
                self._buffer.remove(entry["id"])
                # Clean up local image file
                if entry["image_path"] and Path(entry["image_path"]).exists():
                    Path(entry["image_path"]).unlink()
                flushed += 1
            else:
                self._buffer.mark_failed(entry["id"], "Upload retry failed")
                break  # Stop on first failure to preserve order

        if flushed > 0:
            logger.info("Flushed %d buffered messages", flushed)
        return flushed

    def _build_message(
        self,
        image_bytes: bytes,
        capture_metadata: dict,
        print_context: dict | None,
    ) -> dict:
        """Build the IoT message envelope."""
        timestamp = capture_metadata.get(
            "timestamp", datetime.now(timezone.utc).isoformat()
        )
        device_id = self._device_config.device_id

        # Generate S3 key based on timestamp
        ts = datetime.fromisoformat(timestamp)
        s3_key = (
            f"raw/image_capture/"
            f"year={ts.year:04d}/month={ts.month:02d}/day={ts.day:02d}/"
            f"device={device_id}/"
            f"{ts.strftime('%Y%m%dT%H%M%SZ')}_{device_id}_print-monitor.jpg"
        )

        message = {
            "schema_version": "1.0",
            "message_id": str(uuid.uuid4()),
            "device_id": device_id,
            "timestamp": timestamp,
            "message_type": "image_capture",
            "payload": {
                "image": {
                    "s3_key": s3_key,
                    "format": capture_metadata.get("format", "jpeg"),
                    "resolution": capture_metadata.get("resolution", "1920x1080"),
                    "size_bytes": capture_metadata.get("size_bytes", len(image_bytes)),
                    "compression_quality": capture_metadata.get(
                        "compression_quality", 80
                    ),
                    "data_base64": base64.b64encode(image_bytes).decode("ascii"),
                },
                "capture_context": {
                    "trigger": "scheduled",
                    "interval_seconds": 30,
                    "camera_id": "cam-usb-001",
                    "camera_model": "brio-4k",
                },
            },
        }

        if print_context:
            message["payload"]["print_context"] = print_context

        return message

    def _try_upload(self, message: dict) -> bool:
        """Attempt to upload a message with retries."""
        url = f"{self._upload_config.endpoint_url}{self._upload_config.upload_path}"

        # Remove base64 image data for the metadata-only message
        # (image is sent separately or inline depending on SORACOM config)
        for attempt in range(1, self._upload_config.max_retries + 1):
            try:
                response = self._session.post(
                    url,
                    json=message,
                    timeout=self._upload_config.timeout_seconds,
                )
                if response.status_code in (200, 201, 202):
                    logger.debug("Upload successful (attempt %d)", attempt)
                    return True

                logger.warning(
                    "Upload failed (attempt %d/%d): HTTP %d - %s",
                    attempt,
                    self._upload_config.max_retries,
                    response.status_code,
                    response.text[:200],
                )
            except requests.exceptions.RequestException as e:
                logger.warning(
                    "Upload error (attempt %d/%d): %s",
                    attempt,
                    self._upload_config.max_retries,
                    str(e),
                )

            if attempt < self._upload_config.max_retries:
                time.sleep(self._upload_config.retry_delay_seconds)

        return False

    def _save_image_locally(
        self, image_bytes: bytes, metadata: dict
    ) -> Path | None:
        """Save image to local filesystem as backup."""
        try:
            timestamp = metadata.get("timestamp", datetime.now(timezone.utc).isoformat())
            ts = datetime.fromisoformat(timestamp)
            filename = f"{ts.strftime('%Y%m%dT%H%M%SZ')}_{self._device_config.device_id}.jpg"

            buffer_dir = Path(self._buffer._config.db_path).parent / "images"
            buffer_dir.mkdir(parents=True, exist_ok=True)

            filepath = buffer_dir / filename
            filepath.write_bytes(image_bytes)
            logger.debug("Image saved locally: %s", filepath)
            return filepath
        except OSError as e:
            logger.error("Failed to save image locally: %s", e)
            return None
