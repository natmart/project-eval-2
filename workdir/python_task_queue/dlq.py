"""
Dead Letter Queue system for the Python Task Queue Library.

This module provides functionality for handling tasks that exhaust all retry attempts:
- Separate queue for permanently failed tasks
- Inspect operations to view failed tasks
- Replay operations to re-enqueue tasks to main queue
- Purge operations to remove tasks from DLQ
- Configurable DLQ backend
- Task metadata preservation including original retry info
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Type
from uuid import UUID, uuid4

from python_task_queue.models import Task, TaskResult, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class DeadLetterTask:
    """
    Represents a task that has exhausted all retry attempts.

    This wraps a failed task with additional metadata about why it was
    moved to the dead letter queue and when.

    Attributes:
        id: Unique identifier for the dead letter entry
        task: The original task that failed
        original_queue: Name of the queue the task came from
        reason: Reason for being moved to DLQ
        error_message: The error message that caused final failure
        error_type: Type of error
        failed_at: Timestamp when the task failed
        retry_count: Number of retry attempts before giving up
        metadata: Additional metadata about the failure
    """

    id: UUID = field(default_factory=uuid4)
    task: Task = None
    original_queue: str = "default"
    reason: str = "max_retries_exceeded"
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    failed_at: datetime = field(default_factory=datetime.utcnow)
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        """Return string representation of dead letter task."""
        return (
            f"DeadLetterTask(id={str(self.id)[:8]}, task_id={str(self.task.id)[:8]}, "
            f"reason={self.reason}, failed_at={self.failed_at.isoformat()})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        from dataclasses import asdict

        data = asdict(self)
        data["id"] = str(data["id"])
        if self.task:
            data["task"] = self.task.to_dict()
        if "failed_at" in data and data["failed_at"]:
            data["failed_at"] = data["failed_at"].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeadLetterTask":
        """Create from dictionary."""
        from dataclasses import asdict

        data_copy = data.copy()
        if "id" in data_copy:
            data_copy["id"] = UUID(data_copy["id"])
        if "task" in data_copy and data_copy["task"]:
            data_copy["task"] = Task.from_dict(data_copy["task"])
        if "failed_at" in data_copy and isinstance(data_copy["failed_at"], str):
            data_copy["failed_at"] = datetime.fromisoformat(data_copy["failed_at"])
        return cls(**{k: v for k, v in data_copy.items() if k in cls.__dataclass_fields__})


class DLQBackend(ABC):
    """
    Abstract base class for Dead Letter Queue backends.

    All DLQ backend implementations must inherit from this class and
    implement the required methods.
    """

    @abstractmethod
    def add(self, dead_letter_task: DeadLetterTask) -> None:
        """
        Add a dead letter task to the DLQ.

        Args:
            dead_letter_task: The dead letter task to add
        """
        pass

    @abstractmethod
    def get(self, dead_letter_id: UUID) -> Optional[DeadLetterTask]:
        """
        Get a dead letter task by ID.

        Args:
            dead_letter_id: The ID of the dead letter task

        Returns:
            The dead letter task, or None if not found
        """
        pass

    @abstractmethod
    def list_all(self, limit: Optional[int] = None) -> List[DeadLetterTask]:
        """
        List all dead letter tasks.

        Args:
            limit: Maximum number of tasks to return

        Returns:
            List of dead letter tasks, ordered by most recent first
        """
        pass

    @abstractmethod
    def remove(self, dead_letter_id: UUID) -> bool:
        """
        Remove a dead letter task from the DLQ.

        Args:
            dead_letter_id: The ID of the dead letter task to remove

        Returns:
            True if the task was removed, False if not found
        """
        pass

    @abstractmethod
    def purge(self) -> int:
        """
        Remove all dead letter tasks from the DLQ.

        Returns:
            Number of tasks removed
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """
        Get the number of tasks in the DLQ.

        Returns:
            Number of dead letter tasks
        """
        pass

    @abstractmethod
    def filter_by_reason(self, reason: str) -> List[DeadLetterTask]:
        """
        Filter dead letter tasks by reason.

        Args:
            reason: The reason to filter by

        Returns:
            List of dead letter tasks matching the reason
        """
        pass

    @abstractmethod
    def filter_by_queue(self, queue_name: str) -> List[DeadLetterTask]:
        """
        Filter dead letter tasks by original queue.

        Args:
            queue_name: The original queue name

        Returns:
            List of dead letter tasks from that queue
        """
        pass


