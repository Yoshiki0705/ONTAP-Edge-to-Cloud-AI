"""Unit tests for the configuration module."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "edge" / "raspberry-pi" / "camera" / "_cellular_fallback"))


class TestCaptureConfig:
    """Tests for CaptureConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=True):
            # Re-import to pick up cleared env
            import importlib
            import config as cfg
            importlib.reload(cfg)

            c = cfg.CaptureConfig()
            assert c.interval_seconds == 30
            assert c.resolution_width == 1920
            assert c.resolution_height == 1080
            assert c.jpeg_quality == 80
            assert c.camera_type == "usb"
            assert c.camera_device == "/dev/video0"

    def test_env_override(self):
        """Test that environment variables override defaults."""
        env = {
            "CAPTURE_INTERVAL_SECONDS": "120",
            "CAPTURE_RESOLUTION_WIDTH": "1280",
            "CAPTURE_RESOLUTION_HEIGHT": "720",
            "CAPTURE_JPEG_QUALITY": "60",
            "CAMERA_TYPE": "csi",
            "CAMERA_DEVICE": "/dev/video1",
        }
        with patch.dict(os.environ, env):
            import importlib
            import config as cfg
            importlib.reload(cfg)

            c = cfg.CaptureConfig()
            assert c.interval_seconds == 120
            assert c.resolution_width == 1280
            assert c.resolution_height == 720
            assert c.jpeg_quality == 60
            assert c.camera_type == "csi"
            assert c.camera_device == "/dev/video1"


class TestUploadConfig:
    """Tests for UploadConfig."""

    def test_default_endpoint(self):
        """Test default upload endpoint (cellular fallback)."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import config as cfg
            importlib.reload(cfg)

            u = cfg.UploadConfig()
            assert u.endpoint_url == "http://unified.soracom.io"
            assert u.timeout_seconds == 30
            assert u.max_retries == 3
            assert u.ontap_nfs_path == "/mnt/ontap/images"


class TestDeviceConfig:
    """Tests for DeviceConfig."""

    def test_device_id_from_env(self):
        """Test device ID from environment."""
        with patch.dict(os.environ, {"DEVICE_ID": "rpi5-test-001"}):
            import importlib
            import config as cfg
            importlib.reload(cfg)

            d = cfg.DeviceConfig()
            assert d.device_id == "rpi5-test-001"
