"""End-to-end test for ONTAP telemetry collection pipeline.

Tests the full flow with mocked ONTAP REST API responses:
  ONTAP API (mock) → collect → format message → upload (mock) → verify

This validates the pipeline works correctly without real ONTAP hardware.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "edge" / "raspberry-pi" / "sensors"))

# Test constants — use .invalid TLD (RFC 6761) to avoid gitleaks false positives
TEST_ONTAP_HOST = "ontap.test.invalid"
TEST_ONTAP_USER = "svc-iot-telemetry"
TEST_ONTAP_PASSWORD = "test-password"


# Realistic ONTAP REST API mock responses
MOCK_CLUSTER_RESPONSE = {
    "name": "edge-cluster-01",
    "version": {
        "full": "NetApp Release 9.15.1",
        "generation": 9,
        "major": 15,
        "minor": 1,
    },
}

MOCK_METRICS_RESPONSE = {
    "records": [
        {
            "timestamp": "2026-05-29T10:00:00Z",
            "iops": {"read": 150, "write": 80, "total": 230},
            "throughput": {"read": 15728640, "write": 8388608},
            "latency": {"read": 920, "write": 1350},
        }
    ]
}

MOCK_VOLUMES_RESPONSE = {
    "records": [
        {
            "name": "vol0",
            "svm": {"name": "svm-root"},
            "space": {"used": 500000000, "size": 1000000000},
            "statistics": {},
        },
        {
            "name": ".snapshot_copies",
            "svm": {"name": "svm-iot"},
            "space": {},
            "statistics": {},
        },
        {
            "name": "inspection_images",
            "svm": {"name": "svm-iot"},
            "space": {"used": 2147483648, "size": 8589934592},
            "statistics": {
                "iops_raw": {"read": 120, "write": 45, "total": 165},
                "throughput_raw": {"read": 15938355, "write": 6082355},
                "latency_raw": {"read": 850, "write": 1200},
            },
        },
        {
            "name": "sensor_data",
            "svm": {"name": "svm-iot"},
            "space": {"used": 536870912, "size": 4294967296},
            "statistics": {
                "iops_raw": {"read": 30, "write": 200, "total": 230},
                "throughput_raw": {"read": 3145728, "write": 20971520},
                "latency_raw": {"read": 450, "write": 600},
            },
        },
    ]
}

MOCK_NODES_RESPONSE = {
    "records": [
        {
            "name": "edge-cluster-01-01",
            "statistics": {"processor_utilization_raw": 35.2},
        },
        {
            "name": "edge-cluster-01-02",
            "statistics": {"processor_utilization_raw": 28.8},
        },
    ]
}


class TestONTAPTelemetryE2E:
    """End-to-end tests for the ONTAP telemetry pipeline."""

    @patch.dict("os.environ", {
        "ONTAP_HOST": "ontap.test.invalid",
        "ONTAP_USER": "svc-iot-telemetry",
        "ONTAP_PASSWORD": "test-password",
        "ONTAP_VERIFY_SSL": "false",
        "DEVICE_ID": "rpi5-e2e-test",
        "COLLECTION_INTERVAL_SECONDS": "60",
        
    })
    def test_full_collection_cycle(self):
        """Test a complete collection cycle: connect → collect → format → upload."""
        import importlib
        import ontap_telemetry as ot
        importlib.reload(ot)

        client = ot.ONTAPClient(TEST_ONTAP_HOST, "svc-iot-telemetry", "test-password", verify_ssl=False)

        # Mock all ONTAP API calls
        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "/cluster" in url and "/metrics" not in url and "/nodes" not in url:
                resp.json.return_value = MOCK_CLUSTER_RESPONSE
            elif "/cluster/metrics" in url:
                resp.json.return_value = MOCK_METRICS_RESPONSE
            elif "/storage/volumes" in url:
                resp.json.return_value = MOCK_VOLUMES_RESPONSE
            elif "/cluster/nodes" in url:
                resp.json.return_value = MOCK_NODES_RESPONSE
            else:
                resp.json.return_value = {}
            return resp

        with patch.object(client._session, "get", side_effect=mock_get):
            # Step 1: Get cluster info
            cluster_info = client.get_cluster_info()
            assert cluster_info["name"] == "edge-cluster-01"
            assert "9.15.1" in cluster_info["ontap_version"]

            # Step 2: Collect metrics
            cluster_metrics = client.get_cluster_metrics()
            assert cluster_metrics["iops_total"] == 230
            assert cluster_metrics["latency_read_us"] == 920

            # Step 3: Collect volume metrics
            volumes = client.get_volume_metrics()
            assert len(volumes) == 2  # vol0 and .snapshot_copies filtered out
            assert volumes[0]["name"] == "inspection_images"
            assert volumes[0]["metrics"]["capacity_used_percent"] == 25.0
            assert volumes[1]["name"] == "sensor_data"

            # Step 4: Collect node metrics
            node_metrics = client.get_node_metrics()
            assert node_metrics["cpu_utilization_percent"] == 32.0  # avg of 35.2 and 28.8
            assert node_metrics["node_count"] == 2

            # Step 5: Build message
            message = ot.build_telemetry_message(
                cluster_info, cluster_metrics, volumes, node_metrics
            )

            # Verify message structure
            assert message["schema_version"] == "1.0"
            assert message["device_id"] == "rpi5-e2e-test"
            assert message["message_type"] == "ontap_telemetry"
            assert len(message["payload"]["volumes"]) == 2
            assert message["payload"]["cluster"]["name"] == "edge-cluster-01"
            assert message["payload"]["node_metrics"]["cpu_utilization_percent"] == 32.0

            # Step 6: Save to ONTAP NFS (mocked via tmp dir)
            import tempfile
            with patch.dict("os.environ", {"OUTPUT_PATH": tempfile.mkdtemp()}):
                importlib.reload(ot)
                success = ot.save_to_ontap(message)
                assert success is True

    @patch.dict("os.environ", {
        "ONTAP_HOST": "ontap.test.invalid",
        "ONTAP_USER": "svc-iot-telemetry",
        "ONTAP_PASSWORD": "test-password",
        "DEVICE_ID": "rpi5-e2e-test",
        "OUTPUT_PATH": "/tmp/test-ontap-telemetry",
    })
    def test_save_failure_handling(self):
        """Test that save failures are handled gracefully."""
        import importlib
        import ontap_telemetry as ot
        importlib.reload(ot)

        message = ot.build_telemetry_message(
            {"name": "test", "ontap_version": "9.15.1"},
            {}, [], {}
        )

        # Simulate write failure (non-existent path)
        with patch.dict("os.environ", {"OUTPUT_PATH": "/nonexistent/path"}):
            importlib.reload(ot)
            success = ot.save_to_ontap(message)
            assert success is False

    @patch.dict("os.environ", {
        "ONTAP_HOST": "ontap.test.invalid",
        "ONTAP_USER": "svc-iot-telemetry",
        "ONTAP_PASSWORD": "test-password",
        "DEVICE_ID": "rpi5-e2e-test",
        "OUTPUT_PATH": "/tmp/test-ontap-telemetry",
    })
    def test_save_http_error_handling(self):
        """Test that save to non-writable path is handled gracefully."""
        import importlib
        import ontap_telemetry as ot
        importlib.reload(ot)

        message = ot.build_telemetry_message(
            {"name": "test", "ontap_version": "9.15.1"},
            {}, [], {}
        )

        # Simulate permission error
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("Permission denied")):
            success = ot.save_to_ontap(message)
            assert success is False

    @patch.dict("os.environ", {
        "ONTAP_HOST": "ontap.test.invalid",
        "ONTAP_USER": "svc-iot-telemetry",
        "ONTAP_PASSWORD": "test-password",
        "DEVICE_ID": "rpi5-e2e-test",
    })
    def test_volume_capacity_calculation(self):
        """Test that volume capacity percentage is calculated correctly."""
        import importlib
        import ontap_telemetry as ot
        importlib.reload(ot)

        client = ot.ONTAPClient(TEST_ONTAP_HOST, "svc-iot-telemetry", "test-password", verify_ssl=False)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "records": [
                {
                    "name": "test_vol",
                    "svm": {"name": "svm1"},
                    "space": {"used": 750000000000, "size": 1000000000000},  # 75%
                    "statistics": {
                        "iops_raw": {"read": 0, "write": 0, "total": 0},
                        "throughput_raw": {"read": 0, "write": 0},
                        "latency_raw": {"read": 0, "write": 0},
                    },
                }
            ]
        }

        with patch.object(client._session, "get", return_value=mock_response):
            volumes = client.get_volume_metrics()
            assert len(volumes) == 1
            assert volumes[0]["metrics"]["capacity_used_percent"] == 75.0

    @patch.dict("os.environ", {
        "ONTAP_HOST": "ontap.test.invalid",
        "ONTAP_USER": "svc-iot-telemetry",
        "ONTAP_PASSWORD": "test-password",
        "DEVICE_ID": "rpi5-e2e-test",
    })
    def test_message_schema_compliance(self):
        """Test that generated messages comply with the data schema design."""
        import importlib
        import ontap_telemetry as ot
        importlib.reload(ot)

        message = ot.build_telemetry_message(
            cluster_info={"name": "cluster-1", "ontap_version": "9.15.1"},
            cluster_metrics={"iops_total": 500, "latency_read_us": 1000},
            volumes=[{
                "name": "vol1",
                "svm": "svm1",
                "metrics": {"iops_total": 100, "capacity_used_percent": 50.0},
            }],
            node_metrics={"cpu_utilization_percent": 40.0},
        )

        # Schema compliance checks
        assert "schema_version" in message
        assert message["schema_version"] == "1.0"
        assert "message_id" in message
        assert len(message["message_id"]) == 36  # UUID format
        assert "device_id" in message
        assert "timestamp" in message
        assert "message_type" in message
        assert message["message_type"] == "ontap_telemetry"
        assert "payload" in message

        # Verify timestamp is valid ISO 8601
        ts = message["timestamp"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None  # Must be timezone-aware