class MemoryDLQBackend(DLQBackend):
    """
    In-memory implementation of Dead Letter Queue backend.

    Stores dead letter tasks in a Python dictionary. This is suitable for
    development and testing but tasks are lost when the process exits.
    """

    def __init__(self) -> None:
        """Initialize the in-memory DLQ backend."""
        self._tasks: Dict[UUID, DeadLetterTask] = {}
        self._lock = None
        import threading

        self._lock = threading.Lock()
        logger.debug("MemoryDLQBackend initialized")

    def add(self, dead_letter_task: DeadLetterTask) -> None:
        """Add a dead letter task to the in-memory DLQ."""
        if dead_letter_task.id is None:
            dead_letter_task.id = uuid4()

        with self._lock:
            self._tasks[dead_letter_task.id] = dead_letter_task
            logger.info(
                f"Added dead letter task {dead_letter_task.id} "
                f"(task_id: {dead_letter_task.task.id})"
            )

    def get(self, dead_letter_id: UUID) -> Optional[DeadLetterTask]:
        """Get a dead letter task by ID."""
        with self._lock:
            return self._tasks.get(dead_letter_id)

    def list_all(self, limit: Optional[int] = None) -> List[DeadLetterTask]:
        """
        List all dead letter tasks.

        Tasks are returned ordered by most recent failed_at timestamp.
        """
        with self._lock:
            tasks = list(self._tasks.values())
            # Sort by failed_at descending (most recent first)
            tasks.sort(key=lambda t: t.failed_at, reverse=True)
            if limit is not None:
                tasks = tasks[:limit]
            return tasks

    def remove(self, dead_letter_id: UUID) -> bool:
        """Remove a dead letter task from the DLQ."""
        with self._lock:
            if dead_letter_id in self._tasks:
                del self._tasks[dead_letter_id]
                logger.info(f"Removed dead letter task {dead_letter_id}")
                return True
            return False

    def purge(self) -> int:
        """Remove all dead letter tasks from the DLQ."""
        with self._lock:
            count = len(self._tasks)
            self._tasks.clear()
            if count > 0:
                logger.info(f"Purged {count} dead letter tasks")
            return count

    def count(self) -> int:
        """Get the number of tasks in the DLQ."""
        with self._lock:
            return len(self._tasks)

    def filter_by_reason(self, reason: str) -> List[DeadLetterTask]:
        """Filter dead letter tasks by reason."""
        with self._lock:
            tasks = [
                t for t in self._tasks.values() if t.reason == reason
            ]
            tasks.sort(key=lambda t: t.failed_at, reverse=True)
            return tasks

    def filter_by_queue(self, queue_name: str) -> List[DeadLetterTask]:
        """Filter dead letter tasks by original queue."""
        with self._lock:
            tasks = [
                t for t in self._tasks.values()
                if t.original_queue == queue_name
            ]
            tasks.sort(key=lambda t: t.failed_at, reverse=True)
            return tasks


