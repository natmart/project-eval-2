"""
Dead Letter Queue (DLQ) implementation for the Python Task Queue Library.

This module provides a system for handling tasks that have exhausted their retry limits.
Failed tasks are moved to the DLQ where they can be inspected, replayed, or purged.

Key components:
- DeadLetterTask: Dataclass wrapping failed tasks with metadata
- DLQBackend: Abstract interface for DLQ storage backends
- MemoryDLQBackend: Thread-safe in-memory implementation
- DeadLetterQueue: Main interface for DLQ operations
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import json

from python_task_queue.models import Task, TaskResult


@dataclass
class DeadLetterTask:
    """
    Represents a task that has been moved to the dead letter queue.
    
    Wraps a failed task with metadata about why it failed, when it failed,
    and its retry history.
    
    Attributes:
        id: Unique identifier for the dead letter entry
        task: The original task that failed
        reason: Primary reason for failure (e.g., "max_retries_exceeded", "execution_failed")
        error_message: Error message from the last failure
        error_type: Type of error that caused failure
        failed_at: Timestamp when the task was moved to DLQ
        original_retry_count: Number of retry attempts before DLQ
        original_max_retries: Maximum retries configured for the task
        queue_name: Name of the queue the task was in (optional)
        metadata: Additional metadata about the failure
    """
    
    id: UUID = field(default_factory=uuid4)
    task: Task = None  # type: ignore
    reason: str = ""
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    failed_at: datetime = field(default_factory=datetime.utcnow)
    original_retry_count: int = 0
    original_max_retries: int = 0
    queue_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert complex types
        if data.get("task"):
            data["task"] = self.task.to_dict()
        data["id"] = str(self.id)
        data["failed_at"] = self.failed_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeadLetterTask":
        """Create from dictionary."""
        data_copy = data.copy()
        # Convert types back
        if data_copy.get("id"):
            data_copy["id"] = UUID(data_copy["id"])
        if data_copy.get("failed_at"):
            data_copy["failed_at"] = datetime.fromisoformat(data_copy["failed_at"])
        if data_copy.get("task"):
            data_copy["task"] = Task.from_dict(data_copy["task"])
        return cls(**{k: v for k, v in data_copy.items() if k in cls.__dataclass_fields__})


class DLQBackend:
    """
    Abstract interface for DLQ storage backends.
    
    Subclasses must implement all abstract methods to provide DLQ storage.
    """
    
    def add_task(self, dead_task: DeadLetterTask) -> None:
        """Add a task to the dead letter queue."""
        raise NotImplementedError
    
    def get_task(self, task_id: UUID) -> Optional[DeadLetterTask]:
        """Retrieve a task from the DLQ by ID."""
        raise NotImplementedError
    
    def get_all_tasks(self) -> List[DeadLetterTask]:
        """Get all tasks in the DLQ."""
        raise NotImplementedError
    
    def filter_tasks(
        self,
        reason: Optional[str] = None,
        queue_name: Optional[str] = None,
    ) -> List[DeadLetterTask]:
        """
        Filter tasks from the DLQ by reason and/or queue name.
        
        Args:
            reason: Filter by failure reason (optional)
            queue_name: Filter by queue name (optional)
            
        Returns:
            List of matching DeadLetterTask objects
        """
        raise NotImplementedError
    
    def remove_task(self, task_id: UUID) -> bool:
        """Remove a task from the DLQ. Returns True if task was found and removed."""
        raise NotImplementedError
    
    def purge_all(self) -> int:
        """Remove all tasks from the DLQ. Returns number of tasks purged."""
        raise NotImplementedError
    
    def purge_filtered(
        self,
        reason: Optional[str] = None,
        queue_name: Optional[str] = None,
    ) -> int:
        """Purge tasks matching filters. Returns number of tasks purged."""
        raise NotImplementedError
    
    def clear(self) -> None:
        """Clear all tasks from the DLQ."""
        raise NotImplementedError
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the DLQ."""
        raise NotImplementedError


