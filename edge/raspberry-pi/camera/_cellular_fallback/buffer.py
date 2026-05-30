"""Local message buffer for offline resilience.

Uses SQLite to persist messages when network is unavailable.
Messages are flushed to the upload endpoint when connectivity returns.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import BufferConfig

logger = logging.getLogger(__name__)


class MessageBuffer:
    """SQLite-backed message buffer for guaranteed delivery."""

    def __init__(self, config: BufferConfig) -> None:
        self._config = config
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        """Initialize the buffer database."""
        db_path = Path(self._config.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._create_tables()
        logger.info("Message buffer opened: %s", db_path)

    def _create_tables(self) -> None:
        """Create buffer tables if they don't exist."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                message_type TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                image_path TEXT,
                retry_count INTEGER DEFAULT 0,
                last_error TEXT
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pending_created
            ON pending_messages(created_at)
        """)
        self._conn.commit()

    def enqueue(
        self,
        message_type: str,
        metadata: dict,
        image_path: str | None = None,
    ) -> int:
        """Add a message to the buffer.

        Args:
            message_type: Type of message (image_capture, sensor_reading, etc.)
            metadata: Message metadata as dict
            image_path: Optional path to local image file

        Returns:
            Buffer entry ID

        Raises:
            BufferFullError if buffer exceeds max size and oldest entries
            have been evicted.
        """
        # Check buffer size and evict oldest if necessary
        self._evict_if_full()

        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """
            INSERT INTO pending_messages (created_at, message_type, metadata_json, image_path)
            VALUES (?, ?, ?, ?)
            """,
            (now, message_type, json.dumps(metadata), image_path),
        )
        self._conn.commit()
        entry_id = cursor.lastrowid
        logger.debug("Buffered message %d (type=%s)", entry_id, message_type)
        return entry_id

    def _evict_if_full(self) -> None:
        """Evict oldest entries if buffer exceeds max size."""
        db_path = Path(self._config.db_path)
        if not db_path.exists():
            return

        # Check total size of buffer DB + image files
        db_size_mb = db_path.stat().st_size / (1024 * 1024)
        image_dir = db_path.parent / "images"
        image_size_mb = 0.0
        if image_dir.exists():
            image_size_mb = sum(
                f.stat().st_size for f in image_dir.iterdir() if f.is_file()
            ) / (1024 * 1024)

        total_mb = db_size_mb + image_size_mb

        if total_mb < self._config.max_size_mb:
            return

        # Evict oldest 10% of entries
        evict_count = max(1, self.pending_count() // 10)
        logger.warning(
            "Buffer full (%.1f MB / %d MB). Evicting %d oldest entries.",
            total_mb,
            self._config.max_size_mb,
            evict_count,
        )

        cursor = self._conn.execute(
            "SELECT id, image_path FROM pending_messages ORDER BY created_at ASC LIMIT ?",
            (evict_count,),
        )
        for row in cursor.fetchall():
            entry_id, img_path = row
            # Delete associated image file
            if img_path and Path(img_path).exists():
                try:
                    Path(img_path).unlink()
                except OSError:
                    pass
            self._conn.execute("DELETE FROM pending_messages WHERE id = ?", (entry_id,))

        self._conn.commit()
        logger.info("Evicted %d oldest buffered messages", evict_count)

    def peek(self, batch_size: int | None = None) -> list[dict]:
        """Get pending messages without removing them.

        Args:
            batch_size: Max messages to return. Defaults to config flush_batch_size.

        Returns:
            List of message dicts with id, metadata, image_path
        """
        limit = batch_size or self._config.flush_batch_size
        cursor = self._conn.execute(
            """
            SELECT id, created_at, message_type, metadata_json, image_path, retry_count
            FROM pending_messages
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "created_at": row[1],
                "message_type": row[2],
                "metadata": json.loads(row[3]),
                "image_path": row[4],
                "retry_count": row[5],
            }
            for row in rows
        ]

    def remove(self, entry_id: int) -> None:
        """Remove a successfully uploaded message from the buffer."""
        self._conn.execute(
            "DELETE FROM pending_messages WHERE id = ?", (entry_id,)
        )
        self._conn.commit()

    def mark_failed(self, entry_id: int, error: str) -> None:
        """Record a failed upload attempt."""
        self._conn.execute(
            """
            UPDATE pending_messages
            SET retry_count = retry_count + 1, last_error = ?
            WHERE id = ?
            """,
            (error, entry_id),
        )
        self._conn.commit()

    def pending_count(self) -> int:
        """Return number of pending messages."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM pending_messages")
        return cursor.fetchone()[0]

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Message buffer closed")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
