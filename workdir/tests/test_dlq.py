"""
Comprehensive tests for the Dead Letter Queue system.

This test suite covers:
- DeadLetterTask creation and serialization
- DLQBackend interface and MemoryDLQBackend implementation
- DeadLetterQueue operations (add, inspect, replay, purge)
- Filtering and statistics
- Edge cases and error handling
"""

import time
from datetime import datetime
from uuid import uuid4

import pytest

from python_task_queue.dlq import (
    DeadLetterTask,
    DeadLetterQueue,
    DLQBackend,
    MemoryDLQBackend,
    create_dlq,
)
from python_task_queue.models import Task, TaskResult, TaskStatus


class TestDeadLetterTask:
    """Test cases for DeadLetterTask dataclass."""

    def test_create_dead_letter_task(self):
        """Test creating a dead letter task with default values."""
        task = Task(name="test_task", payload={"data": 123})
        dead_letter = DeadLetterTask(
            task=task,
            original_queue="main",
            reason="max_retries_exceeded",
            error_message="Task failed",
            error_type="ValueError",
        )

        assert dead_letter.task == task
        assert dead_letter.original_queue == "main"
        assert dead_letter.reason == "max_retries_exceeded"
        assert dead_letter.error_message == "Task failed"
        assert dead_letter.error_type == "ValueError"
        assert dead_letter.retry_count == 0
        assert isinstance(dead_letter.id, type(uuid4()))

    def test_dead_letter_task_serialization(self):
        """Test serialization and deserialization of dead letter tasks."""
        task = Task(name="test_task", payload={"data": 123})
        dead_letter = DeadLetterTask(
            task=task,
            original_queue="main",
            reason="max_retries_exceeded",
            error_message="Task failed",
            error_type="ValueError",
        )

        # Serialize
        data = dead_letter.to_dict()
        assert isinstance(data["id"], str)
        assert isinstance(data["task"], dict)
        assert isinstance(data["failed_at"], str)

        # Deserialize
        restored = DeadLetterTask.from_dict(data)
        assert str(restored.id) == data["id"]
        assert restored.task.name == task.name
        assert restored.original_queue == dead_letter.original_queue
        assert restored.reason == dead_letter.reason

    def test_dead_letter_task_with_failed_task(self):
        """Test creating dead letter task from a failed task."""
        task = Task(name="test_task", payload={"data": 123})
        task.fail(
            error="Division by zero",
            error_type="ZeroDivisionError",
        )

        dead_letter = DeadLetterTask(task=task, reason="max_retries_exceeded")

        assert dead_letter.task.status == TaskStatus.FAILED
        assert task.retry_count == 0  # Task fails without retrying

    def test_dead_letter_task_with_retry_count(self):
        """Test dead letter task preserves retry count."""
        task = Task(name="test_task", payload={"data": 123})
        task.retry_count = 3

        dead_letter = DeadLetterTask(
            task=task,
            reason="max_retries_exceeded",
            retry_count=3,
        )

        assert dead_letter.retry_count == 3


