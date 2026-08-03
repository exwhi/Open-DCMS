"""Persistent queue manager for Agent data with retry tracking.

Uses SQLite for reliable storage of unsent payloads. Supports:
- Retry with exponential backoff
- Batch sending
- Deduplication
- Offline mode with local caching
"""
import sqlite3
import json
import time
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Default queue database location (can be overridden)
DEFAULT_QUEUE_DB = Path.home() / ".cache" / "open-dcms-agent" / "queue.db"


class PersistentQueue:
    """SQLite-backed persistent queue for agent payloads."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize queue manager.
        
        Args:
            db_path: Path to SQLite database. Defaults to ~/.cache/open-dcms-agent/queue.db
        """
        self.db_path = Path(db_path) if db_path else DEFAULT_QUEUE_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def close(self):
        """Close any open connections (cleanup for tests)."""
        pass

    def _init_db(self):
        """Create schema if not exists."""
        with sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0) as conn:
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload_id TEXT UNIQUE NOT NULL,
                    payload_json TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_retry_at TIMESTAMP,
                    next_retry_at TIMESTAMP,
                    status TEXT DEFAULT 'pending'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON queue(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_next_retry ON queue(next_retry_at)
            """)
            conn.commit()

    def enqueue(self, payload: Dict[str, Any]) -> bool:
        """Add payload to queue.
        
        Args:
            payload: Payload dict with 'id' field
            
        Returns:
            True if enqueued successfully
        """
        try:
            payload_id = payload.get('id')
            if not payload_id:
                logger.warning("Payload missing 'id' field, skipping")
                return False

            with sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO queue (payload_id, payload_json, status)
                    VALUES (?, ?, 'pending')
                """, (payload_id, json.dumps(payload)))
                conn.commit()
            logger.info(f"Enqueued payload {payload_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue: {e}")
            return False

    def dequeue(self, max_items: int = 100) -> List[Dict[str, Any]]:
        """Get next batch of payloads to send (respecting retry schedule).
        
        Args:
            max_items: Maximum items to return
            
        Returns:
            List of payloads ready to send
        """
        try:
            now = datetime.utcnow()
            with sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0) as conn:
                cursor = conn.execute("""
                    SELECT id, payload_id, payload_json FROM queue
                    WHERE status = 'pending'
                    AND (next_retry_at IS NULL OR next_retry_at <= ?)
                    ORDER BY created_at ASC
                    LIMIT ?
                """, (now, max_items))
                rows = cursor.fetchall()
            
            results = []
            for db_id, payload_id, payload_json in rows:
                try:
                    payload = json.loads(payload_json)
                    payload['_db_id'] = db_id  # Track for update
                    results.append(payload)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON for payload {payload_id}")
                    self.mark_failed(db_id, "Invalid JSON")
            
            return results
        except Exception as e:
            logger.error(f"Failed to dequeue: {e}")
            return []

    def mark_sent(self, payload_id: str) -> bool:
        """Mark payload as successfully sent.
        
        Args:
            payload_id: Payload ID
            
        Returns:
            True if updated
        """
        try:
            with sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0) as conn:
                cursor = conn.execute("""
                    UPDATE queue SET status = 'sent'
                    WHERE payload_id = ?
                """, (payload_id,))
                conn.commit()
            logger.info(f"Marked {payload_id} as sent")
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to mark sent: {e}")
            return False

    def mark_failed(self, db_id: int, error_msg: str, max_retries: int = 10) -> bool:
        """Mark payload as failed, schedule retry with exponential backoff.
        
        Args:
            db_id: Database row ID
            error_msg: Error message
            max_retries: Maximum retry attempts
            
        Returns:
            True if updated; False if max retries exceeded
        """
        try:
            with sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0) as conn:
                cursor = conn.execute("""
                    SELECT retry_count FROM queue WHERE id = ?
                """, (db_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                
                retry_count = row[0]
                if retry_count >= max_retries:
                    # Give up after max retries
                    conn.execute("""
                        UPDATE queue SET status = 'failed', last_error = ?
                        WHERE id = ?
                    """, (error_msg, db_id))
                    logger.warning(f"Payload {db_id} exceeded max retries")
                else:
                    # Schedule next retry: exponential backoff with jitter
                    backoff = min(2 ** retry_count + (hash(db_id) % 10), 3600)  # max 1 hour
                    next_retry = datetime.utcnow() + timedelta(seconds=backoff)
                    conn.execute("""
                        UPDATE queue 
                        SET retry_count = retry_count + 1,
                            status = 'pending',
                            last_error = ?,
                            last_retry_at = ?,
                            next_retry_at = ?
                        WHERE id = ?
                    """, (error_msg, datetime.utcnow(), next_retry, db_id))
                    logger.info(f"Retry scheduled for {db_id} in {backoff}s (attempt {retry_count + 1})")
                
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to mark failed: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics.
        
        Returns:
            Dict with pending/sent/failed counts
        """
        try:
            with sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0) as conn:
                cursor = conn.execute("""
                    SELECT status, COUNT(*) FROM queue GROUP BY status
                """)
                stats = dict(cursor.fetchall())
            return {
                'pending': stats.get('pending', 0),
                'sent': stats.get('sent', 0),
                'failed': stats.get('failed', 0),
                'total': sum(stats.values()),
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {'error': str(e)}

    def cleanup_old(self, days: int = 7) -> int:
        """Delete old sent records to save space.
        
        Args:
            days: Keep sent records for this many days
            
        Returns:
            Number of deleted rows
        """
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            with sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0) as conn:
                cursor = conn.execute("""
                    DELETE FROM queue
                    WHERE status = 'sent' AND created_at < ?
                """, (cutoff,))
                conn.commit()
            logger.info(f"Cleaned up {cursor.rowcount} old records")
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Failed to cleanup: {e}")
            return 0

    def export_batch(self, max_items: int = 1000) -> List[Dict[str, Any]]:
        """Export batch of pending/failed items for inspection.
        
        Returns:
            List of queue entries with status
        """
        try:
            with sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0) as conn:
                cursor = conn.execute("""
                    SELECT payload_id, status, retry_count, last_error, created_at
                    FROM queue
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (max_items,))
                rows = cursor.fetchall()
            return [
                {
                    'payload_id': r[0],
                    'status': r[1],
                    'retry_count': r[2],
                    'last_error': r[3],
                    'created_at': r[4],
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Failed to export batch: {e}")
            return []
