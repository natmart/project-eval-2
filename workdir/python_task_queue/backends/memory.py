"""
In-memory queue backend implementation.

This module provides a thread-safe in-memory implementation of QueueBackend
using collections.deque and threading.Lock. Perfect for testing, development,
and single-process applications.

Features:
- Thread-safe operations with Lock
- Priority queue support (lower numbers = higher priority)
- All QueueBackend methods implemented
- Suitable for concurrent worker access
"""

from __future__ import annotations

import heapq
from collections import deque
from threading import Lock
from typing import Dict, List, Optional
from uuid import UUID

from python_task_queue.backends.base import QueueBackend, TaskNotFoundError
from python_task_queue.models import Task, TaskStatus


class InMemoryBackend(QueueBackend):
    """
    Thread-safe in-memory implementation of QueueBackend.

    This backend stores all tasks in memory using a priority queue for pending
    tasks and dictionaries for task lookup. It uses thread.Lock to ensure
    thread-safe operations, making it suitable for concurrent worker access.

    The backend implements priority queue semantics where tasks with lower
    priority numbers are dequeued first (priority 1 = highest, priority 10 = lowest).

    Example:
        >>> backend = InMemoryBackend()
        >>> task1 = Task(name="high_priority", priority=1)
        >>> task2 = Task(name="low_priority", priority=10)
        >>> backend.enqueue(task1)
        >>> backend.enqueue(task2)
        >>> next_task = backend.dequeue()
        >>> assert next_task == task1  # Higher priority task comes first

    Note:
        This backend stores all tasks in memory and does not persist data.
        All data is lost when the backend is destroyed or the process exits.
    """

    def __init__(self) -> None:
        """
        Initialize the in-memory backend.

        Creates internal data structures for task storage:
        - _priority_queue: List-based priority queue for pending tasks
        - _tasks_by_id: Dictionary for fast task lookup by ID
        - _lock: Threading lock for thread-safe operations
        """
        # Priority queue stores tuples of (priority, created_at, task_id)
        # created_at ensures FIFO ordering for tasks with same priority
        self._priority_queue: List[tuple[int, float, UUID]] = []
        
        # Dictionary storing all tasks by ID
        self._tasks_by_id: Dict[UUID, Task] = {}
        
        # Lock for thread-safe operations
        self._lock = Lock()
        
        # Counter for ordering tasks with same priority
        self._counter = 0

    def enqueue(self, task: Task) -> None:
        """
        Add a task to the queue.

        The task is added to the priority queue based on its priority.
        Tasks with lower priority numbers are processed first. Tasks with
        the same priority are processed in FIFO order (by creation time).

        Args:
            task: The task to add to the queue

        Raises:
            ValueError: If task is already in the queue or has invalid state

        Example:
            >>> backend = InMemoryBackend()
            >>> task = Task(name="process_data", priority=3)
            >>> backend.enqueue(task)
            >>> assert backend.size() == 1
        """
        with self._lock:
            # Check if task is already in the queue
            if task.id in self._tasks_by_id:
                raise ValueError(f"Task {task.id} is already in the queue")
            
            # Only accept PENDING or RETRYING tasks
            if task.status not in (TaskStatus.PENDING, TaskStatus.RETRYING):
                raise ValueError(
                    f"Cannot enqueue task with status {task.status.value}. "
                    "Only PENDING and RETRYING tasks can be enqueued."
                )
            
            # Store the task
            self._tasks_by_id[task.id] = task
            
            # Add to priority queue
            # Use priority, counter, and task_id for ordering
            # Counter ensures FIFO for same priority
            self._counter += 1
            heapq.heappush(
                self._priority_queue,
                (task.priority, self._counter, task.id)
            )

    def dequeue(self) -> Optional[Task]:
        """
        Remove and return the next task from the queue.

        Returns the highest priority task (lowest priority number) that is
        in a PENDING state. If the highest priority task is in another state
        (e.g., RUNNING), it is skipped and the next task is returned.

        The task's status is not changed; the caller is responsible for
        updating it to RUNNING.

        Returns:
            The next task to process, or None if the queue is empty

        Example:
            >>> backend = InMemoryBackend()
            >>> backend.enqueue(Task(name="task1", priority=3))
            >>> backend.enqueue(Task(name="task2", priority=1))
            >>> task = backend.dequeue()
            >>> assert task.name == "task2"  # Higher priority comes first
        """
        with self._lock:
            # Find the next eligible task
            while self._priority_queue:
                priority, counter, task_id = heapq.heappop(self._priority_queue)
                
                # Get the task from storage
                task = self._tasks_by_id.get(task_id)
                
                if task is None:
                    # Task was removed, skip it
                    continue
                
                # Only return PENDING tasks
                if task.status == TaskStatus.PENDING:
                    return task
                
                # Task is not pending, skip it
                # Note: it might be RUNNING, RETRYING, etc.
                continue
            
            return None

    def peek(self) -> Optional[Task]:
        """
        Return the next task from the queue without removing it.

        Inspects the next task that would be returned by dequeue() without
        modifying the queue state.

        Returns:
            The next task that would be returned by dequeue(), or None if queue is empty

        Example:
            >>> backend = InMemoryBackend()
            >>> backend.enqueue(Task(name="task1", priority=5))
            >>> task = backend.peek()
            >>> assert task is not None
            >>> assert backend.size() == 1  # Task not removed
        """
        with self._lock:
            # Look at the top of the priority queue without popping
            while self._priority_queue:
                priority, counter, task_id = self._priority_queue[0]
                task = self._tasks_by_id.get(task_id)
                
                if task is None:
                    # Task was removed, remove it from queue
                    heapq.heappop(self._priority_queue)
                    continue
                
                if task.status == TaskStatus.PENDING:
                    return task
                
                # Task not pending, remove it from queue and continue
                heapq.heappop(self._priority_queue)
            
            return None

    def size(self) -> int:
        """
        Return the number of PENDING tasks in the queue.

        Counts only tasks that are in PENDING status and eligible for processing.

        Returns:
            The number of pending tasks in the queue

        Example:
            >>> backend = InMemoryBackend()
            >>> backend.enqueue(Task(name="task1", priority=5))
            >>> backend.enqueue(Task(name="task2", priority=3))
            >>> assert backend.size() == 2
        """
        with self._lock:
            # Count PENDING tasks
            return sum(
                1 for task in self._tasks_by_id.values()
                if task.status == TaskStatus.PENDING
            )

    def acknowledge(self, task_id: UUID) -> None:
        """
        Mark a task as successfully completed.

        Updates the task's status to COMPLETED and stores the completion timestamp.

        Args:
            task_id: The UUID of the task to acknowledge

        Raises:
            TaskNotFoundError: If no task with the given ID exists

        Example:
            >>> backend = InMemoryBackend()
            >>> task = Task(name="task1")
            >>> backend.enqueue(task)
            >>> backend.acknowledge(task.id)
            >>> updated_task = backend.get_task(task.id)
            >>> assert updated_task.status == TaskStatus.COMPLETED
        """
        with self._lock:
            task = self._tasks_by_id.get(task_id)
            
            if task is None:
                raise TaskNotFoundError(task_id)
            
            # Mark as completed
            task.complete()

    def fail(self, task_id: UUID, error: str) -> None:
        """
        Mark a task as failed and record the error.

        Updates the task's status to FAILED (or RETRYING if retries are still
        available) and records the error information.

        Args:
            task_id: The UUID of the task to mark as failed
            error: A description of the error that caused the failure

        Raises:
            TaskNotFoundError: If no task with the given ID exists

        Example:
            >>> backend = InMemoryBackend()
            >>> task = Task(name="task1", max_retries=0)
            >>> backend.enqueue(task)
            >>> backend.fail(task.id, "Processing failed")
            >>> updated_task = backend.get_task(task.id)
            >>> assert updated_task.status == TaskStatus.FAILED
        """
        with self._lock:
            task = self._tasks_by_id.get(task_id)
            
            if task is None:
                raise TaskNotFoundError(task_id)
            
            # Mark as failed (will automatically handle retry logic)
            task.fail(error=error)

    def get_task(self, task_id: UUID) -> Optional[Task]:
        """
        Retrieve a task by its ID.

        Returns the task with the specified ID regardless of its current status.

        Args:
            task_id: The UUID of the task to retrieve

        Returns:
            The task with the given ID, or None if it doesn't exist

        Example:
            >>> backend = InMemoryBackend()
            >>> task = Task(name="task1")
            >>> backend.enqueue(task)
            >>> retrieved = backend.get_task(task.id)
            >>> assert retrieved.id == task.id
        """
        with self._lock:
            return self._tasks_by_id.get(task_id)

    def list_tasks(
        self, status: Optional[TaskStatus] = None
    ) -> List[Task]:
        """
        List tasks, optionally filtered by status.

        Returns a list of tasks matching the specified criteria. The list
        contains copies of the stored tasks to prevent external modification.

        Args:
            status: Optional status filter. If None, returns all tasks.

        Returns:
            A list of tasks matching the criteria

        Example:
            >>> backend = InMemoryBackend()
            >>> backend.enqueue(Task(name="task1"))
            >>> backend.enqueue(Task(name="task2"))
            >>> tasks = backend.list_tasks(TaskStatus.PENDING)
            >>> assert len(tasks) == 2
        """
        with self._lock:
            if status is None:
                # Return all tasks as copies
                return list(self._tasks_by_id.values())
            else:
                # Return filtered tasks as copies
                return [
                    task for task in self._tasks_by_id.values()
                    if task.status == status
                ]

    def clear(self) -> None:
        """
        Remove all tasks from the queue.

        This is a convenience method for testing and cleanup. It removes
        all tasks regardless of their status.

        Example:
            >>> backend = InMemoryBackend()
            >>> backend.enqueue(Task(name="task1"))
            >>> backend.enqueue(Task(name="task2"))
            >>> backend.clear()
            >>> assert backend.size() == 0
        """
        with self._lock:
            self._priority_queue.clear()
            self._tasks_by_id.clear()
            self._counter = 0