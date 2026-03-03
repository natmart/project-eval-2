"""
Comprehensive tests for the core task queue data models.

Tests cover:
- TaskStatus enum functionality
- TaskResult creation and serialization
- Task creation, lifecycle, and serialization
- Edge cases and validation
"""

import json
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Dict
from uuid import UUID, uuid4

import pytest

from python_task_queue.models import Task, TaskResult, TaskStatus


class TestTaskStatus:
    """Test cases for the TaskStatus enum."""

    def test_all_status_values_exist(self):
        """Verify all expected status values are defined."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.RETRYING.value == "retrying"

    def test_status_string_representation(self):
        """Test that statuses convert to strings correctly."""
        assert str(TaskStatus.PENDING) == "pending"
        assert str(TaskStatus.RUNNING) == "running"

    def test_from_string_valid(self):
        """Test creating TaskStatus from valid strings."""
        assert TaskStatus.from_string("pending") == TaskStatus.PENDING
        assert TaskStatus.from_string("RUNNING") == TaskStatus.RUNNING
        assert TaskStatus.from_string("Completed") == TaskStatus.COMPLETED

    def test_from_string_invalid(self):
        """Test that from_string raises ValueError for invalid strings."""
        with pytest.raises(ValueError) as exc_info:
            TaskStatus.from_string("invalid_status")
        assert "Invalid task status" in str(exc_info.value)

    def test_is_terminal(self):
        """Test identification of terminal states."""
        assert TaskStatus.COMPLETED.is_terminal()
        assert TaskStatus.FAILED.is_terminal()
        assert not TaskStatus.PENDING.is_terminal()
        assert not TaskStatus.RUNNING.is_terminal()
        assert not TaskStatus.RETRYING.is_terminal()

    def test_is_active(self):
        """Test identification of active states."""
        assert TaskStatus.PENDING.is_active()
        assert TaskStatus.RUNNING.is_active()
        assert TaskStatus.RETRYING.is_active()
        assert not TaskStatus.COMPLETED.is_active()
        assert not TaskStatus.FAILED.is_active()

    def test_can_retry(self):
        """Test determination of retryable states."""
        assert TaskStatus.FAILED.can_retry()
        assert TaskStatus.RETRYING.can_retry()
        assert not TaskStatus.PENDING.can_retry()
        assert not TaskStatus.RUNNING.can_retry()
        assert not TaskStatus.COMPLETED.can_retry()


class TestTaskResult:
    """Test cases for the TaskResult dataclass."""

    def test_create_success_result(self):
        """Test creating a successful TaskResult."""
        result = TaskResult.from_success("test_value", metadata={"key": "value"})
        
        assert result.success is True
        assert result.value == "test_value"
        assert result.error is None
        assert result.error_type is None
        assert result.traceback is None
        assert result.metadata == {"key": "value"}

    def test_create_failure_result(self):
        """Test creating a failed TaskResult."""
        result = TaskResult.from_failure(
            error="Something went wrong",
            error_type="ValueError",
            traceback="Stack trace here",
            metadata={"attempt": 1},
        )
        
        assert result.success is False
        assert result.value is None
        assert result.error == "Something went wrong"
        assert result.error_type == "ValueError"
        assert result.traceback == "Stack trace here"
        assert result.metadata == {"attempt": 1}

    def test_repr_success(self):
        """Test string representation of successful result."""
        result = TaskResult.from_success("short value")
        repr_str = repr(result)
        
        assert "SUCCESS" in repr_str
        assert "short value" in repr_str

    def test_repr_failure(self):
        """Test string representation of failed result."""
        result = TaskResult.from_failure("Error message", "RuntimeError")
        repr_str = repr(result)
        
        assert "FAILED" in repr_str
        assert "RuntimeError" in repr_str
        assert "Error message" in repr_str

    def test_to_dict(self):
        """Test TaskResult serialization to dictionary."""
        result = TaskResult.from_success(42, metadata={"count": 5})
        data = result.to_dict()
        
        assert data["success"] is True
        assert data["value"] == 42
        assert data["error"] is None
        assert data["metadata"] == {"count": 5}

    def test_from_dict(self):
        """Test TaskResult deserialization from dictionary."""
        data = {
            "success": False,
            "value": None,
            "error": "Test error",
            "error_type": "Exception",
            "traceback": None,
            "metadata": {},
        }
        result = TaskResult.from_dict(data)
        
        assert result.success is False
        assert result.error == "Test error"
        assert result.error_type == "Exception"

    def test_to_json_and_from_json(self):
        """TaskTest JSON serialization roundtrip."""
        original = TaskResult.from_success({"nested": "data"}, metadata={"source": "test"})
        
        json_str = original.to_json()
        restored = TaskResult.from_json(json_str)
        
        assert restored.success == original.success
        assert restored.value == original.value
        assert restored.metadata == original.metadata

    def test_result_with_complex_value(self):
        """Test TaskResult with complex value types."""
        complex_value = {"list": [1, 2, 3], "dict": {"nested": True}, "number": 42.5}
        result = TaskResult.from_success(complex_value)
        
        assert result.value == complex_value

    def test_empty_metadata_defaults(self):
        """Test that empty metadata defaults to empty dict."""
        result = TaskResult(success=True, value="test")
        assert result.metadata == {}
        
        result2 = TaskResult(success=False, error="test")
        assert result2.metadata == {}


class TestTaskCreation:
    """Test cases for Task creation and initialization."""

    def test_create_minimal_task(self):
        """Test creating a task with minimal parameters."""
        task = Task()
        
        assert isinstance(task.id, UUID)
        assert task.name == "unnamed_task"
        assert task.status == TaskStatus.PENDING
        assert task.priority == 5
        assert task.payload is None
        assert task.retry_count == 0
        assert task.max_retries == 3
        assert isinstance(task.created_at, datetime)
        assert task.started_at is None
        assert task.completed_at is None
        assert task.result is None

    def test_create_task_with_all_fields(self):
        """Test creating a task with all fields specified."""
        task_id = uuid4()
        created = datetime.utcnow()
        
        task = Task(
            id=task_id,
            name="test_task",
            payload={"key": "value"},
            status=TaskStatus.RUNNING,
            priority=2,
            created_at=created,
            started_at=created,
            completed_at=created,
            retry_count=1,
            max_retries=5,
            metadata={"custom": "data"},
        )
        
        assert task.id == task_id
        assert task.name == "test_task"
        assert task.payload == {"key": "value"}
        assert task.status == TaskStatus.RUNNING
        assert task.priority == 2
        assert task.created_at == created
        assert task.started_at == created
        assert task.completed_at == created
        assert task.retry_count == 1
        assert task.max_retries == 5
        assert task.metadata == {"custom": "data"}

    def test_task_with_string_status(self):
        """Test that string status is converted to TaskStatus enum."""
        task = Task(status="running")
        
        assert isinstance(task.status, TaskStatus)
        assert task.status == TaskStatus.RUNNING

    def test_invalid_priority_raises_error(self):
        """Test that invalid priority raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Task(priority=0)
        assert "Priority must be between 1 and 10" in str(exc_info.value)
        
        with pytest.raises(ValueError):
            Task(priority=11)

    def test_repr_includes_key_info(self):
        """Test that repr includes key task information."""
        task = Task(name="my_task", priority=3, status=TaskStatus.RUNNING, retry_count=2)
        repr_str = repr(task)
        
        assert "my_task" in repr_str
        assert "running" in repr_str
        assert "3" in repr_str
        assert "2/" in repr_str

    def test_str_provides_simple_representation(self):
        """Test that str provides a simple, readable representation."""
        task = Task(name="important_task", status=TaskStatus.COMPLETED)
        str_repr = str(task)
        
        assert "important_task" in str_repr
        assert "completed" in str_repr

    def test_task_comparison_by_priority(self):
        """Test that tasks are compared by priority."""
        high_priority = Task(name="high", priority=1)
        low_priority = Task(name="low", priority=10)
        medium_priority = Task(name="medium", priority=5)
        
        assert high_priority < medium_priority
        assert medium_priority < low_priority
        assert high_priority < low_priority

    def test_execution_time_before_completion(self):
        """Test execution_time property for incomplete task."""
        task = Task()
        assert task.execution_time is None

    def test_execution_time_after_completion(self):
        """Test execution_time calculation after task completion."""
        started = datetime.utcnow()
        completed = started + timedelta(seconds=5.5)
        
        task = Task(started_at=started, completed_at=completed)
        
        assert task.execution_time == 5.5


