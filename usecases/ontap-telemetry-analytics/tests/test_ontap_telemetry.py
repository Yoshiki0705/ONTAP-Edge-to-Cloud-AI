"""Unit tests for ONTAP telemetry collector."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[3] / "edge" / "raspberry-pi" / "sensors"))


class TestBuildTelemetryMessage:
    """Tests for message building."""

    def test_message_structure(self):
        """Test that telemetry message has correct structure."""
        with patch.dict("os.environ", {"DEVICE_ID": "rpi5-test"}):
            import importlib

            import ontap_telemetry as ot
            importlib.reload(ot)

            msg = ot.build_telemetry_message(
                cluster_info={"name": "test-cluster", "ontap_version": "9.15.1"},
                cluster_metrics={"iops_total": 100},
                volumes=[{"name": "vol1", "svm": "svm1", "metrics": {"iops_total": 50}}],
                node_metrics={"cpu_utilization_percent": 25.0},
            )

            assert msg["schema_version"] == "1.0"
            assert msg["device_id"] == "rpi5-test"
            assert msg["message_type"] == "ontap_telemetry"
            assert "message_id" in msg
            assert "timestamp" in msg

            payload = msg["payload"]
            assert payload["cluster"]["name"] == "test-cluster"
            assert payload["cluster"]["ontap_version"] == "9.15.1"
            assert payload["volumes"][0]["name"] == "vol1"
            assert payload["node_metrics"]["cpu_utilization_percent"] == 25.0

    def test_message_id_is_unique(self):
        """Test that each message gets a unique ID."""
        with patch.dict("os.environ", {"DEVICE_ID": "rpi5-test"}):
            import importlib

            import ontap_telemetry as ot
            importlib.reload(ot)

            msg1 = ot.build_telemetry_message({}, {}, [], {})
            msg2 = ot.build_telemetry_message({}, {}, [], {})
            assert msg1["message_id"] != msg2["message_id"]


class TestONTAPClient:
    """Tests for ONTAPClient with mocked HTTP."""

    def test_get_cluster_info(self):
        """Test cluster info parsing."""
        import ontap_telemetry as ot

        client = ot.ONTAPClient("fake-host", "user", "pass", verify_ssl=False)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "name": "my-cluster",
            "version": {"full": "NetApp Release 9.15.1"},
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._session, "get", return_value=mock_response):
            info = client.get_cluster_info()
            assert info["name"] == "my-cluster"
            assert info["ontap_version"] == "NetApp Release 9.15.1"

    def test_get_volume_metrics_skips_internal(self):
        """Test that internal volumes (vol0, .*) are skipped."""
        import ontap_telemetry as ot

        client = ot.ONTAPClient("fake-host", "user", "pass", verify_ssl=False)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "records": [
                {"name": "vol0", "svm": {"name": "svm1"}, "space": {}, "statistics": {}},
                {"name": ".snapshots", "svm": {"name": "svm1"}, "space": {}, "statistics": {}},
                {
                    "name": "data_vol",
                    "svm": {"name": "svm1"},
                    "space": {"used": 1000, "size": 4000},
                    "statistics": {
                        "iops_raw": {"read": 10, "write": 5, "total": 15},
                        "throughput_raw": {"read": 1048576, "write": 524288},
                        "latency_raw": {"read": 500, "write": 800},
                    },
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._session, "get", return_value=mock_response):
            volumes = client.get_volume_metrics()
            assert len(volumes) == 1
            assert volumes[0]["name"] == "data_vol"
            assert volumes[0]["metrics"]["capacity_used_percent"] == 25.0
