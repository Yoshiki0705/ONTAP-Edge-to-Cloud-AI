"""Configuration for edge camera capture system.

All settings are loaded from environment variables with sensible defaults.
See .env.example for reference.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CaptureConfig:
    """Camera capture settings."""

    interval_seconds: int = int(os.getenv("CAPTURE_INTERVAL_SECONDS", "30"))
    resolution_width: int = int(os.getenv("CAPTURE_RESOLUTION_WIDTH", "1920"))
    resolution_height: int = int(os.getenv("CAPTURE_RESOLUTION_HEIGHT", "1080"))
    jpeg_quality: int = int(os.getenv("CAPTURE_JPEG_QUALITY", "80"))
    camera_type: str = os.getenv("CAMERA_TYPE", "usb")  # "usb" or "csi"
    camera_device: str = os.getenv("CAMERA_DEVICE", "/dev/video0")


@dataclass(frozen=True)
class UploadConfig:
    """SORACOM upload settings."""

    endpoint_url: str = os.getenv(
        "SORACOM_ENDPOINT_URL",
        "http://unified.soracom.io",
    )
    upload_path: str = os.getenv("SORACOM_UPLOAD_PATH", "/")
    timeout_seconds: int = int(os.getenv("UPLOAD_TIMEOUT_SECONDS", "30"))
    max_retries: int = int(os.getenv("UPLOAD_MAX_RETRIES", "3"))
    retry_delay_seconds: int = int(os.getenv("UPLOAD_RETRY_DELAY_SECONDS", "5"))


@dataclass(frozen=True)
class BufferConfig:
    """Local buffer settings for offline resilience."""

    db_path: str = os.getenv("BUFFER_DB_PATH", "/var/lib/edge-camera/buffer.db")
    max_size_mb: int = int(os.getenv("BUFFER_MAX_SIZE_MB", "500"))
    flush_batch_size: int = int(os.getenv("BUFFER_FLUSH_BATCH_SIZE", "10"))


@dataclass(frozen=True)
class DeviceConfig:
    """Device identification."""

    device_id: str = os.getenv("DEVICE_ID", "rpi5-001")
    device_type: str = os.getenv("DEVICE_TYPE", "raspberry-pi-5")


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    capture: CaptureConfig = field(default_factory=CaptureConfig)
    upload: UploadConfig = field(default_factory=UploadConfig)
    buffer: BufferConfig = field(default_factory=BufferConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