class TestTaskLifecycle:
    """Test cases for Task lifecycle operations."""

    def test_start_task(self):
        """Test starting a task."""
        task = Task()
        task.start()
        
        assert task.status == TaskStatus.RUNNING
        assert isinstance(task.started_at, datetime)
        assert task.started_at <= datetime.utcnow()

    def test_start_already_running_task_raises_error(self):
        """Test that starting an already running task raises error."""
        task = Task(status=TaskStatus.RUNNING)
        
        with pytest.raises(ValueError) as exc_info:
            task.start()
        assert "Cannot start task" in str(exc_info.value)

    def test_start_completed_task_raises_error(self):
        """Test that starting a completed task raises error."""
        task = Task(status=TaskStatus.COMPLETED)
        
        with pytest.raises(ValueError):
            task.start()

    def test_complete_task(self):
        """Test completing a task successfully."""
        task = Task(status=TaskStatus.RUNNING)
        task.complete(result="success!")
        
        assert task.status == TaskStatus.COMPLETED
        assert isinstance(task.completed_at, datetime)
        assert task.result.success is True
        assert task.result.value == "success!"
        assert task.error is None  # Deprecated field should be None

    def test_complete_task_with_metadata(self):
        """Test completing a task with metadata."""
        task = Task(status=TaskStatus.RUNNING)
        task.complete(result=42, metadata={"worker": "1", "duration_ms": 100})
        
        assert task.result.metadata == {"worker": "1", "duration_ms": 100}

    def test_complete_pending_task_raises_error(self):
        """Test that completing a pending task raises error."""
        task = Task(status=TaskStatus.PENDING)
        
        with pytest.raises(ValueError) as exc_info:
            task.complete(result="test")
        assert "Cannot complete task" in str(exc_info.value)

    def test_fail_task(self):
        """Test failing a task."""
        task = Task(status=TaskStatus.RUNNING)
        task.fail(error="Something failed", error_type="RuntimeError")
        
        assert task.status == TaskStatus.FAILED
        assert isinstance(task.completed_at, datetime)
        assert task.result.success is False
        assert task.result.error == "Something failed"
        assert task.result.error_type == "RuntimeError"
        assert task.error == "Something failed"  # Check deprecated field

    def test_fail_task_with_traceback(self):
        """Test failing a task with traceback."""
        task = Task(status=TaskStatus.RUNNING)
        traceback = "Traceback (most recent call last):\n  ..."
        
        task.fail(error="Error", traceback=traceback)
        
        assert task.result.traceback == traceback

    def test_fail_task_with_retry_available(self):
        """Test that failed task with retries goes to RETRYING."""
        task = Task(status=TaskStatus.RUNNING, retry_count=0, max_retries=3)
        task.fail(error="Will retry")
        
        assert task.status == TaskStatus.RETRYING
        assert task.retry_count == 1

    def test_fail_task_with_max_retries_exceeded(self):
        """Test that failed task with no retries stays FAILED."""
        task = Task(status=TaskStatus.RUNNING, retry_count=3, max_retries=3)
        task.fail(error="No more retries")
        
        assert task.status == TaskStatus.FAILED
        assert task.retry_count == 3

    def test_fail_task_without_retry_permission(self):
        """Test failing task with can_retry=False."""
        task = Task(status=TaskStatus.RUNNING, retry_count=0, max_retries=3)
        task.fail(error="Immediate failure", can_retry=False)
        
        assert task.status == TaskStatus.FAILED
        assert task.retry_count == 0

    def test_retry_task(self):
        """Test retrying a task."""
        task = Task(status=TaskStatus.FAILED, retry_count=0, max_retries=3)
        task.retry()
        
        assert task.status == TaskStatus.RETRYING
        assert task.retry_count == 1

    def test_retry_task_raises_when_not_allowed(self):
        """Test that retrying beyond max_retries raises error."""
        task = Task(status=TaskStatus.FAILED, retry_count=3, max_retries=3)
        
        with pytest.raises(ValueError) as exc_info:
            task.retry()
        assert "Cannot be retried" in str(exc_info.value)

    def test_can_be_retried_property(self):
        """Test can_be_retried property logic."""
        # Can retry: failed with attempts left
        task1 = Task(status=TaskStatus.FAILED, retry_count=0, max_retries=3)
        assert task1.can_be_retried is True
        
        # Cannot retry: failed with max retries exhausted
        task2 = Task(status=TaskStatus.FAILED, retry_count=3, max_retries=3)
        assert task2.can_be_retried is False
        
        # Cannot retry: completed tasks are terminal
        task3 = Task(status=TaskStatus.COMPLETED, retry_count=0, max_retries=3)
        assert task3.can_be_retried is False
        
        # Cannot retry: pending tasks
        task4 = Task(status=TaskStatus.PENDING, retry_count=0, max_retries=3)
        assert task4.can_be_retried is False


