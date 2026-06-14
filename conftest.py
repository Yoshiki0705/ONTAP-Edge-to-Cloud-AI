"""Pytest configuration — mock hardware-dependent modules for CI/test environments."""

import sys
from unittest.mock import MagicMock

# Mock cv2 (OpenCV) — not available in CI or non-Pi environments
cv2_mock = MagicMock()
cv2_mock.VideoCapture.return_value = MagicMock()
cv2_mock.imencode.return_value = (True, MagicMock(tobytes=lambda: b"\xff\xd8\xff\xe0" + b"\x00" * 100))
sys.modules.setdefault("cv2", cv2_mock)

# Mock confluent_kafka — not available in CI without Kafka broker
kafka_mock = MagicMock()
kafka_mock.Producer.return_value = MagicMock()
sys.modules.setdefault("confluent_kafka", kafka_mock)