class TestMemoryDLQBackend:
    """Test cases for MemoryDLQBackend implementation."""

    def test_backend_initialization(self):
        """Test that backend initializes correctly."""
        backend = MemoryDLQBackend()
        assert backend.count() == 0

    def test_add_and_get(self):
        """Test adding and retrieving a dead letter task."""
        backend = MemoryDLQBackend()
        task = Task(name="test_task", payload={"data": 123})
        task.fail(error="Failed")

        dead_letter = DeadLetterTask(task=task, reason="max_retries_exceeded")
        backend.add(dead_letter)

        retrieved = backend.get(dead_letter.id)
        assert retrieved is not None
        assert retrieved.id == dead_letter.id
        assert retrieved.task.name == task.name

    def test_get_nonexistent(self):
        """Test getting a non-existent task returns None."""
        backend = MemoryDLQBackend()
        retrieved = backend.get(uuid4())
        assert retrieved is None

    def test_list_all_empty(self):
        """Test listing tasks when DLQ is empty."""
        backend = MemoryDLQBackend()
        tasks = backend.list_all()
        assert tasks == []

    def test_list_all_with_tasks(self):
        """Test listing all tasks returns them sorted by most recent."""
        backend = MemoryDLQBackend()

        # Add tasks with different timestamps
        tasks_added = []
        for i in range(3):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dead_letter = DeadLetterTask(
                task=task,
                reason="max_retries_exceeded",
            )
            backend.add(dead_letter)
            tasks_added.append(dead_letter)
            time.sleep(0.01)  # Small delay for timestamp difference

        tasks = backend.list_all()
        assert len(tasks) == 3
        # Most recent first
        assert tasks[0].id == tasks_added[2].id
        assert tasks[1].id == tasks_added[1].id
        assert tasks[2].id == tasks_added[0].id

    def test_list_all_with_limit(self):
        """Test listing with a limit."""
        backend = MemoryDLQBackend()

        for i in range(5):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dead_letter = DeadLetterTask(task=task, reason="max_retries_exceeded")
            backend.add(dead_letter)
            time.sleep(0.01)

        tasks = backend.list_all(limit=3)
        assert len(tasks) == 3

    def test_remove(self):
        """Test removing a task from DLQ."""
        backend = MemoryDLQBackend()
        task = Task(name="test_task")
        task.fail(error="Failed")

        dead_letter = DeadLetterTask(task=task, reason="max_retries_exceeded")
        backend.add(dead_letter)

        assert backend.count() == 1
        assert backend.remove(dead_letter.id) is True
        assert backend.count() == 0
        assert backend.remove(dead_letter.id) is False

    def test_purge(self):
        """Test purging all tasks from DLQ."""
        backend = MemoryDLQBackend()

        for i in range(5):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dead_letter = DeadLetterTask(task=task, reason="max_retries_exceeded")
            backend.add(dead_letter)

        assert backend.count() == 5
        count = backend.purge()
        assert count == 5
        assert backend.count() == 0

    def test_count(self):
        """Test counting tasks in DLQ."""
        backend = MemoryDLQBackend()
        assert backend.count() == 0

        for i in range(3):
            task = Task(name=f"test_task_{i}")
            task.fail(error="Failed")
            dead_letter = DeadLetterTask(task=task, reason="max_retries_exceeded")
            backend.add(dead_letter)

        assert backend.count() == 3

    def test_filter_by_reason(self):
        """Test filtering tasks by reason."""
        backend = MemoryDLQBackend()

        # Add tasks with different reasons
        for i in range(3):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            reason = "max_retries_exceeded" if i % 2 == 0 else "timeout"
            dead_letter = DeadLetterTask(task=task, reason=reason)
            backend.add(dead_letter)

        max_retries_tasks = backend.filter_by_reason("max_retries_exceeded")
        timeout_tasks = backend.filter_by_reason("timeout")

        assert len(max_retries_tasks) == 2
        assert len(timeout_tasks) == 1

    def test_filter_by_queue(self):
        """Test filtering tasks by original queue."""
        backend = MemoryDLQBackend()

        # Add tasks from different queues
        for i in range(3):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            queue = "main" if i % 2 == 0 else "priority"
            dead_letter = DeadLetterTask(task=task, original_queue=queue)
            backend.add(dead_letter)

        main_tasks = backend.filter_by_queue("main")
        priority_tasks = backend.filter_by_queue("priority")

        assert len(main_tasks) == 2
        assert len(priority_tasks) == 1

    def test_filter_by_queue_sorted(self):
        """Test that filtered tasks are sorted by most recent."""
        backend = MemoryDLQBackend()

        for i in range(3):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dead_letter = DeadLetterTask(task=task, original_queue="main")
            backend.add(dead_letter)
            time.sleep(0.01)

        tasks = backend.filter_by_queue("main")
        assert len(tasks) == 3
        # Check they're sorted by failed_at descending
        assert tasks[0].failed_at >= tasks[1].failed_at >= tasks[2].failed_at


