"""
Comprehensive tests for the Dead Letter Queue (DLQ).

Tests cover:
- DeadLetterTask dataclass functionality
- DLQBackend operations
- MemoryDLQBackend thread-safe implementation
- DeadLetterQueue high-level operations (add, inspect, replay, purge, stats)
"""

import pytest
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from python_task_queue.dlq import (
    DeadLetterTask,
    DLQBackend,
    MemoryDLQBackend,
    DeadLetterQueue,
)
from python_task_queue.models import Task, TaskStatus, TaskResult


class TestDeadLetterTask:
    """Test cases for DeadLetterTask dataclass."""
    
    def test_create_dead_letter_task(self):
        """Test creating a DeadLetterTask."""
        task = Task(name="test_task", payload={"key": "value"})
        dead_task = DeadLetterTask(
            task=task,
            reason="max_retries_exceeded",
            error_message="Task failed",
            error_type="ValueError",
        )
        
        assert dead_task.task.name == "test_task"
        assert dead_task.reason == "max_retries_exceeded"
        assert dead_task.error_message == "Task failed"
        assert dead_task.error_type == "ValueError"
        assert dead_task.original_retry_count == 0
        assert dead_task.original_max_retries == 0
    
    def test_dead_letter_task_with_retry_info(self):
        """Test DeadLetterTask with retry information."""
        task = Task(
            name="retry_task",
            retry_count=3,
            max_retries=3,
        )
        task.fail(
            error="Permanent failure",
            error_type="RuntimeError",
        )
        
        dead_task = DeadLetterTask(
            task=task,
            reason="exhausted_retries",
            error_message=task.error,
            error_type="RuntimeError",
            original_retry_count=task.retry_count,
            original_max_retries=task.max_retries,
            queue_name="test_queue",
        )
        
        assert dead_task.original_retry_count == 3
        assert dead_task.original_max_retries == 3
        assert dead_task.queue_name == "test_queue"
        assert dead_task.status == TaskStatus.FAILED
    
    def test_dead_letter_task_serialization(self):
        """Test DeadLetterTask to_dict and from_dict."""
        task = Task(name="test_task", payload={"key": "value"})
        dead_task = DeadLetterTask(
            task=task,
            reason="max_retries_exceeded",
            error_message="Error",
            queue_name="test_queue",
        )
        
        # Convert to dict
        data = dead_task.to_dict()
        assert data["id"] == str(dead_task.id)
        assert "task" in data
        assert data["reason"] == "max_retries_exceeded"
        assert data["queue_name"] == "test_queue"
        assert "failed_at" in data
        
        # Convert back from dict
        restored = DeadLetterTask.from_dict(data)
        assert restored.id == dead_task.id
        assert restored.task.name == dead_task.task.name
        assert restored.reason == dead_task.reason
        assert restored.error_message == dead_task.error_message
    
    def test_dead_letter_task_with_metadata(self):
        """Test DeadLetterTask with custom metadata."""
        task = Task(name="test_task")
        dead_task = DeadLetterTask(
            task=task,
            reason="custom_failure",
            metadata={"worker_id": "worker-1", "attempt": 5},
        )
        
        assert dead_task.metadata == {"worker_id": "worker-1", "attempt": 5}


