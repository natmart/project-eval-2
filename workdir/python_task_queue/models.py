"""
Core data models for the Python Task Queue Library.

This module defines the fundamental data structures used throughout the task queue:
- TaskStatus: Enum representing the various states a task can be in
- Task: The primary dataclass representing a task in the queue
- TaskResult: Dataclass for capturing task execution results
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


class TaskStatus(Enum):
    """
    Enumeration of possible task statuses.

    The task lifecycle follows these common transitions:
    - pending -> running
    - running -> completed (success)
    - running -> failed (error)
    - failed -> retrying (if retries available)
    - retrying -> running
    - retrying -> failed (after max retries exceeded)

    Attributes:
        pending: Task has been created/enqueued but not yet processed
        running: Task is currently being executed
        completed: Task finished successfully
        failed: Task failed and no more retries are available
        retrying: Task failed but will be retried
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

    def __str__(self) -> str:
        """Return the string representation of the status."""
        return self.value

    @classmethod
    def from_string(cls, value: str) -> TaskStatus:
        """
        Create a TaskStatus from a string value.

        Args:
            value: String representation of the status

        Returns:
            TaskStatus enum value

        Raises:
            ValueError: If the string is not a valid status
        """
        try:
            return cls(value.lower())
        except ValueError as e:
            valid_values = [s.value for s in cls]
            raise ValueError(
                f"Invalid task status '{value}'. Valid values: {valid_values}"
            ) from e

    def is_terminal(self) -> bool:
        """
        Check if this is a terminal state (no further transitions).

        Returns:
            True if the status is COMPLETED or FAILED
        """
        return self in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    def is_active(self) -> bool:
        """
        Check if this is an active state (task can still make progress).

        Returns:
            True if the status is PENDING, RUNNING, or RETRYING
        """
        return self in (TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.RETRYING)

    def can_retry(self) -> bool:
        """
        Determine if a task in this status can be retried.

        Returns:
            True if the status allows retrying (FAILED or RETRYING)
        """
        return self in (TaskStatus.FAILED, TaskStatus.RETRYING)