class TestDeadLetterQueue:
    """Test cases for DeadLetterQueue main interface."""

    def test_initialization_with_memory_backend(self):
        """Test DLQ initialization with default memory backend."""
        dlq = DeadLetterQueue()
        assert isinstance(dlq.backend, MemoryDLQBackend)
        assert dlq.count() == 0

    def test_initialization_with_custom_backend(self):
        """Test DLQ initialization with custom backend."""
        backend = MemoryDLQBackend()
        dlq = DeadLetterQueue(backend=backend)
        assert dlq.backend is backend

    def test_add_failed_task(self):
        """Test adding a failed task to DLQ."""
        dlq = DeadLetterQueue()
        task = Task(name="test_task", payload={"data": 123})
        task.fail(error="Max retries exceeded")

        dead_letter = dlq.add_failed_task(
            task=task,
            original_queue="main",
            reason="max_retries_exceeded",
            error_message="Task failed after 3 retries",
            error_type="ValueError",
        )

        assert dead_letter.task.id == task.id
        assert dead_letter.original_queue == "main"
        assert dead_letter.reason == "max_retries_exceeded"
        assert dlq.count() == 1

    def test_add_failed_task_non_failed_status(self):
        """Test that adding non-FAILED task raises ValueError."""
        dlq = DeadLetterQueue()
        task = Task(name="test_task", status=TaskStatus.PENDING)

        with pytest.raises(ValueError, match="Cannot add task with status PENDING"):
            dlq.add_failed_task(task=task, reason="test")

    def test_add_failed_task_with_task_result(self):
        """Test that error info is extracted from task result."""
        dlq = DeadLetterQueue()
        task = Task(name="test_task")
        task.fail(
            error="Division by zero",
            error_type="ZeroDivisionError",
        )

        dead_letter = dlq.add_failed_task(task=task)

        assert dead_letter.error_message == "Division by zero"
        assert dead_letter.error_type == "ZeroDivisionError"

    def test_inspect_all(self):
        """Test inspecting all tasks."""
        dlq = DeadLetterQueue()

        for i in range(3):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dlq.add_failed_task(task=task)
            time.sleep(0.01)

        tasks = dlq.inspect()
        assert len(tasks) == 3

    def test_inspect_with_limit(self):
        """Test inspecting with a limit."""
        dlq = DeadLetterQueue()

        for i in range(5):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dlq.add_failed_task(task=task)

        tasks = dlq.inspect(limit=2)
        assert len(tasks) == 2

    def test_inspect_by_reason(self):
        """Test inspecting filtered by reason."""
        dlq = DeadLetterQueue()

        for i in range(3):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            reason = "max_retries_exceeded" if i % 2 == 0 else "timeout"
            dlq.add_failed_task(task=task, reason=reason)

        tasks = dlq.inspect(reason="max_retries_exceeded")
        assert len(tasks) == 2
        assert all(t.reason == "max_retries_exceeded" for t in tasks)

    def test_inspect_by_queue(self):
        """Test inspecting filtered by queue."""
        dlq = DeadLetterQueue()

        for i in range(3):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            queue = "main" if i % 2 == 0 else "priority"
            dlq.add_failed_task(task=task, original_queue=queue)

        main_tasks = dlq.inspect(queue_name="main")
        assert len(main_tasks) == 2
        assert all(t.original_queue == "main" for t in main_tasks)

    def test_inspect_combined_filters(self):
        """Test inspecting with both reason and queue filters."""
        dlq = DeadLetterQueue()

        # Add tasks with different combinations
        for i, (reason, queue) in enumerate([
            ("max_retries_exceeded", "main"),
            ("timeout", "main"),
            ("max_retries_exceeded", "priority"),
            ("timeout", "priority"),
        ]):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dlq.add_failed_task(task=task, reason=reason, original_queue=queue)

        tasks = dlq.inspect(reason="timeout", queue_name="main")
        assert len(tasks) == 1
        assert tasks[0].reason == "timeout"
        assert tasks[0].original_queue == "main"

    def test_get_task(self):
        """Test getting a specific task by ID."""
        dlq = DeadLetterQueue()
        task = Task(name="test_task")
        task.fail(error="Failed")

        dead_letter = dlq.add_failed_task(task=task)
        retrieved = dlq.get_task(dead_letter.id)

        assert retrieved is not None
        assert retrieved.id == dead_letter.id

    def test_get_task_nonexistent(self):
        """Test getting a non-existent task returns None."""
        dlq = DeadLetterQueue()
        retrieved = dlq.get_task(uuid4())
        assert retrieved is None

    def test_replay(self):
        """Test replaying a dead letter task."""
        dlq = DeadLetterQueue()

        original_task = Task(name="test_task", payload={"data": 123})
        original_task.fail(error="Failed")

        dead_letter = dlq.add_failed_task(
            task=original_task,
            original_queue="main",
            retry_count=3,
        )

        replayed_task = dlq.replay(replay_id=dead_letter.id)

        # Check that original task is removed from DLQ
        assert dlq.get_task(dead_letter.id) is None
        assert dlq.count() == 0

        # Check replayed task properties
        assert replayed_task.id != original_task.id
        assert replayed_task.status == TaskStatus.PENDING
        assert replayed_task.retry_count == 3  # Not reset by default
        assert replayed_task.name == original_task.name
        assert replayed_task.payload == original_task.payload
        assert replayed_task.started_at is None
        assert replayed_task.completed_at is None
        assert replayed_task.result is None
        assert replayed_task.error is None

    def test_replay_with_reset_retries(self):
        """Test replaying with reset_retries=True."""
        dlq = DeadLetterQueue()

        original_task = Task(name="test_task")
        original_task.retry_count = 3
        original_task.fail(error="Failed")

        dead_letter = dlq.add_failed_task(task=original_task)

        replayed_task = dlq.replay(
            replay_id=dead_letter.id,
            reset_retries=True,
        )

        assert replayed_task.retry_count == 0

    def test_replay_with_new_max_retries(self):
        """Test replaying with new max_retries."""
        dlq = DeadLetterQueue()

        original_task = Task(name="test_task", max_retries=3)
        original_task.fail(error="Failed")

        dead_letter = dlq.add_failed_task(task=original_task)

        replayed_task = dlq.replay(
            replay_id=dead_letter.id,
            new_max_retries=10,
        )

        assert replayed_task.max_retries == 10

    def test_replay_auto_increase_max_retries(self):
        """Test that max_retries is auto-increased when exhausted."""
        dlq = DeadLetterQueue()

        original_task = Task(name="test_task", max_retries=3)
        original_task.retry_count = 3
        original_task.fail(error="Failed")

        dead_letter = dlq.add_failed_task(task=original_task)

        # Replay without specifying new max_retries
        replayed_task = dlq.replay(replay_id=dead_letter.id)

        # Should auto-increase by 3
        assert replayed_task.max_retries == 6

    def test_replay_with_new_priority(self):
        """Test replaying with new priority."""
        dlq = DeadLetterQueue()

        original_task = Task(name="test_task", priority=5)
        original_task.fail(error="Failed")

        dead_letter = dlq.add_failed_task(task=original_task)

        replayed_task = dlq.replay(
            replay_id=dead_letter.id,
            new_priority=1,
        )

        assert replayed_task.priority == 1

    def test_replay_metadata_preservation(self):
        """Test that replay metadata is added to task."""
        dlq = DeadLetterQueue()

        original_task = Task(name="test_task")
        original_task.metadata = {"original": "value"}
        original_task.fail(error="Failed")

        dead_letter = dlq.add_failed_task(
            task=original_task,
            reason="max_retries_exceeded",
        )

        replayed_task = dlq.replay(replay_id=dead_letter.id)

        # Check original metadata preserved
        assert replayed_task.metadata["original"] == "value"

        # Check replay metadata added
        assert "dlq_replayed_at" in replayed_task.metadata
        assert "dlq_original_failed_at" in replayed_task.metadata
        assert "dlq_reason" in replayed_task.metadata
        assert "dlq_original_retry_count" in replayed_task.metadata
        assert "dlq_original_max_retries" in replayed_task.metadata
        assert replayed_task.metadata["dlq_reason"] == "max_retries_exceeded"

    def test_replay_nonexistent(self):
        """Test replaying a non-existent task raises ValueError."""
        dlq = DeadLetterQueue()

        with pytest.raises(ValueError, match="not found"):
            dlq.replay(replay_id=uuid4())

    def test_replay_all(self):
        """Test replaying all tasks."""
        dlq = DeadLetterQueue()

        for i in range(3):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dlq.add_failed_task(task=task)

        replayed_tasks = dlq.replay_all(reset_retries=True)

        assert len(replayed_tasks) == 3
        assert dlq.count() == 0
        assert all(t.status == TaskStatus.PENDING for t in replayed_tasks)
        assert all(t.retry_count == 0 for t in replayed_tasks)

    def test_replay_filtered(self):
        """Test replaying filtered tasks."""
        dlq = DeadLetterQueue()

        for i, reason in enumerate(["max_retries_exceeded", "timeout"] * 2):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dlq.add_failed_task(task=task, reason=reason)

        # Replay only timeout tasks
        replayed_tasks = dlq.replay_filtered(reason="timeout")

        assert len(replayed_tasks) == 2
        assert dlq.count() == 2  # Two max_retries_exceeded tasks remain

    def test_purge_single(self):
        """Test purging a single task."""
        dlq = DeadLetterQueue()

        task = Task(name="test_task")
        task.fail(error="Failed")
        dead_letter = dlq.add_failed_task(task=task)

        assert dlq.count() == 1
        result = dlq.purge(dead_letter.id)
        assert result is True
        assert dlq.count() == 0

    def test_purge_single_nonexistent(self):
        """Test purging a non-existent task returns False."""
        dlq = DeadLetterQueue()
        result = dlq.purge(uuid4())
        assert result is False

    def test_purge_all(self):
        """Test purging all tasks."""
        dlq = DeadLetterQueue()

        for i in range(5):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dlq.add_failed_task(task=task)

        count = dlq.purge_all()
        assert count == 5
        assert dlq.count() == 0

    def test_purge_filtered(self):
        """Test purging filtered tasks."""
        dlq = DeadLetterQueue()

        for i, reason in enumerate(["max_retries_exceeded", "timeout"] * 2):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dlq.add_failed_task(task=task, reason=reason)

        count = dlq.purge_filtered(reason="timeout")
        assert count == 2
        assert dlq.count() == 2

    def test_count(self):
        """Test counting tasks."""
        dlq = DeadLetterQueue()
        assert dlq.count() == 0

        for i in range(3):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dlq.add_failed_task(task=task)

        assert dlq.count() == 3

    def test_count_by_reason(self):
        """Test counting tasks by reason."""
        dlq = DeadLetterQueue()

        for i, reason in enumerate(["max_retries_exceeded"] * 3 + ["timeout"] * 2):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dlq.add_failed_task(task=task, reason=reason)

        assert dlq.count_by_reason("max_retries_exceeded") == 3
        assert dlq.count_by_reason("timeout") == 2
        assert dlq.count_by_reason("nonexistent") == 0

    def test_count_by_queue(self):
        """Test counting tasks by queue."""
        dlq = DeadLetterQueue()

        for i, queue in enumerate(["main"] * 3 + ["priority"] * 2):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}")
            dlq.add_failed_task(task=task, original_queue=queue)

        assert dlq.count_by_queue("main") == 3
        assert dlq.count_by_queue("priority") == 2

    def test_get_statistics(self):
        """Test getting DLQ statistics."""
        dlq = DeadLetterQueue()

        # Add varied tasks
        for i, (reason, queue, error_type) in enumerate([
            ("max_retries_exceeded", "main", "ValueError"),
            ("timeout", "main", "TimeoutError"),
            ("max_retries_exceeded", "priority", "ValueError"),
            ("invalid", "priority", "SyntaxError"),
        ]):
            task = Task(name=f"test_task_{i}")
            task.fail(error=f"Failed {i}", error_type=error_type)
            dlq.add_failed_task(task=task, reason=reason, original_queue=queue)

        stats = dlq.get_statistics()

        assert stats["total_count"] == 4
        assert stats["queues"]["main"] == 2
        assert stats["queues"]["priority"] == 2
        assert stats["reasons"]["max_retries_exceeded"] == 2
        assert stats["reasons"]["timeout"] == 1
        assert stats["reasons"]["invalid"] == 1
        assert stats["errors"]["ValueError"] == 2
        assert stats["errors"]["TimeoutError"] == 1
        assert stats["errors"]["SyntaxError"] == 1

    def test_get_statistics_empty(self):
        """Test getting statistics on empty DLQ."""
        dlq = DeadLetterQueue()
        stats = dlq.get_statistics()

        assert stats["total_count"] == 0
        assert stats["queues"] == {}
        assert stats["reasons"] == {}
        assert stats["errors"] == {}

    def test_repr(self):
        """Test string representation."""
        dlq = DeadLetterQueue()
        assert "DeadLetterQueue" in repr(dlq)
        assert str(dlq.count()) in repr(dlq)


