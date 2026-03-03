#!/usr/bin/env python3
"""
Simple standalone test for SQLite backend functionality.
"""

import os
import sys
import tempfile
import time
import traceback

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from python_task_queue.backends.sqlite import SQLiteBackend
from python_task_queue.models import Task, TaskStatus


def test_basic_operations():
    """Test basic CRUD operations."""
    print("Testing basic operations...")

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        backend = SQLiteBackend(database_path=db_path)

        # Test enqueue
        task1 = Task(name="test_task_1", payload={"key": "value"}, priority=5)
        backend.enqueue(task1)
        print(f"  ✓ Enqueued task: {task1.id}")

        # Test get_task
        retrieved = backend.get_task(task1.id)
        assert retrieved is not None
        assert retrieved.id == task1.id
        print(f"  ✓ Retrieved task: {retrieved.id}")

        # Test size
        assert backend.size() == 1
        print(f"  ✓ Queue size: {backend.size()}")

        # Test peek
        peeked = backend.peek()
        assert peeked is not None
        assert peeked.id == task1.id
        assert peeked.status == TaskStatus.PENDING
        print(f"  ✓ Peeked task still pending")

        # Test dequeue
        task2 = backend.dequeue()
        assert task2 is not None
        assert task2.id == task1.id
        assert task2.status == TaskStatus.RUNNING
        assert task2.started_at is not None
        print(f"  ✓ Dequeued task now running")

        # Test size after dequeue
        assert backend.size() == 0
        print(f"  ✓ Queue size after dequeue: {backend.size()}")

        # Test acknowledge
        backend.acknowledge(task2.id)
        retrieved = backend.get_task(task2.id)
        assert retrieved.status == TaskStatus.COMPLETED
        assert retrieved.completed_at is not None
        print(f"  ✓ Task acknowledged and completed")

        backend.close()
        print("  ✓ Basic operations test passed!")
        return True

    except Exception as e:
        print(f"  ✗ Basic operations test failed: {e}")
        traceback.print_exc()
        return False

    finally:
        try:
            os.unlink(db_path)
            for ext in ["-wal", "-shm"]:
                wal_path = db_path + ext
                if os.path.exists(wal_path):
                    os.unlink(wal_path)
        except Exception:
            pass


def test_multiple_tasks():
    """Test handling multiple tasks with priorities."""
    print("\nTesting multiple tasks...")

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        backend = SQLiteBackend(database_path=db_path)

        # Enqueue tasks with different priorities
        tasks = [
            Task(name="low", priority=10),
            Task(name="high", priority=1),
            Task(name="medium", priority=5),
        ]

        for task in tasks:
            backend.enqueue(task)

        assert backend.size() == 3
        print(f"  ✓ Enqueued 3 tasks")

        # Dequeue should return in priority order
        first = backend.dequeue()
        assert first.name == "high"
        print(f"  ✓ First dequeued: {first.name}")

        second = backend.dequeue()
        assert second.name == "medium"
        print(f"  ✓ Second dequeued: {second.name}")

        third = backend.dequeue()
        assert third.name == "low"
        print(f"  ✓ Third dequeued: {third.name}")

        backend.close()
        print("  ✓ Multiple tasks test passed!")
        return True

    except Exception as e:
        print(f"  ✗ Multiple tasks test failed: {e}")
        traceback.print_exc()
        return False

    finally:
        try:
            os.unlink(db_path)
            for ext in ["-wal", "-shm"]:
                wal_path = db_path + ext
                if os.path.exists(wal_path):
                    os.unlink(wal_path)
        except Exception:
            pass


def test_retry_logic():
    """Test task retry logic."""
    print("\nTesting retry logic...")

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        backend = SQLiteBackend(database_path=db_path)

        # Test task with retries
        task = Task(name="retry_task", max_retries=3)
        backend.enqueue(task)

        # Dequeue and fail it
        dequeued = backend.dequeue()
        backend.fail(dequeued.id, "Task failed")

        # Should be in RETRYING status
        retrieved = backend.get_task(task.id)
        assert retrieved.status == TaskStatus.RETRYING
        assert retrieved.retry_count == 1
        print(f"  ✓ Task marked as RETRYING (retry {retrieved.retry_count})")

        # Fail again
        retrieved.running()
        backend.fail(retrieved.id, "Failed again")
        retrieved = backend.get_task(task.id)
        assert retrieved.status == TaskStatus.RETRYING
        assert retrieved.retry_count == 2
        print(f"  ✓ Task retrying again (retry {retrieved.retry_count})")

        # Fail a third time (should move to FAILED)
        retrieved.running()
        backend.fail(retrieved.id, "Failed third time")
        retrieved = backend.get_task(task.id)
        assert retrieved.status == TaskStatus.FAILED
        assert retrieved.retry_count == 3
        print(f"  ✓ Task marked as FAILED after max retries")

        backend.close()
        print("  ✓ Retry logic test passed!")
        return True

    except Exception as e:
        print(f"  ✗ Retry logic test failed: {e}")
        traceback.print_exc()
        return False

    finally:
        try:
            os.unlink(db_path)
            for ext in ["-wal", "-shm"]:
                wal_path = db_path + ext
                if os.path.exists(wal_path):
                    os.unlink(wal_path)
        except Exception:
            pass


