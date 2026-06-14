"""Kafka producer for edge devices.

Publishes structured events to Kafka topics. Falls back to local file buffer
when Kafka is unreachable (factory disconnection resilience).

Configuration via environment variables:
    KAFKA_BOOTSTRAP_SERVERS: Kafka broker addresses (comma-separated)
    KAFKA_TOPIC: Target topic (default: factory.events.raw)
    KAFKA_ENABLED: "true" to enable Kafka publishing (default: "false")
    KAFKA_BUFFER_PATH: Local buffer directory when Kafka is unreachable
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "factory.events.raw")
KAFKA_ENABLED = os.getenv("KAFKA_ENABLED", "false").lower() == "true"
KAFKA_BUFFER_PATH = os.getenv("KAFKA_BUFFER_PATH", "/tmp/kafka-buffer")


class EventPublisher:
    """Publishes events to Kafka with local buffer fallback.

    Usage:
        publisher = EventPublisher()
        publisher.publish(event_dict)
        publisher.flush()  # Ensure delivery
    """

    def __init__(self):
        self._producer = None
        self._buffer_dir = Path(KAFKA_BUFFER_PATH)

        if KAFKA_ENABLED:
            try:
                from confluent_kafka import Producer

                self._producer = Producer({
                    "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
                    "client.id": f"edge-{os.getenv('DEVICE_ID', 'unknown')}",
                    "acks": "all",
                    "retries": 3,
                    "retry.backoff.ms": 1000,
                    "linger.ms": 100,  # Batch for efficiency
                    "compression.type": "lz4",
                })
                print(f"[kafka] Connected to {KAFKA_BOOTSTRAP_SERVERS}")
            except ImportError:
                print("[kafka] confluent-kafka not installed, falling back to buffer")
                self._producer = None
            except Exception as e:
                print(f"[kafka] Connection failed: {e}, falling back to buffer")
                self._producer = None

    def publish(self, event: dict, topic: str | None = None) -> bool:
        """Publish event to Kafka or buffer locally.

        Args:
            event: v3-aligned event dict
            topic: Override default topic

        Returns:
            True if published to Kafka, False if buffered locally
        """
        target_topic = topic or KAFKA_TOPIC
        event_json = json.dumps(event, ensure_ascii=False)

        # Partition key: site_id + equipment_id (ordering guarantee per equipment)
        partition_key = f"{event.get('site_id', '')}-{event.get('equipment_id', '')}"

        if self._producer is not None:
            try:
                self._producer.produce(
                    target_topic,
                    key=partition_key.encode("utf-8"),
                    value=event_json.encode("utf-8"),
                    callback=self._delivery_callback,
                )
                return True
            except Exception as e:
                print(f"[kafka] Publish failed: {e}, buffering locally")
                self._buffer_event(event_json)
                return False
        else:
            self._buffer_event(event_json)
            return False

    def flush(self, timeout: float = 10.0) -> int:
        """Flush pending Kafka messages.

        Returns:
            Number of messages still in queue (0 = all delivered)
        """
        if self._producer is not None:
            return self._producer.flush(timeout)
        return 0

    def replay_buffer(self) -> int:
        """Replay locally buffered events to Kafka.

        Call this after Kafka connectivity is restored.

        Returns:
            Number of events replayed
        """
        if not self._buffer_dir.exists():
            return 0

        replayed = 0
        for f in sorted(self._buffer_dir.glob("*.json")):
            try:
                event = json.loads(f.read_text(encoding="utf-8"))
                if self.publish(event):
                    f.unlink()  # Remove after successful publish
                    replayed += 1
            except Exception as e:
                print(f"[kafka] Replay failed for {f.name}: {e}")
                break  # Stop replay on failure to maintain ordering

        if replayed > 0:
            print(f"[kafka] Replayed {replayed} buffered events")

        return replayed

    def _buffer_event(self, event_json: str) -> None:
        """Save event to local filesystem buffer."""
        self._buffer_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        buffer_file = self._buffer_dir / f"{timestamp}.json"
        buffer_file.write_text(event_json, encoding="utf-8")

    @staticmethod
    def _delivery_callback(err, msg):
        """Kafka delivery confirmation callback."""
        if err is not None:
            print(f"[kafka] Delivery failed: {err}")
        # Successful delivery — silent (avoid log spam in continuous mode)