class TestMemoryDLQBackend:
    """Test cases for MemoryDLQBackend."""
    
    def test_backend_add_and_get_task(self):
        """Test adding and retrieving a task."""
        backend = MemoryDLQBackend()
        task = Task(name="test_task")
        dead_task = DeadLetterTask(task=task, reason="test_reason")
        
        backend.add_task(dead_task)
        retrieved = backend.get_task(dead_task.id)
        
        assert retrieved is not None
        assert retrieved.id == dead_task.id
        assert retrieved.reason == "test_reason"
    
    def test_backend_get_nonexistent_task(self):
        """Test getting a task that doesn't exist."""
        backend = MemoryDLQBackend()
        result = backend.get_task(uuid4())
        assert result is None
    
    def test_backend_get_all_tasks(self):
        """Test getting all tasks from the DLQ."""
        backend = MemoryDLQBackend()
        
        task1 = DeadLetterTask(task=Task(name="task1"), reason="reason1")
        task2 = DeadLetterTask(task=Task(name="task2"), reason="reason2")
        task3 = DeadLetterTask(task=Task(name="task3"), reason="reason1")
        
        backend.add_task(task1)
        backend.add_task(task2)
        backend.add_task(task3)
        
        all_tasks = backend.get_all_tasks()
        assert len(all_tasks) == 3
        
        task_ids = {t.id for t in all_tasks}
        assert task1.id in task_ids
        assert task2.id in task_ids
        assert task3.id in task_ids
    
    def test_backend_filter_by_reason(self):
        """Test filtering tasks by reason."""
        backend = MemoryDLQBackend()
        
        task1 = DeadLetterTask(task=Task(name="task1"), reason="reason1")
        task2 = DeadLetterTask(task=Task(name="task2"), reason="reason2")
        task3 = DeadLetterTask(task=Task(name="task3"), reason="reason1")
        
        backend.add_task(task1)
        backend.add_task(task2)
        backend.add_task(task3)
        
        filtered = backend.filter_tasks(reason="reason1")
        assert len(filtered) == 2
        assert all(t.reason == "reason1" for t in filtered)
    
    def test_backend_filter_by_queue_name(self):
        """Test filtering tasks by queue name."""
        backend = MemoryDLQBackend()
        
        task1 = DeadLetterTask(task=Task(name="task1"), reason="r1", queue_name="queue_a")
        task2 = DeadLetterTask(task=Task(name="task2"), reason="r2", queue_name="queue_b")
        task3 = DeadLetterTask(task=Task(name="task3"), reason="r1", queue_name="queue_a")
        
        backend.add_task(task1)
        backend.add_task(task2)
        backend.add_task(task3)
        
        filtered = backend.filter_tasks(queue_name="queue_a")
        assert len(filtered) == 2
        assert all(t.queue_name == "queue_a" for t in filtered)
    
    def test_backend_filter_by_reason_and_queue(self):
        """Test filtering by both reason and queue name."""
        backend = MemoryDLQBackend()
        
        task1 = DeadLetterTask(task=Task(name="task1"), reason="r1", queue_name="queue_a")
        task2 = DeadLetterTask(task=Task(name="task2"), reason="r2", queue_name="queue_a")
        task3 = DeadLetterTask(task=Task(name="task3"), reason="r1", queue_name="queue_b")
        task4 = DeadLetterTask(task=Task(name="task4"), reason="r1", queue_name="queue_a")
        
        backend.add_task(task1)
        backend.add_task(task2)
        backend.add_task(task3)
        backend.add_task(task4)
        
        # Filter by both
        filtered = backend.filter_tasks(reason="r1", queue_name="queue_a")
        assert len(filtered) == 2
        
        task_ids = {t.id for t in filtered}
        assert task1.id in task_ids
        assert task4.id in task_ids
        assert task3.id not in task_ids  # Wrong queue
        assert task2.id not in task_ids  # Wrong reason
    
    def test_backend_remove_task(self):
        """Test removing a task."""
        backend = MemoryDLQBackend()
        task = DeadLetterTask(task=Task(name="test"), reason="test")
        
        backend.add_task(task)
        assert backend.get_task(task.id) is not None
        
        removed = backend.remove_task(task.id)
        assert removed is True
        assert backend.get_task(task.id) is None
    
    def test_backend_remove_nonexistent_task(self):
        """Test removing a task that doesn't exist."""
        backend = MemoryDLQBackend()
        removed = backend.remove_task(uuid4())
        assert removed is False
    
    def test_backend_purge_all(self):
        """Test purging all tasks."""
        backend = MemoryDLQBackend()
        
        for i in range(5):
            backend.add_task(DeadLetterTask(task=Task(name=f"task{i}"), reason="test"))
        
        assert len(backend.get_all_tasks()) == 5
        count = backend.purge_all()
        assert count == 5
        assert len(backend.get_all_tasks()) == 0
    
    def test_backend_purge_filtered(self):
        """Test purging tasks with filters."""
        backend = MemoryDLQBackend()
        
        task1 = DeadLetterTask(task=Task(name="task1"), reason="r1", queue_name="queue_a")
        task2 = DeadLetterTask(task=Task(name="task2"), reason="r2", queue_name="queue_a")
        task3 = DeadLetterTask(task=Task(name="task3"), reason="r1", queue_name="queue_b")
        
        backend.add_task(task1)
        backend.add_task(task2)
        backend.add_task(task3)
        
        # Purge by reason
        count = backend.purge_filtered(reason="r1")
        assert count == 2
        assert len(backend.get_all_tasks()) == 1
        
        # Remaining task should be task2
        remaining = backend.get_all_tasks()
        assert len(remaining) == 1
        assert remaining[0].id == task2.id
    
    def test_backend_clear(self):
        """Test clearing the DLQ."""
        backend = MemoryDLQBackend()
        
        for i in range(3):
            backend.add_task(DeadLetterTask(task=Task(name=f"task{i}"), reason="test"))
        
        backend.clear()
        assert len(backend.get_all_tasks()) == 0
    
    def test_backend_get_stats(self):
        """Test getting DLQ statistics."""
        backend = MemoryDLQBackend()
        
        # Add tasks with different reasons and queues
        backend.add_task(DeadLetterTask(task=Task(name="t1"), reason="r1", queue_name="q1"))
        backend.add_task(DeadLetterTask(task=Task(name="t2"), reason="r1", queue_name="q1"))
        backend.add_task(DeadLetterTask(task=Task(name="t3"), reason="r2", queue_name="q1"))
        backend.add_task(DeadLetterTask(task=Task(name="t4"), reason="r1", queue_name="q2"))
        
        stats = backend.get_stats()
        assert stats["total_tasks"] == 4
        assert stats["by_reason"]["r1"] == 3
        assert stats["by_reason"]["r2"] == 1
        assert stats["by_queue"]["q1"] == 3
        assert stats["by_queue"]["q2"] == 1
    
    def test_backend_stats_with_no_queue(self):
        """Test stats includes default queue for tasks with no queue."""
        backend = MemoryDLQBackend()
        
        backend.add_task(DeadLetterTask(task=Task(name="t1"), reason="r1"))
        backend.add_task(DeadLetterTask(task=Task(name="t2"), reason="r1", queue_name="q1"))
        
        stats = backend.get_stats()
        assert stats["by_queue"]["default"] == 1
        assert stats["by_queue"]["q1"] == 1