def test_persistence():
    """Test data persistence across backend restarts."""
    print("\nTesting persistence...")

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        # First backend instance
        backend1 = SQLiteBackend(database_path=db_path)
        task = Task(name="persistent_task", payload={"data": "value"}, max_retries=2)
        backend1.enqueue(task)
        backend1.close()
        print(f"  ✓ Enqueued task and closed backend")

        # Second backend instance
        backend2 = SQLiteBackend(database_path=db_path)
        retrieved = backend2.get_task(task.id)
        assert retrieved is not None
        assert retrieved.id == task.id
        assert retrieved.name == task.name
        assert retrieved.payload == task.payload
        assert retrieved.max_retries == task.max_retries
        print(f"  ✓ Task persisted across restart")

        # Verify status persists
        dequeued = backend2.dequeue()
        backend2.close()

        # Third backend instance
        backend3 = SQLiteBackend(database_path=db_path)
        retrieved = backend3.get_task(task.id)
        assert retrieved.status == TaskStatus.RUNNING
        print(f"  ✓ Task status persisted")

        backend3.close()
        print("  ✓ Persistence test passed!")
        return True

    except Exception as e:
        print(f"  ✗ Persistence test failed: {e}")
        traceback.print_exc()
        return False

    finally:
        try:
            os.unlink(db_path)
            for ext in ["-wal", "-shm"]:
                wal_path = db_path + ext
                if os.path.exists(wal_path):
                    os.unlink(wal_path)
        except Exception:
            pass


def test_list_tasks():
    """Test listing tasks."""
    print("\nTesting list_tasks...")

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        backend = SQLiteBackend(database_path=db_path)

        # Enqueue tasks
        for i in range(3):
            task = Task(name=f"task_{i}", priority=i+1)
            backend.enqueue(task)

        # List all tasks
        all_tasks = backend.list_tasks()
        assert len(all_tasks) == 3
        print(f"  ✓ Listed {len(all_tasks)} tasks")

        # List pending tasks
        pending = backend.list_tasks(TaskStatus.PENDING)
        assert len(pending) == 3
        print(f"  ✓ Listed {len(pending)} pending tasks")

        # Dequeue one and check again
        backend.dequeue()
        pending = backend.list_tasks(TaskStatus.PENDING)
        assert len(pending) == 2
        print(f"  ✓ After dequeue, {len(pending)} pending tasks")

        backend.close()
        print("  ✓ List tasks test passed!")
        return True

    except Exception as e:
        print(f"  ✗ List tasks test failed: {e}")
        traceback.print_exc()
        return False

    finally:
        try:
            os.unlink(db_path)
            for ext in ["-wal", "-shm"]:
                wal_path = db_path + ext
                if os.path.exists(wal_path):
                    os.unlink(wal_path)
        except Exception:
            pass


def test_clear():
    """Test clearing the queue."""
    print("\nTesting clear...")

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        backend = SQLiteBackend(database_path=db_path)

        # Enqueue tasks
        for i in range(5):
            task = Task(name=f"task_{i}")
            backend.enqueue(task)

        assert backend.size() == 5
        print(f"  ✓ Enqueued 5 tasks")

        # Clear queue
        backend.clear()
        assert backend.size() == 0
        assert backend.list_tasks() == []
        print(f"  ✓ Queue cleared")

        backend.close()
        print("  ✓ Clear test passed!")
        return True

    except Exception as e:
        print(f"  ✗ Clear test failed: {e}")
        traceback.print_exc()
        return False

    finally:
        try:
            os.unlink(db_path)
            for ext in ["-wal", "-shm"]:
                wal_path = db_path + ext
                if os.path.exists(wal_path):
                    os.unlink(wal_path)
        except Exception:
            pass


def main():
    """Run all tests."""
    print("=" * 70)
    print("SQLite Backend Simple Tests")
    print("=" * 70)

    tests = [
        test_basic_operations,
        test_multiple_tasks,
        test_retry_logic,
        test_persistence,
        test_list_tasks,
        test_clear,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"  ✗ {test.__name__} failed with exception: {e}")
            traceback.print_exc()
            results.append(False)

    print("\n" + "=" * 70)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 70)

    if all(results):
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {len(results) - sum(results)} test(s) failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())