class TestTaskSerialization:
    """Test cases for Task serialization and deserialization."""

    def test_to_dict(self):
        """Test Task serialization to dictionary."""
        task_id = uuid4()
        created = datetime.utcnow()
        
        task = Task(
            id=task_id,
            name="test",
            payload={"data": "value"},
            status=TaskStatus.COMPLETED,
            priority=3,
            created_at=created,
            started_at=created,
            completed_at=created,
            retry_count=1,
            max_retries=5,
            metadata={"key": "val"},
        )
        task.complete(result="done")
        
        data = task.to_dict()
        
        assert isinstance(data["id"], str)
        assert data["id"] == str(task_id)
        assert data["name"] == "test"
        assert data["status"] == "completed"
        assert data["priority"] == 3
        assert data["retry_count"] == 1
        assert data["max_retries"] == 5
        assert data["result"]["success"] is True
        assert data["result"]["value"] == "done"

    def test_from_dict(self):
        """Test Task deserialization from dictionary."""
        task_id = uuid4()
        created = datetime.utcnow()
        
        data = {
            "id": str(task_id),
            "name": "test",
            "payload": {"data": "value"},
            "status": "completed",
            "priority": 3,
            "created_at": created.isoformat(),
            "started_at": created.isoformat(),
            "completed_at": created.isoformat(),
            "result": {
                "success": True,
                "value": "done",
                "error": None,
                "error_type": None,
                "traceback": None,
                "metadata": {},
            },
            "error": None,
            "retry_count": 1,
            "max_retries": 5,
            "metadata": {"key": "val"},
        }
        
        task = Task.from_dict(data)
        
        assert isinstance(task.id, UUID)
        assert task.id == task_id
        assert task.name == "test"
        assert task.status == TaskStatus.COMPLETED
        assert task.priority == 3
        assert task.retry_count == 1
        assert task.result.success is True
        assert task.result.value == "done"

    def test_serialization_roundtrip(self):
        """Test full serialization roundtrip: Task -> dict -> Task."""
        original = Task(
            name="roundtrip_test",
            payload={"nested": {"data": True}},
            status=TaskStatus.RUNNING,
            priority=2,
            retry_count=1,
            max_retries=4,
            metadata={"test": True},
        )
        
        # Serialize
        data = original.to_dict()
        
        # Deserialize
        restored = Task.from_dict(data)
        
        # Verify equality of all fields
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.payload == original.payload
        assert restored.status == original.status
        assert restored.priority == original.priority
        assert restored.retry_count == original.retry_count
        assert restored.max_retries == original.max_retries
        assert restored.metadata == original.metadata

    def test_to_json_and_from_json(self):
        """Test JSON serialization roundtrip."""
        original = Task(
            name="json_test",
            payload=[1, 2, 3],
            status=TaskStatus.RETRYING,
            priority=7,
        )
        
        json_str = original.to_json()
        restored = Task.from_json(json_str)
        
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.status == original.status
        assert restored.payload == original.payload

    def test_serialization_with_none_fields(self):
        """Test serialization when optional fields are None."""
        task = Task(
            name="none_test",
            status=TaskStatus.PENDING,
        )
        
        data = task.to_dict()
        restored = Task.from_dict(data)
        
        assert restored.started_at is None
        assert restored.completed_at is None
        assert restored.result is None

    def test_serialization_preserves_uuid(self):
        """Test that UUID serialization preserves exact value."""
        original_id = uuid4()
        task = Task(id=original_id, name="uuid_test")
        
        data = task.to_dict()
        restored = Task.from_dict(data)
        
        assert restored.id == original_id
        assert type(restored.id) is UUID

    def test_copy_creates_independent_task(self):
        """Test that copy creates an independent Task instance."""
        original = Task(
            name="original",
            status=TaskStatus.PENDING,
            priority=5,
            retry_count=0,
        )
        
        copy_ = original.copy()
        
        assert copy_.id == original.id
        assert copy_.name == original.name
        assert copy_.status == original.status
        
        # Verify they're not the same object
        assert copy_ is not original

    def test_copy_with_changes(self):
        """Test copying with field modifications."""
        original = Task(
            name="original",
            status=TaskStatus.PENDING,
            retry_count=0,
        )
        
        copy_ = original.copy(
            status=TaskStatus.RETRYING,
            retry_count=1,
            name="modified"
        )
        
        # Original should be unchanged
        assert original.status == TaskStatus.PENDING
        assert original.retry_count == 0
        assert original.name == "original"
        
        # Copy should have changes
        assert copy_.status == TaskStatus.RETRYING
        assert copy_.retry_count == 1
        assert copy_.name == "modified"
        
        # ID should be the same
        assert copy_.id == original.id


class TestTaskEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_task_with_large_payload(self):
        """Test task with very large payload."""
        large_payload = {"data": "x" * 1000000}  # 1MB string
        task = Task(name="large", payload=large_payload)
        
        assert len(task.payload["data"]) == 1000000
        
        # Should still be serializable
        data = task.to_dict()
        assert len(data["payload"]["data"]) == 1000000

    def test_task_with_unicode_name(self):
        """Test task with Unicode characters in name."""
        task = Task(name="测试🚀任务")
        
        assert "测试🚀任务" in str(task)
        assert "测试🚀任务" in repr(task)

    def test_task_priority_boundaries(self):
        """Test task priority at boundaries."""
        low_priority = Task(priority=10, name="low")
        high_priority = Task(priority=1, name="high")
        
        assert high_priority < low_priority

    def test_retry_count_exactly_equals_max_retries(self):
        """Test behavior when retry_count equals max_retries."""
        task = Task(status=TaskStatus.FAILED, retry_count=3, max_retries=3)
        
        assert task.can_be_retried is False
        assert task.status == TaskStatus.FAILED

    def test_zero_max_retries(self):
        """Test task with max_retries set to 0."""
        task = Task(status=TaskStatus.FAILED, max_retries=0, retry_count=0)
        
        assert task.can_be_retried is False
        task.fail("Error", can_retry=True)  # Should still fail
        assert task.status == TaskStatus.FAILED

    def test_metadata_mutation_does_not_affect_other_tasks(self):
        """Test that metadata dict can be mutated independently."""
        task1 = Task(metadata={"shared_key": "value1"})
        task2 = Task(metadata={"shared_key": "value2"})
        
        task1.metadata["shared_key"] = "changed"
        
        assert task1.metadata["shared_key"] == "changed"
        assert task2.metadata["shared_key"] == "value2"

    def test_task_result_with_none_value_success(self):
        """Test successful TaskResult with None value."""
        result = TaskResult.from_success(None)
        
        assert result.success is True
        assert result.value is None

    def test_multiple_status_transitions(self):
        """Test complete lifecycle with multiple states."""
        task = Task()
        
        # Pending -> Running
        task.start()
        assert task.status == TaskStatus.RUNNING
        
        # Running -> Retrying (simulated failure with retry)
        task.fail("Temp failure", can_retry=True)
        assert task.status == TaskStatus.RETRYING
        assert task.retry_count == 1
        
        # Retrying -> Running (restart)
        task.started_at = datetime.utcnow()  # Reset for retry
        task.status = TaskStatus.RUNNING
        
        # Running -> Completed
        task.complete(result="success")
        assert task.status == TaskStatus.COMPLETED
        assert task.retry_count == 1  # Should preserve retry count