class DeadLetterQueue:
    """
    Main interface for the Dead Letter Queue system.

    This class provides a high-level API for managing failed tasks that
    have exhausted all retry attempts. It supports operations like inspect,
    replay, and purge.

    Examples:
        >>> dlq = DeadLetterQueue(backend=MemoryDLQBackend())
        >>> failed_task = Task(name="test_task", payload={"data": 123})
        >>> failed_task.fail(error="Max retries exceeded")
        >>> dlq.add_failed_task(
        ...     task=failed_task,
        ...     original_queue="main",
        ...     reason="max_retries_exceeded"
        ... )
        >>> # Inspect
        >>> tasks = dlq.inspect()
        >>> # Replay
        >>> task = dlq.replay(replay_id=tasks[0].id)
        >>> # Purge
        >>> dlq.purge_all()
    """

    def __init__(self, backend: Optional[DLQBackend] = None):
        """
        Initialize the Dead Letter Queue.

        Args:
            backend: The DLQ backend to use. If None, uses MemoryDLQBackend.
        """
        self.backend = backend or MemoryDLQBackend()
        logger.info(f"DeadLetterQueue initialized with {type(self.backend).__name__}")

    def add_failed_task(
        self,
        task: Task,
        original_queue: str = "default",
        reason: str = "max_retries_exceeded",
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DeadLetterTask:
        """
        Add a failed task to the dead letter queue.

        Args:
            task: The task that failed (should have status FAILED)
            original_queue: Name of the queue the task came from
            reason: Reason for being moved to DLQ
            error_message: The error message that caused failure
            error_type: Type of error
            metadata: Additional metadata about the failure

        Returns:
            The created DeadLetterTask

        Raises:
            ValueError: If task status is not FAILED
        """
        if task.status != TaskStatus.FAILED:
            raise ValueError(
                f"Cannot add task with status {task.status.value} to DLQ. "
                "Only FAILED tasks can be added."
            )

        # Extract error info from task result if available
        if error_message is None and task.result:
            error_message = task.result.error
        if error_type is None and task.result:
            error_type = task.result.error_type

        dead_letter_task = DeadLetterTask(
            task=task,
            original_queue=original_queue,
            reason=reason,
            error_message=error_message,
            error_type=error_type,
            retry_count=task.retry_count,
            metadata=metadata or {},
        )

        self.backend.add(dead_letter_task)
        return dead_letter_task

    def inspect(
        self,
        reason: Optional[str] = None,
        queue_name: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[DeadLetterTask]:
        """
        Inspect dead letter tasks.

        Args:
            reason: Filter by reason if provided
            queue_name: Filter by original queue if provided
            limit: Maximum number of tasks to return

        Returns:
            List of dead letter tasks matching filters, most recent first
        """
        if reason is not None and queue_name is not None:
            # Filter by both
            tasks = [
                t for t in self.backend.list_all()
                if t.reason == reason and t.original_queue == queue_name
            ]
        elif reason is not None:
            tasks = self.backend.filter_by_reason(reason)
        elif queue_name is not None:
            tasks = self.backend.filter_by_queue(queue_name)
        else:
            tasks = self.backend.list_all()

        if limit is not None:
            tasks = tasks[:limit]

        return tasks

    def get_task(self, dead_letter_id: UUID) -> Optional[DeadLetterTask]:
        """
        Get a specific dead letter task by ID.

        Args:
            dead_letter_id: The ID of the dead letter task

        Returns:
            The dead letter task, or None if not found
        """
        return self.backend.get(dead_letter_id)

    def replay(
        self,
        replay_id: UUID,
        reset_retries: bool = False,
        new_max_retries: Optional[int] = None,
        new_priority: Optional[int] = None,
    ) -> Optional[Task]:
        """
        Replay a dead letter task by returning it to the main queue.

        This removes the task from the DLQ and returns a fresh Task instance
        that can be re-enqueued in the main queue.

        Args:
            replay_id: The ID of the dead letter task to replay
            reset_retries: If True, reset retry count to 0
            new_max_retries: Set a new max_retries value (None = keep original)
            new_priority: Set a new priority (None = keep original)

        Returns:
            A new Task instance ready to be re-enqueued, or None if not found

        Raises:
            ValueError: If the dead letter task is not found
        """
        dead_letter_task = self.backend.get(replay_id)

        if dead_letter_task is None:
            raise ValueError(f"Dead letter task with id {replay_id} not found")

        original_task = dead_letter_task.task

        # Create a fresh copy of the task for replay
        changes = {
            "status": TaskStatus.PENDING,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }

        if reset_retries:
            changes["retry_count"] = 0

        if new_max_retries is not None:
            changes["max_retries"] = new_max_retries
        elif original_task.retry_count >= original_task.max_retries:
            # If we exhausted retries and didn't specify new max, increase it
            changes["max_retries"] = original_task.max_retries + 3

        if new_priority is not None:
            changes["priority"] = new_priority

        # Add metadata about replay
        replay_metadata = original_task.metadata.copy()
        replay_metadata["dlq_replayed_at"] = datetime.utcnow().isoformat()
        replay_metadata["dlq_original_failed_at"] = dead_letter_task.failed_at.isoformat()
        replay_metadata["dlq_reason"] = dead_letter_task.reason
        replay_metadata["dlq_original_retry_count"] = dead_letter_task.retry_count
        replay_metadata["dlq_original_max_retries"] = original_task.max_retries

        changes["metadata"] = replay_metadata

        replayed_task = original_task.copy(**changes)

        # Remove from DLQ
        self.backend.remove(replay_id)

        logger.info(
            f"Replayed dead letter task {replay_id} "
            f"as new task {replayed_task.id}"
        )

        return replayed_task

    def replay_all(
        self,
        reset_retries: bool = True,
        new_max_retries: Optional[int] = None,
    ) -> List[Task]:
        """
        Replay all dead letter tasks.

        Args:
            reset_retries: If True, reset retry count to 0 for all tasks
            new_max_retries: Set a new max_retries value (None = keep original or increase)

        Returns:
            List of replayed tasks
        """
        tasks = self.backend.list_all()
        replayed_tasks = []

        for dead_letter_task in tasks:
            try:
                replayed_task = self.replay(
                    replay_id=dead_letter_task.id,
                    reset_retries=reset_retries,
                    new_max_retries=new_max_retries,
                )
                replayed_tasks.append(replayed_task)
            except Exception as e:
                logger.error(
                    f"Failed to replay dead letter task {dead_letter_task.id}: {e}"
                )

        return replayed_tasks

    def replay_filtered(
        self,
        reason: Optional[str] = None,
        queue_name: Optional[str] = None,
        reset_retries: bool = True,
        new_max_retries: Optional[int] = None,
    ) -> List[Task]:
        """
        Replay dead letter tasks that match filters.

        Args:
            reason: Filter by reason if provided
            queue_name: Filter by original queue if provided
            reset_retries: If True, reset retry count to 0
            new_max_retries: Set a new max_retries value

        Returns:
            List of replayed tasks
        """
        tasks = self.inspect(reason=reason, queue_name=queue_name)
        replayed_tasks = []

        for dead_letter_task in tasks:
            try:
                replayed_task = self.replay(
                    replay_id=dead_letter_task.id,
                    reset_retries=reset_retries,
                    new_max_retries=new_max_retries,
                )
                replayed_tasks.append(replayed_task)
            except Exception as e:
                logger.error(
                    f"Failed to replay dead letter task {dead_letter_task.id}: {e}"
                )

        return replayed_tasks

    def purge(self, dead_letter_id: UUID) -> bool:
        """
        Remove a specific dead letter task from the DLQ.

        Args:
            dead_letter_id: The ID of the dead letter task to remove

        Returns:
            True if removed, False if not found
        """
        return self.backend.remove(dead_letter_id)

    def purge_all(self) -> int:
        """
        Remove all dead letter tasks from the DLQ.

        Returns:
            Number of tasks removed
        """
        count = self.backend.purge()
        return count

    def purge_filtered(
        self,
        reason: Optional[str] = None,
        queue_name: Optional[str] = None,
    ) -> int:
        """
        Remove dead letter tasks that match filters.

        Args:
            reason: Filter by reason if provided
            queue_name: Filter by original queue if provided

        Returns:
            Number of tasks removed
        """
        tasks = self.inspect(reason=reason, queue_name=queue_name)
        count = 0

        for dead_letter_task in tasks:
            if self.backend.remove(dead_letter_task.id):
                count += 1

        return count

    def count(self) -> int:
        """
        Get the total number of dead letter tasks.

        Returns:
            Number of tasks in DLQ
        """
        return self.backend.count()

    def count_by_reason(self, reason: str) -> int:
        """
        Count dead letter tasks by reason.

        Args:
            reason: The reason to count

        Returns:
            Number of tasks with that reason
        """
        tasks = self.backend.filter_by_reason(reason)
        return len(tasks)

    def count_by_queue(self, queue_name: str) -> int:
        """
        Count dead letter tasks by original queue.

        Args:
            queue_name: The original queue name

        Returns:
            Number of tasks from that queue
        """
        tasks = self.backend.filter_by_queue(queue_name)
        return len(tasks)

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the dead letter queue.

        Returns:
            Dictionary containing statistics
        """
        all_tasks = self.backend.list_all()

        stats = {
            "total_count": len(all_tasks),
            "queues": {},
            "reasons": {},
            "errors": {},
        }

        for task in all_tasks:
            # Count by queue
            queue = task.original_queue
            stats["queues"][queue] = stats["queues"].get(queue, 0) + 1

            # Count by reason
            reason = task.reason
            stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1

            # Count by error type
            error_type = task.error_type or "unknown"
            stats["errors"][error_type] = stats["errors"].get(error_type, 0) + 1

        return stats

    def __repr__(self) -> str:
        """Return string representation."""
        return f"DeadLetterQueue(backend={type(self.backend).__name__}, count={self.count()})"


# Convenience functions for common operations

def create_dlq(backend_type: str = "memory", **backend_kwargs) -> DeadLetterQueue:
    """
    Create a DeadLetterQueue with the specified backend.

    Args:
        backend_type: Type of backend ("memory")
        **backend_kwargs: Additional arguments for backend initialization

    Returns:
        Configured DeadLetterQueue

    Raises:
        ValueError: If backend_type is not supported
    """
    if backend_type == "memory":
        backend = MemoryDLQBackend(**backend_kwargs)
    else:
        raise ValueError(f"Unsupported DLQ backend type: {backend_type}")

    return DeadLetterQueue(backend=backend)