class TestCreateDLQ:
    """Test cases for create_dlq convenience function."""

    def test_create_dlq_memory(self):
        """Test creating DLQ with memory backend."""
        dlq = create_dlq(backend_type="memory")
        assert isinstance(dlq, DeadLetterQueue)
        assert isinstance(dlq.backend, MemoryDLQBackend)

    def test_create_dlq_unsupported_backend(self):
        """Test that unsupported backend raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported DLQ backend"):
            create_dlq(backend_type="unsupported")


class TestDLQThreadSafety:
    """Test thread-safety of DLQ operations."""

    import threading

    def test_concurrent_add(self):
        """Test adding tasks concurrently."""
        dlq = DeadLetterQueue()
        num_threads = 10
        tasks_per_thread = 10

        def add_tasks():
            for i in range(tasks_per_thread):
                task = Task(name=f"test_task_{i}")
                task.fail(error="Failed")
                dlq.add_failed_task(task=task)

        threads = [
            self.threading.Thread(target=add_tasks)
            for _ in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have all tasks
        assert dlq.count() == num_threads * tasks_per_thread

    def test_concurrent_purge_and_count(self):
        """Test concurrent purge and count operations."""
        dlq = DeadLetterQueue()

        # Add some tasks
        for i in range(50):
            task = Task(name=f"test_task_{i}")
            task.fail(error="Failed")
            dlq.add_failed_task(task=task)

        results = {"counts": [], "purges": []}

        def count_tasks():
            for _ in range(100):
                results["counts"].append(dlq.count())

        def purge_tasks():
            for _ in range(10):
                count = dlq.purge_all()
                results["purges"].append(count)

        thread_count = self.threading.Thread(target=count_tasks)
        thread_purge = self.threading.Thread(target=purge_tasks)

        thread_count.start()
        thread_purge.start()
        thread_count.join()
        thread_purge.join()

        # Verify operations completed without errors
        assert len(results["counts"]) == 100
        assert sum(results["purges"]) <= 50  # Total purged can't exceed total added


class TestDLQEdgeCases:
    """Test edge cases and error handling."""

    def test_add_task_with_large_payload(self):
        """Test adding task with large payload."""
        dlq = DeadLetterQueue()
        large_payload = {"data": "x" * 10000}

        task = Task(name="large_task", payload=large_payload)
        task.fail(error="Failed")

        dead_letter = dlq.add_failed_task(task=task)
        assert dead_letter.task.payload == large_payload

    def test_add_task_with_special_characters(self):
        """Test adding task with special characters in data."""
        dlq = DeadLetterQueue()

        task = Task(name="special_task", payload={"data": "Hello\nWorld\t!@#$%"})
        task.fail(error="Failed")

        dead_letter = dlq.add_failed_task(task=task)
        assert dead_letter.task.payload["data"] == "Hello\nWorld\t!@#$%"

    def test_replay_with_unicode(self):
        """Test replaying task with unicode data."""
        dlq = DeadLetterQueue()

        task = Task(name="unicode_task", payload={"emoji": "😀🎉"})
        task.fail(error="Failed")

        dead_letter = dlq.add_failed_task(task=task)
        replayed = dlq.replay(dead_letter.id)

        assert replayed.payload["emoji"] == "😀🎉"

    def test_empty_metadata(self):
        """Test task with empty metadata dict."""
        dlq = DeadLetterQueue()

        task = Task(name="test_task")
        task.metadata = {}
        task.fail(error="Failed")

        dead_letter = dlq.add_failed_task(task=task)
        assert dead_letter.metadata == {}

    def test_none_values_in_optional_fields(self):
        """Test handling of None values in optional fields."""
        dlq = DeadLetterQueue()

        task = Task(name="test_task")
        task.fail(error="Failed")

        # Add with None optional fields
        dead_letter = dlq.add_failed_task(
            task=task,
            error_message=None,
            error_type=None,
            metadata=None,
        )

        assert dead_letter.error_message is None
        assert dead_letter.error_type is None
        assert dead_letter.metadata == {}


class TestDLQIntegration:
    """Integration tests with retry system."""

    def test_dlq_integration_with_retry_count(self):
        """Test DLQ with realistic retry scenario."""
        dlq = DeadLetterQueue()

        # Create a task that failed after retries
        task = Task(name="failing_task", max_retries=3)
        task.fail(error="Service unavailable")

        # Simulate retry attempts
        for i in range(4):  # Original + 3 retries
            task.retry_count = i
            if i == 3:
                task.fail(error="Service unavailable", can_retry=False)
                break

        # Add to DLQ
        dead_letter = dlq.add_failed_task(
            task=task,
            original_queue="main",
            reason="max_retries_exceeded",
            retry_count=3,
        )

        assert dead_letter.retry_count == 3
        assert dead_letter.task.retry_count == 3

        # Replay with reset
        replayed = dlq.replay(dead_letter.id, reset_retries=True)
        assert replayed.retry_count == 0
        assert replayed.max_retries == 6  # Auto-increased

    def test_dlq_different_failure_reasons(self):
        """Test DLQ with various failure reasons."""
        dlq = DeadLetterQueue()

        reasons = [
            "max_retries_exceeded",
            "timeout",
            "invalid_payload",
            "permission_denied",
            "service_not_available",
        ]

        for reason in reasons:
            task = Task(name=f"task_{reason}")
            task.fail(error=reason)
            dlq.add_failed_task(task=task, reason=reason)

        # Verify all are there
        assert dlq.count() == len(reasons)

        # Filter by each reason
        for reason in reasons:
            tasks = dlq.inspect(reason=reason)
            assert len(tasks) == 1
            assert tasks[0].reason == reason

    def test_dlq_lifecycle(self):
        """Test complete DLQ lifecycle: add, inspect, replay, purge."""
        dlq = DeadLetterQueue()

        # Add failed task
        task = Task(name="lifecycle_task")
        task.fail(error="Initial failure")

        dead_letter = dlq.add_failed_task(
            task=task,
            original_queue="main",
            reason="max_retries_exceeded",
        )

        # Inspect
        assert dlq.count() == 1
        inspected = dlq.inspect()
        assert len(inspected) == 1

        # Replay
        replayed = dlq.replay(dead_letter.id, reset_retries=True)
        assert replayed.status == TaskStatus.PENDING
        assert dlq.count() == 0

        # Add back to test purge
        dlq.add_failed_task(task=replayed, reason="test")
        assert dlq.count() == 1

        # Purge
        count = dlq.purge_all()
        assert count == 1
        assert dlq.count() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])