"""ONTAP REST API telemetry collector.

Periodically polls ONTAP cluster metrics (IOPS, latency, throughput,
capacity, node health) and forwards to SORACOM for cloud analytics.

Requires:
    - ONTAP 9.13.1+ with REST API enabled
    - Service account with readonly role
    - Network access from Pi to ONTAP data LIF (port 443)

Environment variables:
    ONTAP_HOST: ONTAP cluster management or data LIF IP/hostname
    ONTAP_USER: Service account username
    ONTAP_PASSWORD: Service account password (use EnvironmentFile for security)
    ONTAP_VERIFY_SSL: Whether to verify SSL certificate (default: true)
    COLLECTION_INTERVAL_SECONDS: Polling interval (default: 60)
    DEVICE_ID: Device identifier (default: rpi5-001)
    SORACOM_ENDPOINT_URL: SORACOM unified endpoint
"""

import json
import logging
import os
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

# Configuration from environment
ONTAP_HOST = os.getenv("ONTAP_HOST", "<ONTAP_DATA_LIF_IP>")
ONTAP_USER = os.getenv("ONTAP_USER", "svc-iot-telemetry")
ONTAP_PASSWORD = os.getenv("ONTAP_PASSWORD", "")
ONTAP_VERIFY_SSL = os.getenv("ONTAP_VERIFY_SSL", "true").lower() == "true"
COLLECTION_INTERVAL = int(os.getenv("COLLECTION_INTERVAL_SECONDS", "60"))
DEVICE_ID = os.getenv("DEVICE_ID", "rpi5-001")
SORACOM_ENDPOINT = os.getenv("SORACOM_ENDPOINT_URL", "http://unified.soracom.io")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Global shutdown flag
_shutdown = False

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='{"time":"%(asctime)s","level":"%(levelname)s","module":"%(module)s","message":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S%z",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


