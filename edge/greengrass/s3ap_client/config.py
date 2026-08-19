"""Configuration for Greengrass S3 AP client component.

All settings loaded from environment variables (set in Greengrass component recipe).
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class S3APConfig:
    """FSx for ONTAP S3 Access Point configuration."""

    # S3 AP ARN: arn:aws:s3:<region>:<account>:accesspoint/<name>
    access_point_arn: str = os.getenv("S3AP_ACCESS_POINT_ARN", "")
    # Alias alternative (e.g., iot-ingest-ap-abc123-s3alias)
    access_point_alias: str = os.getenv("S3AP_ACCESS_POINT_ALIAS", "")
    region: str = os.getenv("AWS_REGION", "ap-northeast-1")


@dataclass(frozen=True)
class BufferConfig:
    """Local disk buffer for offline resilience."""

    db_path: str = os.getenv(
        "S3AP_BUFFER_DB_PATH", "/var/lib/greengrass-s3ap/buffer.db"
    )
    max_size_mb: int = int(os.getenv("S3AP_BUFFER_MAX_SIZE_MB", "500"))
    flush_batch_size: int = int(os.getenv("S3AP_BUFFER_FLUSH_BATCH_SIZE", "10"))
    flush_interval_seconds: int = int(
        os.getenv("S3AP_BUFFER_FLUSH_INTERVAL_SECONDS", "10")
    )


@dataclass(frozen=True)
class RetryConfig:
    """Exponential backoff retry settings."""

    max_retries: int = int(os.getenv("S3AP_MAX_RETRIES", "5"))
    base_delay_seconds: float = float(os.getenv("S3AP_RETRY_BASE_DELAY", "1.0"))
    max_delay_seconds: float = float(os.getenv("S3AP_RETRY_MAX_DELAY", "60.0"))
    # Entries exceeding max retries are moved to dead letter
    dead_letter_max_retries: int = int(os.getenv("S3AP_DEAD_LETTER_MAX_RETRIES", "10"))


@dataclass(frozen=True)
class DeviceConfig:
    """Device identification for directory partitioning."""

    device_id: str = os.getenv("DEVICE_ID", "rpi5-001")
    site_id: str = os.getenv("SITE_ID", "lab-tokyo")


@dataclass(frozen=True)
class ComponentConfig:
    """Top-level component configuration."""

    s3ap: S3APConfig = field(default_factory=S3APConfig)
    buffer: BufferConfig = field(default_factory=BufferConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
