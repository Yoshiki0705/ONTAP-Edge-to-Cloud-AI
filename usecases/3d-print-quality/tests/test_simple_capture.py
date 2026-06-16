"""Unit tests for simple_capture.py (primary ONTAP-centric pipeline).

Tests the main capture pipeline:
  capture_image → save_to_ontap → invoke_analysis_lambda → save_result_to_ontap
"""

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[3] / "edge" / "raspberry-pi" / "camera"))


class TestSaveToOntap:
    """Tests for save_to_ontap function."""

    def test_saves_image_to_correct_path(self, tmp_path):
        """Test that image is saved to date-structured directory."""
        with patch.dict("os.environ", {"ONTAP_NFS_PATH": str(tmp_path), "DEVICE_ID": "rpi5-test"}):
            import importlib
            import simple_capture as sc
            importlib.reload(sc)

            image_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # fake JPEG
            timestamp = "20260529T103000Z"

            result_path = sc.save_to_ontap(image_bytes, timestamp)

            assert result_path.exists()
            assert result_path.read_bytes() == image_bytes
            assert "rpi5-test" in result_path.name
            assert timestamp in result_path.name
            # Verify date directory structure
            assert "/2026/" in str(result_path) or "\\2026\\" in str(result_path)

    def test_creates_directories(self, tmp_path):
        """Test that nested date directories are created automatically."""
        with patch.dict("os.environ", {"ONTAP_NFS_PATH": str(tmp_path), "DEVICE_ID": "rpi5-test"}):
            import importlib
            import simple_capture as sc
            importlib.reload(sc)

            image_bytes = b"\xff\xd8" + b"\x00" * 50
            timestamp = "20260101T000000Z"

            result_path = sc.save_to_ontap(image_bytes, timestamp)
            assert result_path.exists()


class TestSaveResultToOntap:
    """Tests for save_result_to_ontap function."""

    def test_saves_result_json(self, tmp_path):
        """Test that analysis result is saved as JSON."""
        with patch.dict("os.environ", {"ONTAP_RESULT_PATH": str(tmp_path), "DEVICE_ID": "rpi5-test"}):
            import importlib
            import simple_capture as sc
            importlib.reload(sc)

            result = {"status": "anomaly_detected", "confidence": 0.87}
            timestamp = "20260529T103000Z"

            sc.save_result_to_ontap(result, timestamp)

            # Find the saved file
            json_files = list(tmp_path.rglob("*.json"))
            assert len(json_files) == 1

            saved = json.loads(json_files[0].read_text())
            assert saved["status"] == "anomaly_detected"
            assert saved["confidence"] == 0.87


class TestInvokeAnalysisLambda:
    """Tests for invoke_analysis_lambda function."""

    def test_invokes_lambda_with_correct_payload(self, tmp_path):
        """Test that Lambda is invoked with correct bucket and key."""
        with patch.dict("os.environ", {
            "ONTAP_NFS_PATH": str(tmp_path),
            "S3_BUCKET": "test-bucket",
            "LAMBDA_FUNCTION_NAME": "test-analyzer",
            "AWS_REGION": "ap-northeast-1",
            "DEVICE_ID": "rpi5-test",
        }):
            import importlib
            import simple_capture as sc
            importlib.reload(sc)

            image_path = tmp_path / "2026" / "05" / "29" / "20260529T103000Z_rpi5-test.jpg"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_bytes = b"\xff\xd8" + b"\x00" * 100

            mock_lambda = MagicMock()
            mock_lambda.invoke.return_value = {
                "Payload": MagicMock(read=MagicMock(return_value=json.dumps({
                    "statusCode": 200,
                    "body": {"status": "normal", "confidence": 0.95}
                }).encode()))
            }

            mock_s3 = MagicMock()

            with patch("boto3.client") as mock_boto:
                def client_factory(service, **kwargs):
                    if service == "lambda":
                        return mock_lambda
                    elif service == "s3":
                        return mock_s3
                    return MagicMock()

                mock_boto.side_effect = client_factory
                result = sc.invoke_analysis_lambda(image_path, image_bytes)

            assert result is not None
            # Verify S3 upload was called
            mock_s3.put_object.assert_called_once()
            # Verify Lambda was invoked
            mock_lambda.invoke.assert_called_once()
            call_kwargs = mock_lambda.invoke.call_args[1]
            assert call_kwargs["FunctionName"] == "test-analyzer"

    def test_returns_none_on_lambda_failure(self, tmp_path):
        """Test graceful handling of Lambda invocation failure."""
        with patch.dict("os.environ", {
            "ONTAP_NFS_PATH": str(tmp_path),
            "S3_BUCKET": "test-bucket",
            "LAMBDA_FUNCTION_NAME": "test-analyzer",
            "AWS_REGION": "ap-northeast-1",
            "DEVICE_ID": "rpi5-test",
        }):
            import importlib
            import simple_capture as sc
            importlib.reload(sc)

            image_path = tmp_path / "test.jpg"
            image_bytes = b"\xff\xd8" + b"\x00" * 100

            with patch("boto3.client") as mock_boto:
                mock_client = MagicMock()
                mock_client.invoke.side_effect = Exception("Lambda timeout")
                mock_client.put_object = MagicMock()
                mock_boto.return_value = mock_client

                result = sc.invoke_analysis_lambda(image_path, image_bytes)

            assert result is None

    def test_skips_when_no_s3_bucket(self, tmp_path):
        """Test that analysis is skipped when S3_BUCKET is not set."""
        with patch.dict("os.environ", {
            "ONTAP_NFS_PATH": str(tmp_path),
            "S3_BUCKET": "",
            "DEVICE_ID": "rpi5-test",
        }):
            import importlib
            import simple_capture as sc
            importlib.reload(sc)

            # capture_and_analyze should print skip message and return True
            with patch.object(sc, "capture_image", return_value=(b"\xff\xd8\x00", "20260529T103000Z")):
                with patch.object(sc, "save_to_ontap", return_value=tmp_path / "test.jpg"):
                    result = sc.capture_and_analyze(skip_analyze=False)

            assert result is True  # Succeeds (just skips analysis)
