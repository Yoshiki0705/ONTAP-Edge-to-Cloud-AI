"""Unit tests for the message buffer module."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Add edge code to path
sys.path.insert(0, str(Path(__file__).parent.parent / "edge" / "raspberry-pi" / "camera"))

from buffer import MessageBuffer
from config import BufferConfig


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database path."""
    return str(tmp_path / "test_buffer.db")


@pytest.fixture
def buffer(tmp_db):
    """Create a MessageBuffer instance with temp DB."""
    config = BufferConfig()
    # Override db_path via object creation (frozen dataclass workaround)
    config = BufferConfig.__new__(BufferConfig)
    object.__setattr__(config, "db_path", tmp_db)
    object.__setattr__(config, "max_size_mb", 10)
    object.__setattr__(config, "flush_batch_size", 5)

    buf = MessageBuffer(config)
    buf.open()
    yield buf
    buf.close()


class TestMessageBuffer:
    """Tests for MessageBuffer."""

    def test_enqueue_and_count(self, buffer):
        """Test basic enqueue and count."""
        assert buffer.pending_count() == 0

        buffer.enqueue("image_capture", {"test": "data1"})
        assert buffer.pending_count() == 1

        buffer.enqueue("sensor_reading", {"test": "data2"})
        assert buffer.pending_count() == 2

    def test_peek_returns_oldest_first(self, buffer):
        """Test that peek returns messages in FIFO order."""
        buffer.enqueue("type_a", {"order": 1})
        buffer.enqueue("type_b", {"order": 2})
        buffer.enqueue("type_c", {"order": 3})

        messages = buffer.peek(batch_size=2)
        assert len(messages) == 2
        assert messages[0]["metadata"]["order"] == 1
        assert messages[1]["metadata"]["order"] == 2

    def test_remove_deletes_entry(self, buffer):
        """Test that remove deletes a specific entry."""
        entry_id = buffer.enqueue("test", {"data": "value"})
        assert buffer.pending_count() == 1

        buffer.remove(entry_id)
        assert buffer.pending_count() == 0

    def test_mark_failed_increments_retry(self, buffer):
        """Test that mark_failed increments retry count."""
        entry_id = buffer.enqueue("test", {"data": "value"})

        buffer.mark_failed(entry_id, "Connection timeout")
        messages = buffer.peek()
        assert messages[0]["retry_count"] == 1

        buffer.mark_failed(entry_id, "Connection timeout again")
        messages = buffer.peek()
        assert messages[0]["retry_count"] == 2

    def test_peek_with_image_path(self, buffer):
        """Test enqueue with image path."""
        entry_id = buffer.enqueue(
            "image_capture",
            {"timestamp": "2026-01-01T00:00:00Z"},
            image_path="/tmp/test.jpg",
        )

        messages = buffer.peek()
        assert messages[0]["image_path"] == "/tmp/test.jpg"
        assert messages[0]["message_type"] == "image_capture"

    def test_empty_peek_returns_empty_list(self, buffer):
        """Test that peek on empty buffer returns empty list."""
        messages = buffer.peek()
        assert messages == []

    def test_context_manager(self, tmp_db):
        """Test context manager protocol."""
        config = BufferConfig.__new__(BufferConfig)
        object.__setattr__(config, "db_path", tmp_db)
        object.__setattr__(config, "max_size_mb", 10)
        object.__setattr__(config, "flush_batch_size", 5)

        with MessageBuffer(config) as buf:
            buf.enqueue("test", {"data": "value"})
            assert buf.pending_count() == 1
