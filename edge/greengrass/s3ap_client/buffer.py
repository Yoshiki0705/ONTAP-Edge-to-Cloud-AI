"""Local disk buffer for S3 AP uploads.

Persists pending uploads in SQLite for offline resilience.
When network is available, flushes buffered items via S3APUploader.
"""

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .config import BufferConfig

logger = logging.getLogger(__name__)


class S3APBuffer:
    """SQLite-backed buffer for S3 AP PutObject operations."""

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
        logger.info("S3 AP buffer opened: %s", db_path)

    def _require_open(self) -> sqlite3.Connection:
        """Return the live connection, or raise if `open()` was not called.

        This was `assert self._conn is not None`. `assert` is removed under
        `python -O`, which edge deployments may well use, and the statement
        after it would then raise AttributeError on None from inside sqlite3
        rather than naming the actual mistake.
        """
        if self._conn is None:
            raise RuntimeError(
                "buffer is not open — call open() before using it"
            )
        return self._conn

    def _create_tables(self) -> None:
        """Create buffer tables."""
        self._require_open()
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                s3_key TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                data_path TEXT NOT NULL,
                metadata_json TEXT,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                last_error TEXT
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pending_created
            ON pending_uploads(created_at)
        """)
        self._conn.commit()

    def enqueue(
        self,
        s3_key: str,
        data_path: str,
        content_type: str = "application/octet-stream",
        metadata: dict | None = None,
        size_bytes: int = 0,
    ) -> int:
        """Add a pending upload to the buffer.

        Args:
            s3_key: Target S3 object key
            data_path: Local path to the data file
            content_type: MIME type
            metadata: Optional S3 user metadata
            size_bytes: Size of the data

        Returns:
            Buffer entry ID
        """
        self._require_open()
        self._evict_if_full()

        now = datetime.now(UTC).isoformat()
        cursor = self._conn.execute(
            """
            INSERT INTO pending_uploads
                (created_at, s3_key, content_type, data_path, metadata_json, size_bytes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                s3_key,
                content_type,
                data_path,
                json.dumps(metadata) if metadata else None,
                size_bytes,
            ),
        )
        self._conn.commit()
        entry_id = cursor.lastrowid
        logger.debug("Buffered upload %d: %s (%d bytes)", entry_id, s3_key, size_bytes)
        return entry_id

    def peek(self, batch_size: int | None = None) -> list[dict]:
        """Get pending uploads without removing them (FIFO order)."""
        self._require_open()
        limit = batch_size or self._config.flush_batch_size
        cursor = self._conn.execute(
            """
            SELECT id, created_at, s3_key, content_type, data_path,
                   metadata_json, size_bytes, retry_count, last_error
            FROM pending_uploads
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            {
                "id": row[0],
                "created_at": row[1],
                "s3_key": row[2],
                "content_type": row[3],
                "data_path": row[4],
                "metadata": json.loads(row[5]) if row[5] else None,
                "size_bytes": row[6],
                "retry_count": row[7],
                "last_error": row[8],
            }
            for row in cursor.fetchall()
        ]

    def remove(self, entry_id: int) -> None:
        """Remove a successfully uploaded entry."""
        self._require_open()
        self._conn.execute(
            "DELETE FROM pending_uploads WHERE id = ?", (entry_id,)
        )
        self._conn.commit()

    def mark_failed(self, entry_id: int, error: str) -> None:
        """Record a failed upload attempt."""
        self._require_open()
        self._conn.execute(
            """
            UPDATE pending_uploads
            SET retry_count = retry_count + 1, last_error = ?
            WHERE id = ?
            """,
            (error, entry_id),
        )
        self._conn.commit()

    def pending_count(self) -> int:
        """Return number of pending uploads."""
        self._require_open()
        cursor = self._conn.execute("SELECT COUNT(*) FROM pending_uploads")
        return cursor.fetchone()[0]

    def _evict_if_full(self) -> None:
        """Evict oldest entries if buffer exceeds max size."""
        db_path = Path(self._config.db_path)
        if not db_path.exists():
            return
        db_size_mb = db_path.stat().st_size / (1024 * 1024)
        if db_size_mb < self._config.max_size_mb:
            return

        evict_count = max(1, self.pending_count() // 10)
        logger.warning(
            "Buffer full (%.1f MB / %d MB). Evicting %d oldest entries.",
            db_size_mb,
            self._config.max_size_mb,
            evict_count,
        )
        self._conn.execute(
            """
            DELETE FROM pending_uploads
            WHERE id IN (
                SELECT id FROM pending_uploads
                ORDER BY created_at ASC LIMIT ?
            )
            """,
            (evict_count,),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
