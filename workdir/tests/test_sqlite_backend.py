"""
Tests for the SQLite persistent backend implementation.
"""

import os
import tempfile
import time
import threading
from uuid import UUID, uuid4

import pytest

from python_task_queue.backends.sqlite import SQLiteBackend
from python_task_queue.backends.base import QueueBackendError, TaskNotFoundError
from python_task_queue.models import Task, TaskStatus, TaskResult


@pytest.fixture
def db_path():
    """Provide a temporary database path for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # Clean up
    try:
        os.unlink(path)
        # Also remove WAL and SHM files
        for ext in ["-wal", "-shm"]:
            wal_path = path + ext
            if os.path.exists(wal_path):
                os.unlink(wal_path)
    except Exception:
        pass


@pytest.fixture
def backend(db_path):
    """Provide a SQLiteBackend instance for testing."""
    backend = SQLiteBackend(database_path=db_path, auto_create=True)
    yield backend
    backend.close()


@pytest.fixture
def sample_task():
    """Provide a sample task for testing."""
    return Task(
        name="test_task",
        payload={"key": "value", "number": 42},
        priority=5,
    )


class TestSQLiteBackendBasics:
    """Test basic functionality of SQLiteBackend."""

    def test_backend_instantiation(self, db_path):
        """Test that SQLiteBackend can be instantiated."""
        backend = SQLiteBackend(database_path=db_path)
        assert backend is not None
        assert backend.database_path == db_path
        backend.close()

    def test_backend_context_manager(self, db_path):
        """Test that SQLiteBackend works as a context manager."""
        with SQLiteBackend(database_path=db_path) as backend:
            assert backend is not None
        # Resources should be cleaned up

    def test_auto_create_tables(self, db_path):
        """Test that tables are auto-created on initialization."""
        backend = SQLiteBackend(database_path=db_path, auto_create=True)
        backend.close()

        # Verify tables exist
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
        )
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "tasks"
        conn.close()


class TestEnqueue:
    """Test task enqueuing functionality."""

    def test_enqueue_single_task(self, backend, sample_task):
        """Test enqueuing a single task."""
        backend.enqueue(sample_task)

        # Verify task was stored
        retrieved = backend.get_task(sample_task.id)
        assert retrieved is not None
        assert retrieved.id == sample_task.id
        assert retrieved.name == sample_task.name
        assert retrieved.status == TaskStatus.PENDING

    def test_enqueue_multiple_tasks(self, backend):
        """Test enqueuing multiple tasks."""
        tasks = [
            Task(name=f"task_{i}", payload={"index": i}, priority=i)
            for i in range(5)
        ]

        for task in tasks:
            backend.enqueue(task)

        # Verify all tasks were stored
        assert backend.size() == 5

        # Verify all tasks can be retrieved
        for task in tasks:
            retrieved = backend.get_task(task.id)
            assert retrieved.id == task.id

    def test_enqueue_with_duplicate_id(self, backend, sample_task):
        """Test that enqueuing a task with duplicate ID raises error."""
        backend.enqueue(sample_task)

        with pytest.raises(QueueBackendError, match="already exists"):
            backend.enqueue(sample_task)

    def test_enqueue_preserves_all_fields(self, backend):
        """Test that all task fields are preserved during enqueue."""
        task = Task(
            name="complex_task",
            payload={"data": [1, 2, 3], "nested": {"key": "value"}},
            priority=3,
            metadata={"custom": "metadata", "tags": ["test", "unit"]},
            max_retries=5,
        )

        backend.enqueue(task)
        retrieved = backend.get_task(task.id)

        assert retrieved.name == task.name
        assert retrieved.payload == task.payload
        assert retrieved.priority == task.priority
        assert retrieved.metadata == task.metadata
        assert retrieved.max_retries == task.max_retries


class TestDequeue:
    """Test task dequeuing functionality."""

    def test_dequeue_empty_queue(self, backend):
        """Test dequeuing from an empty queue."""
        task = backend.dequeue()
        assert task is None

    def test_dequeue_single_task(self, backend, sample_task):
        """Test dequeuing a single task."""
        backend.enqueue(sample_task)

        task = backend.dequeue()
        assert task is not None
        assert task.id == sample_task.id

    def test_dequeue_updates_status(self, backend, sample_task):
        """Test that dequeuing updates task status to RUNNING."""
        backend.enqueue(sample_task)

        task = backend.dequeue()
        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None

    def test_dequeue_priority_order(self, backend):
        """Test that tasks are dequeued in priority order."""
        tasks = [
            Task(name="low", priority=10),
            Task(name="high", priority=1),
            Task(name="medium", priority=5),
        ]

        for task in tasks:
            backend.enqueue(task)

        # Should dequeue in order: high (1), medium (5), low (10)
        first = backend.dequeue()
        assert first.name == "high"

        second = backend.dequeue()
        assert second.name == "medium"

        third = backend.dequeue()
        assert third.name == "low"

    def test_dequeue_fifo_for_same_priority(self, backend):
        """Test FIFO ordering for tasks with same priority."""
        tasks = [Task(name=f"task_{i}", priority=5) for i in range(5)]

        for task in tasks:
            backend.enqueue(task)
            # Small delay to ensure different enqueued_at times
            time.sleep(0.01)

        # Should dequeue in FIFO order
        for i, task in enumerate(tasks):
            next_task = backend.dequeue()
            assert next_task.name == f"task_{i}"

    def test_dequeue_removes_from_pending(self, backend, sample_task):
        """Test that dequeued tasks are not in pending status."""
        backend.enqueue(sample_task)
        backend.dequeue()

        # Queue size should be 0 (no pending tasks)
        assert backend.size() == 0

        # Task should be in RUNNING status
        retrieved = backend.get_task(sample_task.id)
        assert retrieved.status == TaskStatus.RUNNING


class TestPeek:
    """Test task peek functionality."""

    def test_peek_empty_queue(self, backend):
        """Test peeking at an empty queue."""
        task = backend.peek()
        assert task is None

    def test_peek_does_not_dequeue(self, backend, sample_task):
        """Test that peek does not remove the task from queue."""
        backend.enqueue(sample_task)

        # Peek should return the task
        peeked = backend.peek()
        assert peeked is not None
        assert peeked.id == sample_task.id
        assert peeked.status == TaskStatus.PENDING

        # Queue size should still be 1
        assert backend.size() == 1

        # Dequeue should still return the same task
        dequeued = backend.dequeue()
        assert dequeued.id == sample_task.id

    def test_peek_returns_same_as_dequeue(self, backend):
        """Test that peek returns the same task that would be dequeued."""
        tasks = [
            Task(name="high", priority=1),
            Task(name="low", priority=10),
        ]

        for task in tasks:
            backend.enqueue(task)

        # Peek should return the high priority task
        peeked = backend.peek()
        assert peeked.name == "high"

        # Dequeue should also return the high priority task
        dequeued = backend.dequeue()
        assert dequeued.name == "high"
        assert dequeued.id == peeked.id


class TestSize:
    """Test queue size functionality."""

    def test_size_empty_queue(self, backend):
        """Test size of empty queue."""
        assert backend.size() == 0

    def test_size_after_enqueue(self, backend):
        """Test size after enqueuing tasks."""
        tasks = [Task(name=f"task_{i}") for i in range(5)]

        for i, task in enumerate(tasks):
            backend.enqueue(task)
            assert backend.size() == i + 1

    def test_size_after_dequeue(self, backend):
        """Test size after dequeuing tasks."""
        tasks = [Task(name=f"task_{i}") for i in range(5)]

        for task in tasks:
            backend.enqueue(task)

        assert backend.size() == 5

        for i in range(5):
            backend.dequeue()
            assert backend.size() == 5 - i - 1

    def test_size_only_counts_pending(self, backend):
        """Test that size only counts pending tasks."""
        task = Task(name="test_task")
        backend.enqueue(task)

        assert backend.size() == 1

        # Dequeue the task (status becomes RUNNING)
        backend.dequeue()
        assert backend.size() == 0  # No pending tasks

        # Acknowledge the task (status becomes COMPLETED)
        backend.acknowledge(task.id)
        assert backend.size() == 0


class TestAcknowledge:
    """Test task acknowledgment functionality."""

    def test_acknowledge_task(self, backend, sample_task):
        """Test acknowledging a task."""
        backend.enqueue(sample_task)
        backend.dequeue()

        backend.acknowledge(sample_task.id)

        # Verify task is marked as completed
        retrieved = backend.get_task(sample_task.id)
        assert retrieved.status == TaskStatus.COMPLETED
        assert retrieved.completed_at is not None

    def test_acknowledge_nonexistent_task(self, backend):
        """Test acknowledging a non-existent task."""
        with pytest.raises(TaskNotFoundError):
            backend.acknowledge(uuid4())


class TestFail:
    """Test task failure functionality."""

    def test_fail_task_no_retries(self, backend):
        """Test failing a task with no retries left."""
        task = Task(name="test_task", max_retries=0)
        backend.enqueue(task)
        backend.dequeue()

        backend.fail(task.id, "Task failed")

        # Verify task is marked as failed
        retrieved = backend.get_task(task.id)
        assert retrieved.status == TaskStatus.FAILED
        assert retrieved.completed_at is not None

    def test_fail_task_with_retries(self, backend):
        """Test failing a task with retries remaining."""
        task = Task(name="test_task", max_retries=3)
        backend.enqueue(task)
        backend.dequeue()

        backend.fail(task.id, "Task failed")

        # Verify task is marked as retrying
        retrieved = backend.get_task(task.id)
        assert retrieved.status == TaskStatus.RETRYING
        assert retrieved.retry_count == 1

    def test_fail_task_max_retries_exceeded(self, backend):
        """Test failing a task after max retries."""
        task = Task(name="test_task", max_retries=2)
        backend.enqueue(task)
        backend.dequeue()

        # Fail once
        backend.fail(task.id, "First failure")
        assert backend.get_task(task.id).status == TaskStatus.RETRYING

        # Fail again
        task.running()
        backend.fail(task.id, "Second failure")
        assert backend.get_task(task.id).status == TaskStatus.RETRYING

        # Fail third time (should mark as FAILED)
        task.running()
        backend.fail(task.id, "Third failure")
        assert backend.get_task(task.id).status == TaskStatus.FAILED

    def test_fail_nonexistent_task(self, backend):
        """Test failing a non-existent task."""
        with pytest.raises(TaskNotFoundError):
            backend.fail(uuid4(), "Task failed")


class TestGetTask:
    """Test task retrieval functionality."""

    def test_get_task_exists(self, backend, sample_task):
        """Test getting an existing task."""
        backend.enqueue(sample_task)

        task = backend.get_task(sample_task.id)
        assert task is not None
        assert task.id == sample_task.id

    def test_get_task_not_exists(self, backend):
        """Test getting a non-existent task."""
        task = backend.get_task(uuid4())
        assert task is None

    def test_get_task_preserves_status(self, backend):
        """Test that get_task preserves task status."""
        task = Task(name="test_task")
        backend.enqueue(task)
        backend.dequeue()
        backend.acknowledge(task.id)

        retrieved = backend.get_task(task.id)
        assert retrieved.status == TaskStatus.COMPLETED


class TestListTasks:
    """Test task listing functionality."""

    def test_list_tasks_empty(self, backend):
        """Test listing tasks when queue is empty."""
        tasks = backend.list_tasks()
        assert tasks == []

    def test_list_tasks_all(self, backend):
        """Test listing all tasks."""
        tasks = [Task(name=f"task_{i}") for i in range(5)]

        for task in tasks:
            backend.enqueue(task)

        all_tasks = backend.list_tasks()
        assert len(all_tasks) == 5

    def test_list_tasks_filter_by_status(self, backend):
        """Test listing tasks filtered by status."""
        task1 = Task(name="task1", priority=1)
        task2 = Task(name="task2", priority=2)
        task3 = Task(name="task3", priority=3)

        backend.enqueue(task1)
        backend.enqueue(task2)
        backend.enqueue(task3)

        # Dequeue and complete one task
        backend.dequeue()
        backend.acknowledge(task1.id)

        # List pending tasks (should be 2)
        pending = backend.list_tasks(TaskStatus.PENDING)
        assert len(pending) == 2

        # List completed tasks (should be 1)
        completed = backend.list_tasks(TaskStatus.COMPLETED)
        assert len(completed) == 1

    def test_list_tasks_order(self, backend):
        """Test that list_tasks returns tasks in correct order."""
        tasks = [
            Task(name="low", priority=10),
            Task(name="high", priority=1),
        ]

        for task in tasks:
            backend.enqueue(task)

        listed = backend.list_tasks()
        # Should be ordered by priority
        assert listed[0].priority == 1
        assert listed[1].priority == 10


class TestClear:
    """Test queue clearing functionality."""

    def test_clear_empty_queue(self, backend):
        """Test clearing an empty queue."""
        backend.clear()
        assert backend.size() == 0

    def test_clear_with_tasks(self, backend):
        """Test clearing a queue with tasks."""
        tasks = [Task(name=f"task_{i}") for i in range(5)]
        for task in tasks:
            backend.enqueue(task)

        backend.clear()
        assert backend.size() == 0
        assert backend.list_tasks() == []


class TestPersistence:
    """Test data persistence across backend restarts."""

    def test_persistence_across_restart(self, db_path):
        """Test that tasks persist across backend restarts."""
        task = Task(name="persistent_task", payload={"data": "value"})

        # Enqueue task with first backend instance
        with SQLiteBackend(database_path=db_path) as backend1:
            backend1.enqueue(task)

        # Create new backend instance and verify task exists
        with SQLiteBackend(database_path=db_path) as backend2:
            retrieved = backend2.get_task(task.id)
            assert retrieved is not None
            assert retrieved.id == task.id
            assert retrieved.name == task.name
            assert retrieved.payload == task.payload

    def test_status_persistence_across_restart(self, db_path):
        """Test that task status persists across restarts."""
        task = Task(name="test_task")

        with SQLiteBackend(database_path=db_path) as backend1:
            backend1.enqueue(task)
            backend1.dequeue()

        # Create new backend instance
        with SQLiteBackend(database_path=db_path) as backend2:
            retrieved = backend2.get_task(task.id)
            assert retrieved.status == TaskStatus.RUNNING

    def test_completed_task_persistence(self, db_path):
        """Test that completed tasks persist across restarts."""
        task = Task(name="test_task")

        with SQLiteBackend(database_path=db_path) as backend1:
            backend1.enqueue(task)
            backend1.dequeue()
            backend1.acknowledge(task.id)

        # Create new backend instance
        with SQLiteBackend(database_path=db_path) as backend2:
            retrieved = backend2.get_task(task.id)
            assert retrieved.status == TaskStatus.COMPLETED
            assert retrieved.completed_at is not None

            # Should not be in pending queue
            assert backend2.size() == 0


class TestConcurrency:
    """Test concurrent access to the backend."""

    def test_concurrent_enqueue(self, backend):
        """Test concurrent enqueuing from multiple threads."""
        num_tasks = 50
        errors = []

        def enqueue_task(i):
            try:
                task = Task(name=f"task_{i}")
                backend.enqueue(task)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(num_tasks):
            t = threading.Thread(target=enqueue_task, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # No errors should have occurred
        assert len(errors) == 0

        # All tasks should be enqueued
        assert backend.size() == num_tasks

    def test_concurrent_dequeue(self, backend):
        """Test concurrent dequeuing from multiple threads."""
        # Enqueue some tasks
        num_tasks = 20
        for i in range(num_tasks):
            task = Task(name=f"task_{i}")
            backend.enqueue(task)

        dequeued_tasks = []
        errors = []

        def dequeue_task():
            try:
                task = backend.dequeue()
                if task:
                    dequeued_tasks.append(task.id)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(5):
            t = threading.Thread(target=dequeue_task)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # No errors should have occurred
        assert len(errors) == 0

        # All tasks should have been dequeued (unique IDs)
        assert len(dequeued_tasks) == num_tasks
        assert len(set(dequeued_tasks)) == num_tasks

    def test_concurrent_mixed_operations(self, backend):
        """Test concurrent enqueuing and dequeuing."""
        num_operations = 30
        errors = []

        def producer(i):
            try:
                task = Task(name=f"task_{i}")
                backend.enqueue(task)
            except Exception as e:
                errors.append(("producer", i, e))

        def consumer():
            try:
                task = backend.dequeue()
                if task:
                    # Simulate processing
                    time.sleep(0.001)
                    backend.acknowledge(task.id)
            except Exception as e:
                errors.append(("consumer", None, e))

        threads = []
        for i in range(num_operations):
            t = threading.Thread(target=producer, args=(i,))
            threads.append(t)

        for _ in range(num_operations):
            t = threading.Thread(target=consumer)
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # No critical errors should have occurred
        critical_errors = [e for e in errors if "no such table" not in str(e[2]).lower()]
        assert len(critical_errors) == 0


class TestConnectionPool:
    """Test connection pool functionality."""

    def test_pool_size_limit(self, db_path):
        """Test that connection pool respects size limit."""
        backend = SQLiteBackend(database_path=db_path, pool_size=2)
        assert backend.pool.max_connections == 2
        backend.close()

    def test_connection_reuse(self, backend):
        """Test that connections are reused from pool."""
        # Perform multiple operations
        for i in range(10):
            task = Task(name=f"task_{i}")
            backend.enqueue(task)
            backend.get_task(task.id)

        # Pool should have recycled connections
        assert len(backend.pool._pool) > 0


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_task_with_none_payload(self, backend):
        """Test enqueuing a task with None payload."""
        task = Task(name="test_task", payload=None)
        backend.enqueue(task)

        retrieved = backend.get_task(task.id)
        assert retrieved.payload is None

    def test_task_with_empty_metadata(self, backend):
        """Test enqueuing a task with empty metadata."""
        task = Task(name="test_task", metadata={})
        backend.enqueue(task)

        retrieved = backend.get_task(task.id)
        assert retrieved.metadata == {}

    def test_task_with_complex_payload(self, backend):
        """Test enqueuing a task with complex nested payload."""
        payload = {
            "numbers": [1, 2, 3],
            "nested": {
                "deeply": {
                    "nested": {"value": "test"}
                }
            },
            "mixed": ["list", {"dict": "value"}],
        }
        task = Task(name="complex_task", payload=payload)
        backend.enqueue(task)

        retrieved = backend.get_task(task.id)
        assert retrieved.payload == payload

    def test_path_with_directory(self, db_path):
        """Test creating database in non-existent directory."""
        # Create a path in a subdirectory
        subdir = os.path.join(os.path.dirname(db_path), "test_subdir")
        custom_path = os.path.join(subdir, "custom.db")

        backend = SQLiteBackend(database_path=custom_path, auto_create=True)
        assert os.path.exists(custom_path)
        backend.close()

        # Clean up
        try:
            os.unlink(custom_path)
            for ext in ["-wal", "-shm"]:
                wal_path = custom_path + ext
                if os.path.exists(wal_path):
                    os.unlink(wal_path)
            os.rmdir(subdir)
        except Exception:
            pass

    def test_dequeue_pending_only(self, backend):
        """Test that dequeue only returns pending tasks."""
        task1 = Task(name="completed", priority=1)
        task2 = Task(name="pending", priority=2)

        backend.enqueue(task1)
        backend.enqueue(task2)

        # Complete task1
        backend.dequeue()
        backend.acknowledge(task1.id)

        # Dequeue should return task2 (the only pending task)
        task = backend.dequeue()
        assert task.id == task2.id
        assert task.name == "pending"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])