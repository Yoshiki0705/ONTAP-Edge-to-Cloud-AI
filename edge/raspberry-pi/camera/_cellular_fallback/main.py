"""Edge camera capture service - main entry point.

Periodically captures images from camera and saves to ONTAP NFS.
Optionally uploads via SORACOM cellular as fallback when wired LAN is unavailable.
Designed to run as a systemd service on Raspberry Pi 5.

Usage:
    python main.py                    # Run with default config
    CAPTURE_INTERVAL_SECONDS=60 python main.py  # Custom interval
"""

import logging
import signal
import sys
import time

from buffer import MessageBuffer
from capture import CameraCapture
from config import AppConfig
from health import HealthMonitor
from uploader import Uploader

# Global flag for graceful shutdown
_shutdown_requested = False


def setup_logging(level: str) -> None:
    """Configure structured JSON logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='{"time":"%(asctime)s","level":"%(levelname)s","module":"%(module)s","message":"%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
    )


def signal_handler(signum: int, frame) -> None:
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    _shutdown_requested = True
    logging.getLogger(__name__).info(
        "Shutdown signal received (signal=%d)", signum
    )


def main() -> int:
    """Main capture loop."""
    config = AppConfig()
    setup_logging(config.log_level)
    logger = logging.getLogger(__name__)

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info(
        "Starting edge camera capture service: device=%s, interval=%ds, camera=%s",
        config.device.device_id,
        config.capture.interval_seconds,
        config.capture.camera_type,
    )

    try:
        with MessageBuffer(config.buffer) as buffer:
            uploader = Uploader(config, buffer)
            health = HealthMonitor(
                device_id=config.device.device_id,
                endpoint_url=config.upload.endpoint_url,
            )

            with CameraCapture(config.capture) as camera:
                _run_capture_loop(camera, uploader, buffer, config, health)

    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        return 1

    logger.info("Service stopped cleanly")
    return 0


def _run_capture_loop(
    camera: CameraCapture,
    uploader: Uploader,
    buffer: MessageBuffer,
    config: AppConfig,
    health: HealthMonitor,
) -> None:
    """Execute the main capture-upload loop."""
    logger = logging.getLogger(__name__)
    capture_count = 0
    error_count = 0

    while not _shutdown_requested:
        loop_start = time.monotonic()

        try:
            # Capture image
            image_bytes, metadata = camera.capture()
            capture_count += 1
            health.increment_capture()

            # Upload, or buffer if offline. The return value says which happened;
            # it was assigned and discarded, so a run that buffered every frame
            # looked the same in the logs as one that uploaded every frame.
            uploaded = uploader.upload_image(image_bytes, metadata)
            if not uploaded:
                logger.warning(
                    "Upload deferred to local buffer (pending=%d)",
                    buffer.pending_count(),
                )

            if capture_count % 10 == 0:
                logger.info(
                    "Status: captures=%d, errors=%d, buffered=%d",
                    capture_count,
                    error_count,
                    buffer.pending_count(),
                )

        except Exception as e:
            error_count += 1
            health.increment_error()
            logger.error("Capture/upload error (#%d): %s", error_count, e)

            # If too many consecutive errors, back off
            if error_count > 10:
                logger.warning("Too many errors, backing off for 60s")
                time.sleep(60)
                error_count = 0

        # Periodically flush buffer (every 5th capture)
        if capture_count % 5 == 0:
            try:
                uploader.flush_buffer()
            except Exception as e:
                logger.warning("Buffer flush error: %s", e)

        # Send health report if due
        if health.should_report():
            health.report(
                camera_status="ok" if error_count == 0 else "error",
                buffer_pending=buffer.pending_count(),
            )

        # Sleep for remaining interval
        elapsed = time.monotonic() - loop_start
        sleep_time = max(0, config.capture.interval_seconds - elapsed)
        if sleep_time > 0 and not _shutdown_requested:
            time.sleep(sleep_time)


if __name__ == "__main__":
    sys.exit(main())
