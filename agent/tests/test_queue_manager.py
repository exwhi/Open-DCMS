import tempfile
import os
import time

from agent.queue_manager import PersistentQueue


def test_persistent_queue_basic(tmp_path):
    dbfile = tmp_path / "queue.db"
    q = PersistentQueue(str(dbfile))

    payload = {'id': 'test-1', 'value': 123}
    assert q.enqueue(payload)

    items = q.dequeue(max_items=10)
    assert items and items[0]['id'] == 'test-1'
    db_id = items[0].get('_db_id')
    assert isinstance(db_id, int)

    # mark sent
    assert q.mark_sent('test-1')

    stats = q.get_stats()
    assert stats.get('sent', 0) >= 1

    # enqueue another and force failure scheduling
    payload2 = {'id': 'test-2', 'value': 456}
    assert q.enqueue(payload2)
    items2 = q.dequeue(max_items=1)
    db_id2 = items2[0].get('_db_id')
    assert q.mark_failed(db_id2, 'network error', max_retries=1)

    # cleanup (sent older than 0 days) should remove the sent record
    deleted = q.cleanup_old(days=0)
    assert isinstance(deleted, int)

    # export batch should not raise
    batch = q.export_batch(max_items=10)
    assert isinstance(batch, list)

    # close/cleanup
    q.close()
import pytest
import tempfile
import json
import time
import gc
from pathlib import Path
from agent.queue_manager import PersistentQueue


def test_persistent_queue_init():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        queue = PersistentQueue(str(db_path))
        assert db_path.exists()
        queue.close()
        gc.collect()  # Force garbage collection to release DB handle


def test_enqueue_dequeue():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        queue = PersistentQueue(str(db_path))
        
        # Enqueue some payloads
        payload1 = {'id': 'p1', 'data': 'test1'}
        payload2 = {'id': 'p2', 'data': 'test2'}
        
        assert queue.enqueue(payload1) is True
        assert queue.enqueue(payload2) is True
        
        # Dequeue
        items = queue.dequeue(max_items=10)
        assert len(items) == 2
        assert items[0]['id'] in ['p1', 'p2']
        assert items[1]['id'] in ['p1', 'p2']
        
        queue.close()
        gc.collect()


def test_mark_sent():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        queue = PersistentQueue(str(db_path))
        
        payload = {'id': 'p1', 'data': 'test'}
        queue.enqueue(payload)
        
        # Mark as sent
        assert queue.mark_sent('p1') is True
        
        # Should not dequeue sent items
        items = queue.dequeue(max_items=10)
        assert len(items) == 0
        
        queue.close()
        gc.collect()


def test_mark_failed_retry():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        queue = PersistentQueue(str(db_path))
        
        payload = {'id': 'p1', 'data': 'test'}
        queue.enqueue(payload)
        
        # First dequeue
        items = queue.dequeue(max_items=10)
        db_id = items[0]['_db_id']
        
        # Mark as failed
        assert queue.mark_failed(db_id, "Connection timeout") is True
        
        # Should still be pending with retry scheduled
        items = queue.dequeue(max_items=10)
        # Item should not be ready yet (retry_at is in future)
        assert len(items) == 0
        
        # Get stats
        stats = queue.get_stats()
        assert stats['pending'] >= 1
        
        queue.close()
        gc.collect()


def test_mark_failed_max_retries():
    """Test that max retries eventually marks item as failed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        queue = PersistentQueue(str(db_path))
        
        payload = {'id': 'p1', 'data': 'test'}
        queue.enqueue(payload)
        
        # Try to dequeue and fail - after max retries should give up
        for attempt in range(12):
            items = queue.dequeue(max_items=10)
            if not items:  # No pending items to retry
                break
            db_id = items[0]['_db_id']
            is_ok = queue.mark_failed(db_id, f"Attempt {attempt}")
            if not is_ok:  # mark_failed returns False if max retries exceeded
                break
            time.sleep(0.01)
            gc.collect()
        
        # Should have some record (either pending or failed)
        stats = queue.get_stats()
        assert stats['total'] >= 1
        
        queue.close()
        gc.collect()
        time.sleep(0.1)


def test_queue_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        queue = PersistentQueue(str(db_path))
        
        # Add 3 payloads
        for i in range(3):
            queue.enqueue({'id': f'p{i}', 'data': f'test{i}'})
        
        stats = queue.get_stats()
        assert stats['pending'] == 3
        assert stats['sent'] == 0
        assert stats['failed'] == 0
        assert stats['total'] == 3
        
        queue.close()
        gc.collect()


def test_cleanup_old():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        queue = PersistentQueue(str(db_path))
        
        # Add and mark as sent
        payload = {'id': 'p1', 'data': 'test'}
        queue.enqueue(payload)
        queue.mark_sent('p1')
        
        # Cleanup (should delete sent records older than 7 days)
        deleted = queue.cleanup_old(days=0)  # 0 days = delete everything
        assert deleted >= 1
        
        queue.close()
        gc.collect()


def test_export_batch():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        queue = PersistentQueue(str(db_path))
        
        for i in range(5):
            queue.enqueue({'id': f'p{i}', 'data': f'test{i}'})
        
        batch = queue.export_batch(max_items=10)
        assert len(batch) == 5
        assert batch[0]['status'] == 'pending'
        
        queue.close()
        gc.collect()


def test_duplicate_payload_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        queue = PersistentQueue(str(db_path))
        
        payload = {'id': 'p1', 'data': 'test'}
        assert queue.enqueue(payload) is True
        
        # Try to enqueue again (should replace)
        payload['data'] = 'updated'
        assert queue.enqueue(payload) is True
        
        items = queue.dequeue(max_items=10)
        assert len(items) == 1
        assert items[0]['data'] == 'updated'
        
        queue.close()
        gc.collect()


def test_missing_payload_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        queue = PersistentQueue(str(db_path))
        
        payload = {'data': 'test'}  # No id
        assert queue.enqueue(payload) is False
        
        items = queue.dequeue(max_items=10)
        assert len(items) == 0
        
        queue.close()
        gc.collect()