class TestDeadLetterQueue:
    """Test cases for DeadLetterQueue high-level interface."""
    
    def test_dlq_add_task(self):
        """Test adding a task to the DLQ."""
        dlq = DeadLetterQueue()
        
        task = Task(name="test_task")
        dead_task = dlq.add(task, reason="test_reason", queue_name="test_queue")
        
        assert dead_task.task.name == "test_task"
        assert dead_task.reason == "test_reason"
        assert dead_task.queue_name == "test_queue"
        assert dlq.count() == 1
    
    def test_dlq_add_task extracts_error_from_result(self):
        """Test that adding a task extracts error info from result."""
        dlq = DeadLetterQueue()
        
        task = Task(name="failing_task")
        task.fail(
            error="This task failed",
            error_type="CustomError",
            traceback="Line 1\nLine 2",
        )
        
        dead_task = dlq.add(task, reason="execution_failed")
        
        assert dead_task.error_message == "This task failed"
        assert dead_task.error_type == "CustomError"
    
    def test_dlq_add_task extracts_error_from_deprecated_field(self):
        """Test that adding a task extracts error info from deprecated error field."""
        dlq = DeadLetterQueue()
        
        task = Task(name="failing_task")
        task.error = "Deprecated error field"
        
        dead_task = dlq.add(task, reason="execution_failed")
        
        assert dead_task.error_message == "Deprecated error field"
    
    def test_dlq_inspect_all(self):
        """Test inspecting all tasks in the DLQ."""
        dlq = DeadLetterQueue()
        
        dlq.add(Task(name="task1"), reason="r1")
        dlq.add(Task(name="task2"), reason="r2")
        dlq.add(Task(name="task3"), reason="r1")
        
        all_tasks = dlq.inspect_all()
        assert len(all_tasks) == 3
    
    def test_dlq_inspect_with_filter(self):
        """Test inspecting tasks with filters."""
        dlq = DeadLetterQueue()
        
        dlq.add(Task(name="task1"), reason="r1", queue_name="q1")
        dlq.add(Task(name="task2"), reason="r2", queue_name="q1")
        dlq.add(Task(name="task3"), reason="r1", queue_name="q2")
        
        # Filter by reason
        tasks = dlq.inspect(reason="r1")
        assert len(tasks) == 2
        
        # Filter by queue
        tasks = dlq.inspect(queue_name="q1")
        assert len(tasks) == 2
        
        # Filter by both
        tasks = dlq.inspect(reason="r1", queue_name="q2")
        assert len(tasks) == 1
    
    def test_dlq_get_specific_task(self):
        """Test getting a specific task by ID."""
        dlq = DeadLetterQueue()
        
        dead_task = dlq.add(Task(name="test_task"), reason="test")
        retrieved = dlq.get(dead_task.id)
        
        assert retrieved is not None
        assert retrieved.id == dead_task.id
    
    def test_dlq_replay_single_task(self):
        """Test replaying a single task from the DLQ."""
        dlq = DeadLetterQueue()
        
        original_task = Task(name="replay_task", payload={"data": "value"})
        dead_task = dlq.add(original_task, reason="replay_test")
        
        # Verify task is in DLQ
        assert dlq.count() == 1
        
        # Replay the task
        replayed_task = dlq.replay(dead_task.id)
        
        assert replayed_task is not None
        assert replayed_task.name == "replay_task"
        assert replayed_task.payload == {"data": "value"}
        
        # Verify task is removed from DLQ
        assert dlq.count() == 0
    
    def test_dlq_replay_nonexistent_task(self):
        """Test replaying a task that doesn't exist."""
        dlq = DeadLetterQueue()
        result = dlq.replay(uuid4())
        assert result is None
    
    def test_dlq_replay_with_reset_retry_count(self):
        """Test replaying a task with retry count reset."""
        dlq = DeadLetterQueue()
        
        task = Task(name="retry_task", retry_count=5, max_retries=5)
        dead_task = dlq.add(task, reason="exhausted_retries")
        
        # Replay with reset
        replayed_task = dlq.replay(dead_task.id, reset_retry_count=True)
        
        assert replayed_task is not None
        assert replayed_task.retry_count == 0
    
    def test_dlq_replay_without_reset_retry_count(self):
        """Test replaying a task without resetting retry count."""
        dlq = DeadLetterQueue()
        
        task = Task(name="retry_task", retry_count=5, max_retries=5)
        dead_task = dlq.add(task, reason="exhausted_retries")
        
        # Replay without reset
        replayed_task = dlq.replay(dead_task.id, reset_retry_count=False)
        
        assert replayed_task is not None
        assert replayed_task.retry_count == 5
    
    def test_dlq_replay_filtered(self):
        """Test replaying multiple tasks with filters."""
        dlq = DeadLetterQueue()
        
        dlq.add(Task(name="task1"), reason="r1", queue_name="q1")
        dlq.add(Task(name="task2"), reason="r2", queue_name="q1")
        dlq.add(Task(name="task3"), reason="r1", queue_name="q2")
        
        # Replay by reason
        tasks = dlq.replay_filtered(reason="r1")
        assert len(tasks) == 2
        assert dlq.count() == 1  # Only task2 should remain
    
    def test_dlq_replay_filtered_with_reset(self):
        """Test replaying filtered tasks with retry count reset."""
        dlq = DeadLetterQueue()
        
        task1 = Task(name="task1", retry_count=3)
        task2 = Task(name="task2", retry_count=4)
        
        dlq.add(task1, reason="r1")
        dlq.add(task2, reason="r1")
        
        tasks = dlq.replay_filtered(reason="r1", reset_retry_count=True)
        
        assert all(t.retry_count == 0 for t in tasks)
    
    def test_dlq_purge_single_task(self):
        """Test purging a single task."""
        dlq = DeadLetterQueue()
        
        dead_task = dlq.add(Task(name="test_task"), reason="test")
        assert dlq.count() == 1
        
        result = dlq.purge(dead_task.id)
        
        assert result is True
        assert dlq.count() == 0
    
    def test_dlq_purge_nonexistent_task(self):
        """Test purging a task that doesn't exist."""
        dlq = DeadLetterQueue()
        result = dlq.purge(uuid4())
        assert result is False
    
    def test_dlq_purge_all(self):
        """Test purging all tasks from the DLQ."""
        dlq = DeadLetterQueue()
        
        for i in range(5):
            dlq.add(Task(name=f"task{i}"), reason="test")
        
        count = dlq.purge_all()
        assert count == 5
        assert dlq.count() == 0
    
    def test_dlq_purge_filtered(self):
        """Test purging tasks with filters."""
        dlq = DeadLetterQueue()
        
        dlq.add(Task(name="task1"), reason="r1", queue_name="q1")
        dlq.add(Task(name="task2"), reason="r2", queue_name="q1")
        dlq.add(Task(name="task3"), reason="r1", queue_name="q2")
        
        # Purge by reason
        count = dlq.purge_filtered(reason="r1")
        assert count == 2
        assert dlq.count() == 1
        
        # Remaining should be task2
        remaining = dlq.inspect_all()
        assert len(remaining) == 1
        assert remaining[0].task.name == "task2"
    
    def test_dlq_clear(self):
        """Test clearing the DLQ."""
        dlq = DeadLetterQueue()
        
        for i in range(3):
            dlq.add(Task(name=f"task{i}"), reason="test")
        
        dlq.clear()
        assert dlq.count() == 0
    
    def test_dlq_get_stats(self):
        """Test getting DLQ statistics."""
        dlq = DeadLetterQueue()
        
        dlq.add(Task(name="t1"), reason="r1", queue_name="q1")
        dlq.add(Task(name="t2"), reason="r1", queue_name="q1")
        dlq.add(Task(name="t3"), reason="r2", queue_name="q2")
        
        stats = dlq.get_stats()
        assert stats["total_tasks"] == 3
        assert stats["by_reason"]["r1"] == 2
        assert stats["by_reason"]["r2"] == 1
    
    def test_dlq_count(self):
        """Test getting the count of tasks in the DLQ."""
        dlq = DeadLetterQueue()
        
        assert dlq.count() == 0
        
        dlq.add(Task(name="task1"), reason="test")
        assert dlq.count() == 1
        
        dlq.add(Task(name="task2"), reason="test")
        assert dlq.count() == 2
    
    def test_dlq_with_custom_backend(self):
        """Test DLQ with a custom backend."""
        custom_backend = MemoryDLQBackend()
        dlq = DeadLetterQueue(backend=custom_backend)
        
        task = Task(name="test")
        dead_task = dlq.add(task, reason="test")
        
        # Should be in custom backend
        assert custom_backend.get_task(dead_task.id) is not None
    
    def test_dlq_add_with_metadata(self):
        """Test adding a task with metadata."""
        dlq = DeadLetterQueue()
        
        task = Task(name="test_task")
        dead_task = dlq.add(
            task,
            reason="test",
            metadata={"worker_id": "worker-1", "attempt": 3},
        )
        
        assert dead_task.metadata == {"worker_id": "worker-1", "attempt": 3}
    
    def test_dlq_serialization_round_trip(self):
        """Test full serialization round trip."""
        dlq = DeadLetterQueue()
        
        task = Task(name="test_task", payload={"key": "value"})
        dead_task = dlq.add(task, reason="test", queue_name="test_queue")
        
        # Serialize
        data = dead_task.to_dict()
        
        # Deserialize
        restored = DeadLetterTask.from_dict(data)
        
        assert restored.id == dead_task.id
        assert restored.task.name == dead_task.task.name
        assert restored.reason == dead_task.reason
        assert restored.queue_name == dead_task.queue_name


class TestDLQBackwardsCompatibility:
    """Test backwards compatibility with deprecated error field."""
    
    def test_backwards_compat_error_field(self):
        """Test that deprecated error field is handled correctly."""
        dlq = DeadLetterQueue()
        
        task = Task(name="old_task")
        task.error = "Old error message"
        
        dead_task = dlq.add(task, reason="test")
        
        # Should extract from deprecated field
        assert dead_task.error_message == "Old error message"
    
    def test_backwards_compat_both_error_fields(self):
        """Test that result.error takes preference over deprecated error field."""
        dlq = DeadLetterQueue()
        
        task = Task(name="task_with_both")
        task.error = "Old error"
        task.result = TaskResult.from_failure("New error", error_type="TestError")
        
        dead_task = dlq.add(task, reason="test")
        
        # Result error should take preference
        assert dead_task.error_message == "New error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])