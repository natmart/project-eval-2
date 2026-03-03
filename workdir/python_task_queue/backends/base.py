"""
Abstract base class for queue backend implementations.

This module defines the QueueBackend abstract base class that all backend
implementations must follow. It establishes the contract for task storage,
retrieval, and lifecycle management.
"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import List, Optional
from uuid import UUID

from python_task_queue.models import Task, TaskStatus


class QueueBackend(metaclass=ABCMeta):
    """
    Abstract base class for task queue backend implementations.

    This class defines the contract that all concrete backend implementations
    must fulfill. It provides methods for enqueuing, dequeuing, acknowledging,
    and managing tasks in the queue.

    Backend implementations must handle thread-safe operations if they will
    be used in multi-threaded environments.

    Examples:
        A concrete backend implementation must inherit from QueueBackend
        and implement all abstract methods:

        >>> class InMemoryBackend(QueueBackend):
        ...     def __init__(self):
        ...         self._tasks = []
        ...     def enqueue(self, task: Task) -> None:
        ...         self._tasks.append(task)
        ...     # ... implement other methods

        The abstract base class cannot be instantiated directly:

        >>> backend = QueueBackend()  # Raises TypeError
    """

    @abstractmethod
    def enqueue(self, task: Task) -> None:
        """
        Add a task to the queue.

        This method should add the task to the backend storage and make it
        available for processing. The task should maintain its position based
        on its priority (lower priority numbers should come first).

        Args:
            task: The task to add to the queue. The task should have a valid
                  UUID and be in a PENDING or RETRYING state.

        Raises:
            QueueBackendError: If the task cannot be enqueued due to backend
                               constraints (e.g., queue size limit exceeded)
            ValueError: If the task is in an invalid state or has invalid fields

        Notes:
            - Tasks with lower priority numbers should be processed first
            - The backend should handle task serialization if needed
            - This method should be thread-safe for concurrent access

        Examples:
            >>> backend = MyBackend()
            >>> task = Task(name="process_data", payload={"key": "value"})
            >>> backend.enqueue(task)
        """
        pass

    @abstractmethod
    def dequeue(self) -> Optional[Task]:
        """
        Remove and return the next task from the queue.

        This method should return the highest priority task that is in a
        PENDING state. The task's status should not be automatically changed;
        that is the responsibility of the caller.

        Returns:
            The next task to process, or None if the queue is empty.

        Notes:
            - Should return the highest priority task (lowest priority number)
            - Task status should remain PENDING; caller is responsible for
              updating it to RUNNING
            - This method should be thread-safe for concurrent access

        Examples:
            >>> backend = MyBackend()
            >>> task = backend.dequeue()
            >>> if task:
            ...     task.start()  # Mark as running
            ...     # Process the task
        """
        pass

    @abstractmethod
    def peek(self) -> Optional[Task]:
        """
        Return the next task from the queue without removing it.

        This method allows inspection of the next task to be processed
        without modifying the queue state.

        Returns:
            The next task that would be returned by dequeue(), or None if the
            queue is empty.

        Notes:
            - Does not modify the queue state
            - Should return the same task that dequeue() would return
            - This method should be thread-safe for concurrent access

        Examples:
            >>> backend = MyBackend()
            >>> task = backend.peek()
            >>> if task:
            ...     print(f"Next task: {task.name}")
        """
        pass

    @abstractmethod
    def size(self) -> int:
        """
        Return the number of tasks currently in the queue.

        This should count tasks that are eligible for processing (typically
        tasks in PENDING status). Completed or failed tasks may or may not be
        included, depending on the backend's design.

        Returns:
            The number of tasks in the queue.

        Notes:
            - This method should be efficient for frequent polling
            - The count should reflect only "pending" work, not historical tasks
            - This method should be thread-safe for concurrent access

        Examples:
            >>> backend = MyBackend()
            >>> print(f"Queue size: {backend.size()} tasks")
        """
        pass

    @abstractmethod
    def acknowledge(self, task_id: UUID) -> None:
        """
        Mark a task as successfully completed.

        This method should update the task's status to COMPLETED and store
        the completion timestamp. The task should be moved out of the active
        queue but may be retained for historical purposes.

        Args:
            task_id: The UUID of the task to acknowledge

        Raises:
            TaskNotFoundError: If no task with the given ID exists
            QueueBackendError: If the task cannot be acknowledged due to
                               backend constraints

        Notes:
            - Task status should be set to COMPLETED
            - completed_at timestamp should be set
            - Task may be moved to a separate "completed" collection
            - This method should be thread-safe for concurrent access

        Examples:
            >>> backend = MyBackend()
            >>> backend.acknowledge(task_id)
        """
        pass

    @abstractmethod
    def fail(self, task_id: UUID, error: str) -> None:
        """
        Mark a task as failed and record the error.

        This method should update the task's status to FAILED (or RETRYING if
        retries are still available) and record the error information. The
        task should be moved out of the active queue.

        Args:
            task_id: The UUID of the task to mark as failed
            error: A description of the error that caused the failure

        Raises:
            TaskNotFoundError: If no task with the given ID exists
            QueueBackendError: If the task cannot be failed due to backend
                               constraints

        Notes:
            - Check task.can_be_retried to determine if task should be RETRYING
            - If retrying, increment retry_count
            - Set completed_at timestamp
            - Record error information in task.result or task.error
            - This method should be thread-safe for concurrent access

        Examples:
            >>> backend = MyBackend()
            >>> backend.fail(task_id, "Connection timeout")
        """
        pass

    @abstractmethod
    def get_task(self, task_id: UUID) -> Optional[Task]:
        """
        Retrieve a task by its ID.

        This method should return the task with the specified ID regardless of
        its current status. It should not modify the queue state.

        Args:
            task_id: The UUID of the task to retrieve

        Returns:
            The task with the given ID, or None if it doesn't exist.

        Notes:
            - Should return tasks in any status (PENDING, RUNNING, COMPLETED, etc.)
            - Does not modify the queue state
            - This method should be thread-safe for concurrent access

        Examples:
            >>> backend = MyBackend()
            >>> task = backend.get_task(task_id)
            >>> if task:
            ...     print(f"Task status: {task.status}")
        """
        pass

    @abstractmethod
    def list_tasks(
        self, status: Optional[TaskStatus] = None
    ) -> List[Task]:
        """
        List tasks, optionally filtered by status.

        This method should return a list of tasks matching the specified criteria.
        The results may be empty if no tasks match.

        Args:
            status: Optional status filter. If None, return all tasks.

        Returns:
            A list of tasks matching the criteria. The list may be empty.

        Notes:
            - Should respect the queue order for PENDING tasks
            - May include tasks in any status
            - Results should be copies, not references to internal state
            - This method should be thread-safe for concurrent access

        Examples:
            >>> backend = MyBackend()
            >>> pending_tasks = backend.list_tasks(TaskStatus.PENDING)
            >>> all_tasks = backend.list_tasks()
        """
        pass


class QueueBackendError(Exception):
    """
    Base exception for queue backend errors.

    This exception should be raised by backend implementations when an
    operation fails due to backend-specific issues (not due to invalid
    input or missing tasks).
    """

    pass


class TaskNotFoundError(QueueBackendError):
    """
    Exception raised when a task cannot be found.

    This exception should be raised by backend implementations when
    attempting to operate on a task that doesn't exist.
    """

    def __init__(self, task_id: UUID, message: Optional[str] = None):
        """
        Initialize the exception.

        Args:
            task_id: The ID of the task that was not found
            message: Optional custom message
        """
        self.task_id = task_id
        if message is None:
            message = f"Task {task_id} not found"
        super().__init__(message)