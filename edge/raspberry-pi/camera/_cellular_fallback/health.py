"""Device health monitoring and heartbeat reporting.

Periodically sends system health metrics for monitoring.
Primary: writes to ONTAP NFS (alongside telemetry data).
Fallback: sends via SORACOM cellular when wired LAN is unavailable.
"""

import logging
import os
import platform
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


@dataclass
class HealthReport:
    """Device health metrics."""

    device_id: str
    timestamp: str
    uptime_seconds: float
    cpu_temp_celsius: float | None
    cpu_usage_percent: float
    memory_used_percent: float
    disk_used_percent: float
    camera_status: str  # "ok" | "error" | "unknown"
    network_status: str  # "ethernet" | "cellular" | "disconnected"
    buffer_pending_count: int
    capture_count_since_boot: int
    error_count_since_boot: int
    python_version: str
    os_version: str


class HealthMonitor:
    """Monitors device health and sends periodic heartbeats."""

    def __init__(
        self,
        device_id: str,
        endpoint_url: str = "http://unified.soracom.io",
        interval_seconds: int = 300,  # 5 minutes
    ) -> None:
        self._device_id = device_id
        self._endpoint_url = endpoint_url
        self._interval_seconds = interval_seconds
        self._boot_time = time.monotonic()
        self._capture_count = 0
        self._error_count = 0
        self._last_report_time = 0.0

    def increment_capture(self) -> None:
        """Record a successful capture."""
        self._capture_count += 1

    def increment_error(self) -> None:
        """Record an error."""
        self._error_count += 1

    def should_report(self) -> bool:
        """Check if it's time to send a health report."""
        return (time.monotonic() - self._last_report_time) >= self._interval_seconds

    def report(
        self,
        camera_status: str = "unknown",
        buffer_pending: int = 0,
    ) -> bool:
        """Generate and send health report.

        Returns:
            True if report was sent successfully
        """
        report = HealthReport(
            device_id=self._device_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            uptime_seconds=time.monotonic() - self._boot_time,
            cpu_temp_celsius=self._get_cpu_temp(),
            cpu_usage_percent=self._get_cpu_usage(),
            memory_used_percent=self._get_memory_usage(),
            disk_used_percent=self._get_disk_usage(),
            camera_status=camera_status,
            network_status=self._get_network_status(),
            buffer_pending_count=buffer_pending,
            capture_count_since_boot=self._capture_count,
            error_count_since_boot=self._error_count,
            python_version=platform.python_version(),
            os_version=platform.platform(),
        )

        success = self._send_report(report)
        if success:
            self._last_report_time = time.monotonic()
        return success

    def _send_report(self, report: HealthReport) -> bool:
        """Send health report to SORACOM endpoint."""
        payload = {
            "schema_version": "1.0",
            "message_type": "device_health",
            "device_id": self._device_id,
            "timestamp": report.timestamp,
            "payload": asdict(report),
        }

        try:
            resp = requests.post(
                self._endpoint_url,
                json=payload,
                timeout=10,
            )
            if resp.status_code in (200, 201, 202):
                logger.debug("Health report sent successfully")
                return True
            logger.warning("Health report failed: HTTP %d", resp.status_code)
            return False
        except requests.exceptions.RequestException as e:
            logger.debug("Health report send error (non-critical): %s", e)
            return False

    @staticmethod
    def _get_cpu_temp() -> float | None:
        """Read CPU temperature (Raspberry Pi specific)."""
        thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
        if thermal_path.exists():
            try:
                temp_raw = thermal_path.read_text().strip()
                return int(temp_raw) / 1000.0
            except (ValueError, OSError):
                pass
        return None

    @staticmethod
    def _get_cpu_usage() -> float:
        """Get CPU usage percentage."""
        try:
            load_1min = os.getloadavg()[0]
            cpu_count = os.cpu_count() or 1
            return min(100.0, (load_1min / cpu_count) * 100.0)
        except OSError:
            return 0.0

    @staticmethod
    def _get_memory_usage() -> float:
        """Get memory usage percentage."""
        meminfo_path = Path("/proc/meminfo")
        if not meminfo_path.exists():
            return 0.0

        try:
            meminfo = meminfo_path.read_text()
            total = available = 0
            for line in meminfo.splitlines():
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available = int(line.split()[1])
            if total > 0:
                return round((1 - available / total) * 100, 1)
        except (ValueError, OSError):
            pass
        return 0.0

    @staticmethod
    def _get_disk_usage() -> float:
        """Get root filesystem usage percentage."""
        try:
            usage = shutil.disk_usage("/")
            return round(usage.used / usage.total * 100, 1)
        except OSError:
            return 0.0

    @staticmethod
    def _get_network_status() -> str:
        """Detect active network interface."""
        # Check for Ethernet
        eth_paths = list(Path("/sys/class/net").glob("eth*")) + list(
            Path("/sys/class/net").glob("en*")
        )
        for eth in eth_paths:
            operstate = eth / "operstate"
            if operstate.exists():
                try:
                    if operstate.read_text().strip() == "up":
                        return "ethernet"
                except OSError:
                    pass

        # Check for cellular (usb0 or wwan0)
        cell_paths = list(Path("/sys/class/net").glob("usb*")) + list(
            Path("/sys/class/net").glob("wwan*")
        )
        for cell in cell_paths:
            operstate = cell / "operstate"
            if operstate.exists():
                try:
                    if operstate.read_text().strip() == "up":
                        return "cellular"
                except OSError:
                    pass

        return "disconnected"
