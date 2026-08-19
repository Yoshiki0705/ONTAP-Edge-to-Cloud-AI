"""Camera capture module.

Supports both USB cameras (e.g., Logitech BRIO) via OpenCV
and CSI cameras (e.g., Pi Camera Module) via picamera2.
"""

import logging
import time
from datetime import UTC, datetime

import cv2
import numpy as np
from config import CaptureConfig

logger = logging.getLogger(__name__)


class CameraCapture:
    """Handles image capture from USB or CSI cameras."""

    def __init__(self, config: CaptureConfig) -> None:
        self._config = config
        self._camera = None

    def open(self) -> None:
        """Initialize camera connection."""
        if self._config.camera_type == "usb":
            self._open_usb()
        elif self._config.camera_type == "csi":
            self._open_csi()
        else:
            raise ValueError(f"Unsupported camera type: {self._config.camera_type}")

    def _open_usb(self) -> None:
        """Open USB camera via OpenCV."""
        device_index = self._parse_device_index()
        self._camera = cv2.VideoCapture(device_index)
        if not self._camera.isOpened():
            raise RuntimeError(
                f"Failed to open USB camera: {self._config.camera_device}"
            )
        self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.resolution_width)
        self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.resolution_height)
        logger.info(
            "USB camera opened: %s (%dx%d)",
            self._config.camera_device,
            self._config.resolution_width,
            self._config.resolution_height,
        )

    def _open_csi(self) -> None:
        """Open CSI camera via picamera2."""
        try:
            from picamera2 import Picamera2  # type: ignore[import-untyped]
        except ImportError as e:
            raise RuntimeError(
                "picamera2 is required for CSI cameras. "
                "Install with: sudo apt install python3-picamera2"
            ) from e

        self._camera = Picamera2()
        camera_config = self._camera.create_still_configuration(
            main={
                "size": (self._config.resolution_width, self._config.resolution_height)
            }
        )
        self._camera.configure(camera_config)
        self._camera.start()
        time.sleep(2)  # Allow camera to warm up
        logger.info(
            "CSI camera opened (%dx%d)",
            self._config.resolution_width,
            self._config.resolution_height,
        )

    def capture(self) -> tuple[bytes, dict]:
        """Capture a single frame and return JPEG bytes + metadata.

        Returns:
            Tuple of (jpeg_bytes, metadata_dict)
        """
        timestamp = datetime.now(UTC)

        if self._config.camera_type == "usb":
            frame = self._capture_usb()
        else:
            frame = self._capture_csi()

        # Encode to JPEG
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, self._config.jpeg_quality]
        success, jpeg_buffer = cv2.imencode(".jpg", frame, encode_params)
        if not success:
            raise RuntimeError("Failed to encode frame to JPEG")

        jpeg_bytes = jpeg_buffer.tobytes()

        metadata = {
            "timestamp": timestamp.isoformat(),
            "resolution": f"{frame.shape[1]}x{frame.shape[0]}",
            "size_bytes": len(jpeg_bytes),
            "compression_quality": self._config.jpeg_quality,
            "format": "jpeg",
        }

        logger.debug(
            "Captured frame: %s, %d bytes",
            metadata["resolution"],
            metadata["size_bytes"],
        )
        return jpeg_bytes, metadata

    def _capture_usb(self) -> np.ndarray:
        """Capture frame from USB camera."""
        ret, frame = self._camera.read()
        if not ret:
            raise RuntimeError("Failed to capture frame from USB camera")
        return frame

    def _capture_csi(self) -> np.ndarray:
        """Capture frame from CSI camera."""
        frame = self._camera.capture_array()
        # picamera2 returns RGB, OpenCV expects BGR
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def close(self) -> None:
        """Release camera resources."""
        if self._camera is None:
            return

        if self._config.camera_type == "usb":
            self._camera.release()
        else:
            self._camera.stop()
            self._camera.close()

        self._camera = None
        logger.info("Camera closed")

    def _parse_device_index(self) -> int:
        """Parse device path to OpenCV device index."""
        device = self._config.camera_device
        if device.startswith("/dev/video"):
            return int(device.replace("/dev/video", ""))
        return int(device)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