class ONTAPClient:
    """Lightweight ONTAP REST API client for telemetry collection."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
    ) -> None:
        self._base_url = f"https://{host}/api"
        self._auth = HTTPBasicAuth(username, password)
        self._verify = verify_ssl
        self._session = requests.Session()
        self._session.auth = self._auth
        self._session.verify = self._verify
        self._session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def get_cluster_info(self) -> dict[str, Any]:
        """Get cluster name and ONTAP version."""
        resp = self._get("/cluster")
        return {
            "name": resp.get("name", "unknown"),
            "ontap_version": resp.get("version", {}).get("full", "unknown"),
        }

    def get_cluster_metrics(self) -> dict[str, Any]:
        """Get cluster-level performance metrics."""
        resp = self._get("/cluster/metrics", params={"interval": "1h"})
        records = resp.get("records", [])
        if not records:
            return {}

        latest = records[-1]
        return {
            "iops_read": latest.get("iops", {}).get("read", 0),
            "iops_write": latest.get("iops", {}).get("write", 0),
            "iops_total": latest.get("iops", {}).get("total", 0),
            "throughput_read_bps": latest.get("throughput", {}).get("read", 0),
            "throughput_write_bps": latest.get("throughput", {}).get("write", 0),
            "latency_read_us": latest.get("latency", {}).get("read", 0),
            "latency_write_us": latest.get("latency", {}).get("write", 0),
        }

    def get_volume_metrics(self) -> list[dict[str, Any]]:
        """Get per-volume capacity and performance metrics."""
        resp = self._get(
            "/storage/volumes",
            params={"fields": "name,svm.name,space,statistics"},
        )
        volumes = []
        for vol in resp.get("records", []):
            space = vol.get("space", {})
            stats = vol.get("statistics", {})

            # Skip internal volumes
            vol_name = vol.get("name", "")
            if vol_name.startswith("vol0") or vol_name.startswith("."):
                continue

            volumes.append({
                "name": vol_name,
                "svm": vol.get("svm", {}).get("name", "unknown"),
                "metrics": {
                    "iops_read": stats.get("iops_raw", {}).get("read", 0),
                    "iops_write": stats.get("iops_raw", {}).get("write", 0),
                    "iops_total": stats.get("iops_raw", {}).get("total", 0),
                    "throughput_read_mbps": round(
                        stats.get("throughput_raw", {}).get("read", 0) / 1_048_576, 2
                    ),
                    "throughput_write_mbps": round(
                        stats.get("throughput_raw", {}).get("write", 0) / 1_048_576, 2
                    ),
                    "latency_read_us": stats.get("latency_raw", {}).get("read", 0),
                    "latency_write_us": stats.get("latency_raw", {}).get("write", 0),
                    "capacity_used_bytes": space.get("used", 0),
                    "capacity_total_bytes": space.get("size", 0),
                    "capacity_used_percent": round(
                        space.get("used", 0) / max(space.get("size", 1), 1) * 100, 1
                    ),
                },
            })
        return volumes

    def get_node_metrics(self) -> dict[str, Any]:
        """Get node-level CPU and memory utilization."""
        resp = self._get("/cluster/nodes", params={"fields": "name,statistics"})
        nodes = resp.get("records", [])
        if not nodes:
            return {}

        # Aggregate across nodes
        total_cpu = 0.0
        node_count = 0
        for node in nodes:
            stats = node.get("statistics", {})
            cpu = stats.get("processor_utilization_raw", 0)
            if cpu > 0:
                total_cpu += cpu
                node_count += 1

        return {
            "cpu_utilization_percent": round(
                total_cpu / max(node_count, 1), 1
            ),
            "node_count": node_count,
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        """Execute GET request to ONTAP REST API."""
        url = f"{self._base_url}{path}"
        try:
            resp = self._session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error("ONTAP API error: %s %s - %s", "GET", path, e)
            raise


def build_telemetry_message(
    cluster_info: dict,
    cluster_metrics: dict,
    volumes: list[dict],
    node_metrics: dict,
) -> dict:
    """Build the IoT message envelope for ONTAP telemetry."""
    return {
        "schema_version": "1.0",
        "message_id": str(uuid.uuid4()),
        "device_id": DEVICE_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_type": "ontap_telemetry",
        "payload": {
            "cluster": cluster_info,
            "metrics_type": "volume_performance",
            "collection_interval_seconds": COLLECTION_INTERVAL,
            "cluster_metrics": cluster_metrics,
            "volumes": volumes,
            "node_metrics": node_metrics,
        },
    }


def send_to_soracom(message: dict) -> bool:
    """Send telemetry message to SORACOM unified endpoint."""
    try:
        resp = requests.post(
            SORACOM_ENDPOINT,
            json=message,
            timeout=30,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code in (200, 201, 202):
            logger.debug("Telemetry sent successfully")
            return True
        logger.warning("SORACOM upload failed: HTTP %d", resp.status_code)
        return False
    except requests.exceptions.RequestException as e:
        logger.warning("SORACOM upload error: %s", e)
        return False


def signal_handler(signum: int, frame) -> None:
    """Handle shutdown signals."""
    global _shutdown
    _shutdown = True
    logger.info("Shutdown signal received")


def main() -> int:
    """Main telemetry collection loop."""
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    if not ONTAP_PASSWORD:
        logger.error("ONTAP_PASSWORD environment variable is required")
        return 1

    logger.info(
        "Starting ONTAP telemetry collector: host=%s, user=%s, interval=%ds",
        ONTAP_HOST,
        ONTAP_USER,
        COLLECTION_INTERVAL,
    )

    client = ONTAPClient(ONTAP_HOST, ONTAP_USER, ONTAP_PASSWORD, ONTAP_VERIFY_SSL)

    # Get cluster info once at startup
    try:
        cluster_info = client.get_cluster_info()
        logger.info("Connected to cluster: %s (%s)", cluster_info["name"], cluster_info["ontap_version"])
    except Exception as e:
        logger.error("Failed to connect to ONTAP: %s", e)
        return 1

    collection_count = 0
    while not _shutdown:
        loop_start = time.monotonic()

        try:
            cluster_metrics = client.get_cluster_metrics()
            volumes = client.get_volume_metrics()
            node_metrics = client.get_node_metrics()

            message = build_telemetry_message(
                cluster_info, cluster_metrics, volumes, node_metrics
            )

            send_to_soracom(message)
            collection_count += 1

            if collection_count % 10 == 0:
                logger.info(
                    "Collections: %d, volumes tracked: %d",
                    collection_count,
                    len(volumes),
                )

        except Exception as e:
            logger.error("Collection error: %s", e)

        # Sleep for remaining interval
        elapsed = time.monotonic() - loop_start
        sleep_time = max(0, COLLECTION_INTERVAL - elapsed)
        if sleep_time > 0 and not _shutdown:
            time.sleep(sleep_time)

    logger.info("Telemetry collector stopped (collections=%d)", collection_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
