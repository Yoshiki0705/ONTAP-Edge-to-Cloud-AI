"""Pytest configuration — mock hardware-dependent modules for CI/test environments."""

import os
import sys
from unittest.mock import MagicMock

# Several handlers construct boto3 clients at module scope, so importing one runs
# botocore's endpoint resolution before any test body executes. That reads the
# ambient AWS configuration: on a developer machine it is present and the import
# succeeds, on a CI runner it is not and the import raises NoRegionError. Four
# tests in tests/test_image_analyzer_store_result.py passed locally and errored in
# CI for exactly this reason.
#
# Set only when absent, so a deliberate override still works. The credentials are
# obvious placeholders and are also a safeguard: a test that slips past its mock
# cannot reach a real account with them.
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")

# Mock cv2 (OpenCV) — not available in CI or non-Pi environments
cv2_mock = MagicMock()
cv2_mock.VideoCapture.return_value = MagicMock()
cv2_mock.imencode.return_value = (True, MagicMock(tobytes=lambda: b"\xff\xd8\xff\xe0" + b"\x00" * 100))
sys.modules.setdefault("cv2", cv2_mock)

# Mock confluent_kafka — not available in CI without Kafka broker
kafka_mock = MagicMock()
kafka_mock.Producer.return_value = MagicMock()
sys.modules.setdefault("confluent_kafka", kafka_mock)
