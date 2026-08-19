"""Greengrass S3 AP client component main loop.

Orchestrates:
1. Accepting data from local IPC (sensor reads, camera captures)
2. Writing to local buffer (SQLite)
3. Flushing buffer to FSx for ONTAP S3 AP with retry

This replaces Greengrass Stream Manager for S3 AP targets.
"""

import json
import logging
import signal
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .buffer import S3APBuffer
from .config import ComponentConfig
from .uploader import S3APUploader, S3APUploadError

logger = logging.getLogger(__name__)


class S3APClientComponent:
    """Main component orchestrating buffer → S3 AP upload cycle."""

    def __init__(self, config: ComponentConfig | None = None) -> None:
        self._config = config or ComponentConfig()
        self._buffer = S3APBuffer(self._config.buffer)
        self._uploader = S3APUploader(self._config.s3ap, self._config.retry)
        self._running = False
        self._flush_thread: threading.Thread | None = None
        self._data_dir = Path(self._config.buffer.db_path).parent / "data"

    def start(self) -> None:
        """Start the component (open buffer, begin flush loop)."""
        logging.basicConfig(
            level=self._config.log_level,
            format='{"time":"%(asctime)s","level":"%(levelname)s","component":"s3ap-client","msg":"%(message)s"}',
        )
        logger.info(
            "Starting S3 AP client component: device=%s, target=%s",
            self._config.device.device_id,
            self._config.s3ap.access_point_arn or self._config.s3ap.access_point_alias,
        )

        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._buffer.open()
        self._running = True

        # Start background flush thread
        self._flush_thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="s3ap-flush"
        )
        self._flush_thread.start()

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        logger.info("S3 AP client component started. Pending: %d", self._buffer.pending_count())

    def stop(self) -> None:
        """Stop the component gracefully."""
        logger.info("Stopping S3 AP client component...")
        self._running = False
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=10)
        self._buffer.close()
        logger.info("S3 AP client component stopped.")

    def ingest_bytes(
        self,
        data: bytes,
        content_type: str = "application/octet-stream",
        filename: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Ingest raw bytes for upload to S3 AP.

        Writes data to local disk buffer and queues for async upload.

        Args:
            data: Raw bytes (image, Parquet, JSON, etc.)
            content_type: MIME type
            filename: Custom filename (auto-generated UUID if None)
            metadata: S3 user metadata

        Returns:
            The S3 key that will be used for this upload
        """
        ts = datetime.now(UTC)
        fname = filename or f"{uuid.uuid4().hex[:12]}.dat"

        # Determine file extension from content_type
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "application/x-parquet": ".parquet",
            "application/json": ".json",
        }
        if not filename:
            ext = ext_map.get(content_type, ".dat")
            fname = f"{uuid.uuid4().hex[:12]}{ext}"

        # Build S3 key following directory design
        s3_key = self._uploader.build_key(
            device_id=self._config.device.device_id,
            data_type=content_type,
            filename=fname,
            timestamp=ts,
        )

        # Write to local data directory
        local_path = self._data_dir / fname
        local_path.write_bytes(data)

        # Enqueue for upload
        self._buffer.enqueue(
            s3_key=s3_key,
            data_path=str(local_path),
            content_type=content_type,
            metadata=metadata,
            size_bytes=len(data),
        )

        logger.debug("Ingested %d bytes → %s (buffered)", len(data), s3_key)
        return s3_key

    def ingest_file(
        self,
        file_path: str | Path,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Ingest an existing local file for upload to S3 AP.

        Args:
            file_path: Path to local file
            content_type: MIME type
            metadata: S3 user metadata

        Returns:
            The S3 key that will be used for this upload
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ts = datetime.now(UTC)
        s3_key = self._uploader.build_key(
            device_id=self._config.device.device_id,
            data_type=content_type,
            filename=path.name,
            timestamp=ts,
        )

        self._buffer.enqueue(
            s3_key=s3_key,
            data_path=str(path),
            content_type=content_type,
            metadata=metadata,
            size_bytes=path.stat().st_size,
        )

        logger.debug("Ingested file %s → %s (buffered)", path.name, s3_key)
        return s3_key

    def flush_now(self) -> int:
        """Immediately flush pending buffer entries. Returns count of successful uploads."""
        return self._flush_batch()

    def pending_count(self) -> int:
        """Return number of pending uploads in buffer."""
        return self._buffer.pending_count()

    def _flush_loop(self) -> None:
        """Background loop that periodically flushes buffer to S3 AP."""
        interval = self._config.buffer.flush_interval_seconds
        while self._running:
            try:
                uploaded = self._flush_batch()
                if uploaded > 0:
                    logger.info("Flushed %d items to S3 AP", uploaded)
            except Exception as e:
                logger.error("Flush loop error: %s", e, exc_info=True)

            # Sleep in small increments to allow quick shutdown
            for _ in range(interval * 10):
                if not self._running:
                    break
                time.sleep(0.1)

    def _flush_batch(self) -> int:
        """Flush one batch of pending uploads. Returns success count."""
        entries = self._buffer.peek()
        if not entries:
            return 0

        success_count = 0
        for entry in entries:
            data_path = Path(entry["data_path"])
            if not data_path.exists():
                logger.warning(
                    "Data file missing for entry %d: %s. Removing from buffer.",
                    entry["id"],
                    entry["data_path"],
                )
                self._buffer.remove(entry["id"])
                continue

            # Check if entry exceeded dead letter threshold
            if entry["retry_count"] >= self._config.retry.dead_letter_max_retries:
                logger.error(
                    "Entry %d exceeded max retries (%d). Moving to dead letter.",
                    entry["id"],
                    entry["retry_count"],
                )
                self._move_to_dead_letter(entry)
                self._buffer.remove(entry["id"])
                continue

            try:
                body = data_path.read_bytes()
                self._uploader.upload(
                    key=entry["s3_key"],
                    body=body,
                    content_type=entry["content_type"],
                    metadata=entry["metadata"],
                )
                # Success — remove from buffer and local file
                self._buffer.remove(entry["id"])
                data_path.unlink(missing_ok=True)
                success_count += 1

            except S3APUploadError as e:
                self._buffer.mark_failed(entry["id"], str(e))
                logger.warning(
                    "Upload failed for entry %d (%s): %s",
                    entry["id"],
                    entry["s3_key"],
                    e.last_error,
                )
                # Stop batch on first failure (backoff applies globally)
                break

        return success_count

    def _move_to_dead_letter(self, entry: dict) -> None:
        """Move entry to dead letter directory for manual inspection."""
        dl_dir = Path(self._config.buffer.db_path).parent / "dead_letter"
        dl_dir.mkdir(parents=True, exist_ok=True)

        dl_meta = {
            "original_key": entry["s3_key"],
            "retry_count": entry["retry_count"],
            "last_error": entry["last_error"],
            "created_at": entry["created_at"],
        }
        dl_path = dl_dir / f"{Path(entry['data_path']).stem}.meta.json"
        dl_path.write_text(json.dumps(dl_meta, indent=2))

        # Move data file to dead letter
        src = Path(entry["data_path"])
        if src.exists():
            dst = dl_dir / src.name
            src.rename(dst)

        logger.info("Moved to dead letter: %s", entry["s3_key"])

    def _handle_signal(self, signum: int, frame) -> None:
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        logger.info("Received signal %d, shutting down...", signum)
        self.stop()
        sys.exit(0)