@dataclass
class TaskResult:
    """
    Represents the result of a task execution.

    This class captures both successful results and error information
    from task execution. It provides a unified interface for handling
    task outcomes.

    Attributes:
        success: Whether the task completed successfully
        value: The result value if successful (None if failed)
        error: Exception/error message if failed (None if successful)
        error_type: Type of error if failed (e.g., "ValueError")
        traceback: Stack trace if failed (optional)
        metadata: Additional metadata about the execution
    """

    success: bool
    value: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    traceback: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        """Return a detailed string representation of the result."""
        status = "SUCCESS" if self.success else "FAILED"
        if self.success:
            return f"TaskResult({status}, value={repr(self.value)[:50]})"
        else:
            return f"TaskResult({status}, error_type={self.error_type}, error={repr(self.error)[:50]})"

    @classmethod
    def from_success(cls, value: Any, metadata: Optional[Dict[str, Any]] = None) -> "TaskResult":
        """
        Create a successful TaskResult.

        Args:
            value: The result value
            metadata: Optional metadata about the execution

        Returns:
            A TaskResult with success=True
        """
        return cls(success=True, value=value, metadata=metadata or {})

    @classmethod
    def from_failure(
        cls,
        error: str,
        error_type: Optional[str] = None,
        traceback: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "TaskResult":
        """
        Create a failed TaskResult.

        Args:
            error: The error message
            error_type: The type of error (e.g., "ValueError", "RuntimeError")
            traceback: Optional stack trace
            metadata: Optional metadata about the execution

        Returns:
            A TaskResult with success=False
        """
        return cls(
            success=False,
            error=error,
            error_type=error_type,
            traceback=traceback,
            metadata=metadata or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the TaskResult to a dictionary.

        This is useful for serialization to formats like JSON.

        Returns:
            Dictionary representation of the result
        """
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        """
        Create a TaskResult from a dictionary.

        Args:
            data: Dictionary representation of the result

        Returns:
            A TaskResult instance
        """
        return cls(**data)

    def to_json(self) -> str:
        """
        Convert the TaskResult to JSON string.

        Returns:
            JSON representation of the result
        """
        data = self.to_dict()
        return json.dumps(data, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "TaskResult":
        """
        Create a TaskResult from JSON string.

        Args:
            json_str: JSON representation of the result

        Returns:
            A TaskResult instance
        """
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class Task:
    """
    Represents a task in the task queue.

    This is the core data structure used throughout the task queue library.
    A task contains all information needed for its execution, tracking, and
    result storage.

    Attributes:
        id: Unique identifier for the task (UUID)
        name: Human-readable name for the task
        payload: The task data/payload to be processed
        status: Current status of the task (TaskStatus)
        priority: Priority level (1 = highest, 10 = lowest)
        created_at: Timestamp when the task was created
        started_at: Timestamp when execution started (None if not started)
        completed_at: Timestamp when execution completed (None if not completed)
        result: TaskResult object with execution outcome (None if not completed)
        error: Deprecated: Use result.error instead
        retry_count: Number of retry attempts made
        max_retries: Maximum number of retry attempts allowed
        metadata: Optional metadata for custom tracking
    """

    id: UUID = field(default_factory=uuid4)
    name: str = "unnamed_task"
    payload: Optional[Any] = None
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 5
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[TaskResult] = None
    error: Optional[str] = None  # Deprecated: Use result.error
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        Validate task after initialization.

        Ensures priority is in valid range and timestamps are consistent.
        """
        if not 1 <= self.priority <= 10:
            raise ValueError(f"Priority must be between 1 and 10, got {self.priority}")

        # Ensure status enum
        if isinstance(self.status, str):
            self.status = TaskStatus.from_string(self.status)

    def __repr__(self) -> str:
        """
        Return a detailed string representation of the task.

        Useful for debugging and logging.
        """
        return (
            f"Task(id={str(self.id)[:8]}, name={self.name!r}, "
            f"status={self.status.value}, priority={self.priority}, "
            f"retries={self.retry_count}/{self.max_retries})"
        )

    def __str__(self) -> str:
        """
        Return a simple string representation of the task.

        Useful for user-friendly display.
        """
        return f"Task[{self.name}] ({self.status.value})"

    def __lt__(self, other: "Task") -> bool:
        """
        Compare tasks by priority for sorting.

        Lower priority numbers have higher priority (come first).

        Args:
            other: Another task to compare against

        Returns:
            True if this task has higher priority (lower number)
        """
        if not isinstance(other, Task):
            return NotImplemented
        return self.priority < other.priority

    @property
    def execution_time(self) -> Optional[float]:
        """
        Calculate the task execution duration in seconds.

        Returns:
            Execution time in seconds, or None if task hasn't completed
        """
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return delta.total_seconds()
        return None

    @property
    def can_be_retried(self) -> bool:
        """
        Check if the task can be retried.

        A task can be retried if it has failed and hasn't exhausted
        its max retry count.

        Returns:
            True if the task can be retried
        """
        return self.status.can_retry() and self.retry_count < self.max_retries

    def start(self) -> None:
        """
        Mark the task as started.

        Sets status to RUNNING and records the start time.
        Raises an error if already started or completed.
        """
        if self.status in (TaskStatus.RUNNING, TaskStatus.COMPLETED):
            raise ValueError(f"Cannot start task in status {self.status.value}")
        
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.utcnow()

    def complete(
        self,
        result: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Mark the task as completed successfully.

        Args:
            result: The result value from execution
            metadata: Optional metadata about the execution
        """
        if self.status not in (TaskStatus.RUNNING, TaskStatus.RETRYING):
            raise ValueError(f"Cannot complete task in status {self.status.value}")
        
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.result = TaskResult.from_success(result, metadata)
        # Clear deprecated error field
        self.error = None

    def fail(
        self,
        error: str,
        error_type: Optional[str] = None,
        traceback: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        can_retry: bool = True,
    ) -> None:
        """
        Mark the task as failed.

        Args:
            error: The error message
            error_type: Type of error
            traceback: Stack trace
            metadata: Optional metadata
            can_retry: Whether the task can be retried (defaults to checking max_retries)
        """
        if self.status not in (TaskStatus.RUNNING, TaskStatus.RETRYING):
            raise ValueError(f"Cannot fail task in status {self.status.value}")
        
        self.completed_at = datetime.utcnow()
        self.result = TaskResult.from_failure(error, error_type, traceback, metadata)
        
        # Set deprecated error field for backward compatibility
        self.error = error

        # Determine if we should retry or fail permanently
        should_retry = can_retry and self.can_be_retried
        
        if should_retry:
            self.status = TaskStatus.RETRYING
            self.retry_count += 1
        else:
            self.status = TaskStatus.FAILED

    def retry(self) -> None:
        """
        Prepare the task for retry.

        Resets the task status to RETRYING and increments retry count.
        """
        if not self.can_be_retried:
            raise ValueError(
                f"Task cannot be retried: {self.retry_count}/{self.max_retries} retries used"
            )
        
        self.status = TaskStatus.RETRYING
        self.retry_count += 1

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the task to a dictionary for serialization.

        Handles conversion of complex types like UUID, datetime, and enums.

        Returns:
            Dictionary representation of the task
        """
        data = asdict(self)
        
        # Convert complex types to serializable formats
        if "id" in data and data["id"]:
            data["id"] = str(data["id"])
        
        if "status" in data and isinstance(data["status"], TaskStatus):
            data["status"] = data["status"].value
        
        for dt_field in ["created_at", "started_at", "completed_at"]:
            if dt_field in data and data[dt_field]:
                data[dt_field] = data[dt_field].isoformat()
        
        # Handle result serialization
        if "result" in data and data["result"]:
            data["result"] = self.result.to_dict() if self.result else None
        
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """
        Create a Task from a dictionary.

        Handles conversion from serialized formats back to complex types.

        Args:
            data: Dictionary representation of the task

        Returns:
            A Task instance
        """
        # Make a copy to avoid modifying the input
        data_copy = data.copy()
        
        # Convert types back
        if "id" in data_copy and data_copy["id"]:
            data_copy["id"] = UUID(data_copy["id"])
        
        if "status" in data_copy and isinstance(data_copy["status"], str):
            data_copy["status"] = TaskStatus.from_string(data_copy["status"])
        
        for dt_field in ["created_at", "started_at", "completed_at"]:
            if dt_field in data_copy and data_copy[dt_field]:
                data_copy[dt_field] = datetime.fromisoformat(data_copy[dt_field])
        
        # Handle result deserialization
        if "result" in data_copy and data_copy["result"]:
            data_copy["result"] = TaskResult.from_dict(data_copy["result"])
        
        # Filter out None values that weren't in the original dict
        # (dataclass fields with defaults)
        return cls(**{k: v for k, v in data_copy.items() if k in cls.__dataclass_fields__})

    def to_json(self) -> str:
        """
        Convert the task to a JSON string.

        Returns:
            JSON representation of the task
        """
        data = self.to_dict()
        return json.dumps(data, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> "Task":
        """
        Create a Task from a JSON string.

        Args:
            json_str: JSON representation of the task

        Returns:
            A Task instance
        """
        data = json.loads(json_str)
        return cls.from_dict(data)

    def copy(self, **changes: Any) -> "Task":
        """
        Create a copy of the task with optional field changes.

        Args:
            **changes: Fields to override in the copy

        Returns:
            A new Task instance with specified changes

        Example:
            >>> task.retry_copy = task.copy(status=TaskStatus.RETRYING, retry_count=task.retry_count + 1)
        """
        data = self.to_dict()
        data.update(changes)
        return Task.from_dict(data)