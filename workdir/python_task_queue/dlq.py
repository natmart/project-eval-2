"""
Dead Letter Queue (DLQ) implementation for the Python Task Queue Library.

Provides a mechanism to store and manage tasks that have exceeded their retry limit.
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


logger = logging.getLogger(__name__)


@dataclass
class DeadLetterTask:
    """
    Represents a task in the dead letter queue.

    Attributes:
        id: Unique identifier for the DLQ entry
        task_id: ID of the original failed task
        task_name: Name of the original task
        payload: Original task payload
        error: Error message from the last failure
        error_type: Type of error
        retry_count: Number of retry attempts made
        max_retries: Maximum retries configured
        enqueued_at: When the task was added to DLQ
        metadata: Additional metadata
    """
    id: UUID = field(default_factory=uuid4)
    task_id: UUID = field(default_factory=uuid4)
    task_name: str = ""
    payload: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    enqueued_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DeadLetterQueue:
    """
    Dead Letter Queue for storing tasks that have exceeded their retry limit.

    Provides operations to add, inspect, list, replay, and purge failed tasks.
    """

    def __init__(self):
        """Initialize the DLQ."""
        self._tasks: Dict[UUID, DeadLetterTask] = {}
        self._lock = threading.RLock()

    def add(self, task: 'Task', error: str, error_type: Optional[str] = None) -> UUID:
        """
        Add a failed task to the DLQ.

        Args:
            task: The failed task
            error: Error message
            error_type: Type of error

        Returns:
            ID of the DLQ entry
        """
        with self._lock:
            dlq_task = DeadLetterTask(
                task_id=task.id,
                task_name=task.name,
                payload=task.payload,
                error=error,
                error_type=error_type,
                retry_count=task.retry_count,
                max_retries=task.max_retries,
            )

            self._tasks[dlq_task.id] = dlq_task
            logger.info(f"Added task {task.id} to DLQ: {error}")

            return dlq_task.id

    def get(self, dlq_id: UUID) -> Optional[DeadLetterTask]:
        """
        Get a DLQ task by ID.

        Args:
            dlq_id: DLQ task ID

        Returns:
            DeadLetterTask or None if not found
        """
        with self._lock:
            return self._tasks.get(dlq_id)

    def list(self, reason: Optional[str] = None, task_name: Optional[str] = None) -> List[DeadLetterTask]:
        """
        List DLQ tasks, optionally filtered.

        Args:
            reason: Filter by error type/reason
            task_name: Filter by task name

        Returns:
            List of DeadLetterTask objects
        """
        with self._lock:
            tasks = list(self._tasks.values())

            if task_name:
                tasks = [t for t in tasks if t.task_name == task_name]

            if reason:
                tasks = [t for t in tasks if reason.lower() in (t.error_type or "").lower()]

            return tasks

    def size(self) -> int:
        """Return the number of tasks in the DLQ."""
        with self._lock:
            return len(self._tasks)

    def replay(self, dlq_id: UUID) -> Optional['Task']:
        """
        Replay a task from the DLQ (remove from DLQ and return as new Task).

        Args:
            dlq_id: DLQ task ID

        Returns:
            Task ready for re-enqueueing or None if not found
        """
        from python_task_queue.models import Task

        with self._lock:
            dlq_task = self._tasks.pop(dlq_id, None)

            if not dlq_task:
                return None

            # Create new task with reset state
            new_task = Task(
                name=dlq_task.task_name,
                payload=dlq_task.payload,
                retry_count=0,
                max_retries=dlq_task.max_retries,
            )

            logger.info(f"Replayed task {dlq_task.task_id} from DLQ as new task {new_task.id}")

            return new_task

    def purge(self, dlq_id: UUID) -> bool:
        """
        Remove a task from the DLQ.

        Args:
            dlq_id: DLQ task ID

        Returns:
            True if removed, False if not found
        """
        with self._lock:
            if dlq_id in self._tasks:
                del self._tasks[dlq_id]
                logger.info(f"Purged DLQ entry {dlq_id}")
                return True
            return False

    def clear(self) -> None:
        """Clear all tasks from the DLQ."""
        with self._lock:
            count = len(self._tasks)
            self._tasks.clear()
            logger.info(f"Cleared {count} tasks from DLQ")

    def statistics(self) -> Dict[str, Any]:
        """
        Get DLQ statistics.

        Returns:
            Dictionary with DLQ stats
        """
        with self._lock:
            return {
                "total_tasks": len(self._tasks),
                "by_task_name": {name: len([t for t in self._tasks.values() if t.task_name == name])
                                 for name in set(t.task_name for t in self._tasks.values())},
                "by_error_type": {err_type: len([t for t in self._tasks.values() if t.error_type == err_type])
                                  for err_type in set(t.error_type for t in self._tasks.values() if t.error_type)},
            }