class MemoryDLQBackend(DLQBackend):
    """
    Thread-safe in-memory implementation of DLQ backend.
    
    Stores all tasks in memory thread-safely using locks.
    Suitable for development, testing, and single-process deployments.
    """
    
    def __init__(self):
        """Initialize the in-memory DLQ."""
        self._tasks: Dict[UUID, DeadLetterTask] = {}
        self._lock = Lock()
    
    def add_task(self, dead_task: DeadLetterTask) -> None:
        """Add a task to the dead letter queue."""
        with self._lock:
            self._tasks[dead_task.id] = dead_task
    
    def get_task(self, task_id: UUID) -> Optional[DeadLetterTask]:
        """Retrieve a task from the DLQ by ID."""
        with self._lock:
            return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> List[DeadLetterTask]:
        """Get all tasks in the DLQ."""
        with self._lock:
            return list(self._tasks.values())
    
    def filter_tasks(
        self,
        reason: Optional[str] = None,
        queue_name: Optional[str] = None,
    ) -> List[DeadLetterTask]:
        """Filter tasks from the DLQ by reason and/or queue name."""
        with self._lock:
            tasks = list(self._tasks.values())
        
        # Apply filters
        if reason:
            tasks = [t for t in tasks if t.reason == reason]
        if queue_name:
            tasks = [t for t in tasks if t.queue_name == queue_name]
        
        return tasks
    
    def remove_task(self, task_id: UUID) -> bool:
        """Remove a task from the DLQ."""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False
    
    def purge_all(self) -> int:
        """Remove all tasks from the DLQ."""
        with self._lock:
            count = len(self._tasks)
            self._tasks.clear()
            return count
    
    def purge_filtered(
        self,
        reason: Optional[str] = None,
        queue_name: Optional[str] = None,
    ) -> int:
        """Purge tasks matching filters."""
        with self._lock:
            tasks_to_remove = [
                task_id for task_id, task in self._tasks.items()
                if (reason is None or task.reason == reason)
                and (queue_name is None or task.queue_name == queue_name)
            ]
            for task_id in tasks_to_remove:
                del self._tasks[task_id]
            return len(tasks_to_remove)
    
    def clear(self) -> None:
        """Clear all tasks from the DLQ."""
        with self._lock:
            self._tasks.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the DLQ."""
        with self._lock:
            total_tasks = len(self._tasks)
            
            # Count by reason
            reason_counts: Dict[str, int] = {}
            for task in self._tasks.values():
                reason_counts[task.reason] = reason_counts.get(task.reason, 0) + 1
            
            # Count by queue
            queue_counts: Dict[str, int] = {}
            for task in self._tasks.values():
                queue = task.queue_name or "default"
                queue_counts[queue] = queue_counts.get(queue, 0) + 1
            
            return {
                "total_tasks": total_tasks,
                "by_reason": reason_counts,
                "by_queue": queue_counts,
            }


class DeadLetterQueue:
    """
    Main interface for the Dead Letter Queue system.
    
    Provides a high-level API for managing failed tasks including:
    - Adding tasks to the DLQ when they exhaust retries
    - Inspecting failed tasks with filtering
    - Replaying tasks (re-enqueueing for retry)
    - Purging tasks from the DLQ
    - Getting statistics
    """
    
    def __init__(self, backend: Optional[DLQBackend] = None):
        """
        Initialize the Dead Letter Queue.
        
        Args:
            backend: Optional custom backend. Defaults to MemoryDLQBackend.
        """
        self.backend = backend or MemoryDLQBackend()
    
    def add(
        self,
        task: Task,
        reason: str = "exhausted_retries",
        queue_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DeadLetterTask:
        """
        Add a task to the dead letter queue.
        
        Args:
            task: The task to add
            reason: Reason for failure (default: "exhausted_retries")
            queue_name: Name of the queue the task was from
            metadata: Additional metadata about the failure
            
        Returns:
            The created DeadLetterTask
        """
        # Extract error info from task result if available
        error_message = None
        error_type = None
        if task.result:
            error_message = task.result.error
            error_type = task.result.error_type
        elif task.error:
            error_message = task.error
            error_type = type(task.error).__name__ if hasattr(task.error, '__class__') else str(type(task.error))
        
        dead_task = DeadLetterTask(
            task=task,
            reason=reason,
            error_message=error_message,
            error_type=error_type,
            original_retry_count=task.retry_count,
            original_max_retries=task.max_retries,
            queue_name=queue_name,
            metadata=metadata or {},
        )
        
        self.backend.add_task(dead_task)
        return dead_task
    
    def inspect(
        self,
        reason: Optional[str] = None,
        queue_name: Optional[str] = None,
    ) -> List[DeadLetterTask]:
        """
        Inspect tasks in the DLQ with optional filtering.
        
        Args:
            reason: Filter by failure reason (optional)
            queue_name: Filter by queue name (optional)
            
        Returns:
            List of DeadLetterTask objects
        """
        return self.backend.filter_tasks(reason=reason, queue_name=queue_name)
    
    def inspect_all(self) -> List[DeadLetterTask]:
        """Get all tasks in the DLQ."""
        return self.backend.get_all_tasks()
    
    def get(self, task_id: UUID) -> Optional[DeadLetterTask]:
        """Get a specific task from the DLQ by ID."""
        return self.backend.get_task(task_id)
    
    def replay(
        self,
        task_id: UUID,
        reset_retry_count: bool = False,
    ) -> Optional[Task]:
        """
        Replay a task from the DLQ (remove from DLQ and return for re-enqueuing).
        
        Args:
            task_id: UUID of the dead letter task to replay
            reset_retry_count: If True, reset retry count to 0; otherwise keep original
            
        Returns:
            The original task ready to be re-enqueued, or None if not found
        """
        dead_task = self.backend.remove_task(task_id)
        if not dead_task:
            return None
        
        task = dead_task.task
        
        # Optionally reset retry count
        if reset_retry_count:
            task.retry_count = 0
            # Create a clean copy
            task = task.copy(retry_count=0)
        
        return task
    
    def replay_filtered(
        self,
        reason: Optional[str] = None,
        queue_name: Optional[str] = None,
        reset_retry_count: bool = False,
    ) -> List[Task]:
        """
        Replay multiple tasks matching filters.
        
        Args:
            reason: Filter by failure reason (optional)
            queue_name: Filter by queue name (optional)
            reset_retry_count: If True, reset retry counts to 0
            
        Returns:
            List of tasks ready to be re-enqueued
        """
        dead_tasks = self.backend.filter_tasks(reason=reason, queue_name=queue_name)
        
        tasks: List[Task] = []
        for dead_task in dead_tasks:
            self.backend.remove_task(dead_task.id)
            task = dead_task.task
            if reset_retry_count:
                task = task.copy(retry_count=0)
            tasks.append(task)
        
        return tasks
    
    def purge(self, task_id: UUID) -> bool:
        """
        Purge a specific task from the DLQ.
        
        Args:
            task_id: UUID of the task to purge
            
        Returns:
            True if task was found and purged
        """
        return self.backend.remove_task(task_id)
    
    def purge_all(self) -> int:
        """
        Purge all tasks from the DLQ.
        
        Returns:
            Number of tasks purged
        """
        return self.backend.purge_all()
    
    def purge_filtered(
        self,
        reason: Optional[str] = None,
        queue_name: Optional[str] = None,
    ) -> int:
        """
        Purge tasks matching filters from the DLQ.
        
        Args:
            reason: Filter by failure reason (optional)
            queue_name: Filter by queue name (optional)
            
        Returns:
            Number of tasks purged
        """
        return self.backend.purge_filtered(reason=reason, queue_name=queue_name)
    
    def clear(self) -> None:
        """Clear all tasks from the DLQ."""
        self.backend.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the DLQ."""
        return self.backend.get_stats()
    
    def count(self) -> int:
        """Get the total number of tasks in the DLQ."""
        return self.get_stats().get("total_tasks", 0)