class TestIntegration:
    """Integration tests testing interactions between models."""

    def test_task_with_result_serialization(self):
        """Test serialization of task with result."""
        task = Task(name="result_test")
        task.start()
        task.complete(result={"status": "ok", "data": [1, 2, 3]})
        
        json_str = task.to_json()
        restored = Task.from_json(json_str)
        
        assert restored.result.success is True
        assert restored.result.value == {"status": "ok", "data": [1, 2, 3]}

    def test_task_with_error_result_serialization(self):
        """Test serialization of task with error result."""
        task = Task(name="error_test")
        task.start()
        task.fail(
            error="Database connection failed",
            error_type="ConnectionError",
            traceback="Stack trace...",
            can_retry=False,
        )
        
        data = task.to_dict()
        restored = Task.from_dict(data)
        
        assert restored.status == TaskStatus.FAILED
        assert restored.result.success is False
        assert restored.result.error == "Database connection failed"
        assert restored.result.error_type == "ConnectionError"
        assert restored.result.traceback is not None

    def test_task_status_transitions_with_result(self):
        """Test that status and result stay synchronized."""
        task = Task()
        
        # Initial state
        assert task.status == TaskStatus.PENDING
        assert task.result is None
        
        # After start
        task.start()
        assert task.status == TaskStatus.RUNNING
        
        # After completion
        task.complete(result=123)
        assert task.status == TaskStatus.COMPLETED
        assert task.result is not None
        assert task.result.success is True

    def test_sort_tasks_by_priority(self):
        """Test sorting a list of tasks by priority."""
        tasks = [
            Task(name="low", priority=10),
            Task(name="high", priority=1),
            Task(name="medium", priority=5),
            Task(name="medium_high", priority=3),
        ]
        
        sorted_tasks = sorted(tasks)
        
        assert sorted_tasks[0].name == "high"
        assert sorted_tasks[1].name == "medium_high"
        assert sorted_tasks[2].name == "medium"
        assert sorted_tasks[3].name == "low"

    def test_task_status_methods_consistency(self):
        """Test consistency across TaskStatus methods."""
        for status in TaskStatus:
            # A task should be either terminal or active, not both
            assert status.is_terminal() != status.is_active()
            
            # Terminal statuses should not allow retry
            if status.is_terminal():
                assert not status.can_retry()