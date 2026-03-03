"""
Dead Letter Queue (DLQ) integration tests.

Tests complete DLQ integration with worker and queue:
- Task failure → DLQ enqueue
- DLQ inspection and filtering
- DLQ replay
- DLQ purge
"""

import threading
import time
import unittest
from uuid import UUID
from typing import Any

from python_task_queue.backends import InMemoryBackend
from python_task_queue.models import Task, TaskStatus
from python_task_queue.worker import Worker
from python_task_queue.registry import TaskRegistry
from python_task_queue.retry import simple_retry_policy
from python_task_queue.dlq import DeadLetterQueue, DeadLetterTask


def always_fail_task(payload: Any = None) -> Any:
    """Task that always fails."""
    raise ValueError("This task always fails")


def conditional_fail_task(payload: Any = None) -> Any:
    """Task that fails based on payload."""
    if payload and payload.get("fail", False):
        raise RuntimeError("Conditional failure")
    return "success"


class DLQIntegrationTest(unittest.TestCase):
    """Integration tests for DLQ functionality."""

    def setUp(self):
        """Set up fresh components for each test."""
        self.backend = InMemoryBackend()
        self.registry = TaskRegistry()
        self.dlq = DeadLetterQueue()
        self.retry_policy = simple_retry_policy(max_attempts=2, max_retries=1)

    def test_dlq_task_enqueue_after_retries_exhausted(self) -> None:
        """Test that tasks are added to DLQ after exhausting retries."""
        # Register failing task
        self.registry.register("always_fail", always_fail_task)

        # Create worker with DLQ integration
        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            retry_policy=self.retry_policy,
            poll_interval=0.01,
        )
        worker.dlq = self.dlq  # Attach DLQ

        # Enqueue failing task
        task = Task(name="always_fail", max_retries=1)
        self.backend.enqueue(task)

        # Start worker
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        # Wait for processing (initial + 1 retry = 2 attempts)
        time.sleep(1.0)

        # Stop worker
        worker.stop()
        worker.join(timeout=2)

        # Verify DLQ has the task
        self.assertEqual(self.dlq.size(), 1, "Task should be in DLQ")

        dlq_task = self.dlq.list()[0]
        self.assertEqual(dlq_task.task_name, "always_fail")
        self.assertIsNotNone(dlq_task.error)
        self.assertEqual(dlq_task.retry_count, 1)
        self.assertEqual(dlq_task.max_retries, 1)

    def test_dlq_inspection(self) -> None:
        """Test DLQ inspection and listing."""
        dlq = DeadLetterQueue()

        # Add tasks to DLQ
        task1 = Task(name="task1", payload={"data": 1})
        task2 = Task(name="task2", payload={"data": 2})
        task3 = Task(name="task1", payload={"data": 3})  # Same name as task1

        dlq.add(task1, "Error 1", "ValueError")
        dlq.add(task2, "Error 2", "RuntimeError")
        dlq.add(task3, "Error 3", "ValueError")

        # List all tasks
        all_tasks = dlq.list()
        self.assertEqual(len(all_tasks), 3)

        # Filter by task name
        task1_tasks = dlq.list(task_name="task1")
        self.assertEqual(len(task1_tasks), 2)

        # Filter by reason/error type
        value_error_tasks = dlq.list(reason="ValueError")
        self.assertEqual(len(value_error_tasks), 2)

        runtime_tasks = dlq.list(reason="RuntimeError")
        self.assertEqual(len(runtime_tasks), 1)

    def test_dlq_get_by_id(self) -> None:
        """Test getting a specific DLQ task by ID."""
        dlq = DeadLetterQueue()

        task = Task(name="test", payload="test")
        dlq_id = dlq.add(task, "Test error", "ValueError")

        # Get by ID
        dlq_task = dlq.get(dlq_id)

        self.assertIsNotNone(dlq_task)
        self.assertEqual(dlq_task.id, dlq_id)
        self.assertEqual(dlq_task.task_name, "test")

        # Non-existent ID
        self.assertIsNone(dlq.get(UUID('00000000-0000-0000-0000-000000000000')))

    def test_dlq_replay(self) -> None:
        """Test replaying a task from DLQ."""
        dlq = DeadLetterQueue()

        # Add task to DLQ
        original_task = Task(name="test", payload="test", max_retries=3)
        dlq_id = dlq.add(original_task, "Original error", "ValueError")

        # Verify it's in DLQ
        self.assertEqual(dlq.size(), 1)

        # Replay task
        new_task = dlq.replay(dlq_id)

        self.assertIsNotNone(new_task)
        self.assertIsInstance(new_task, Task)
        self.assertEqual(new_task.name, "test")
        self.assertEqual(new_task.payload, "test")
        self.assertEqual(new_task.retry_count, 0)  # Reset
        self.assertEqual(new_task.max_retries, 3)
        self.assertNotEqual(new_task.id, original_task.id)  # New task ID

        # Verify DLQ is empty
        self.assertEqual(dlq.size(), 0)

    def test_dlq_purge(self) -> None:
        """Test purging tasks from DLQ."""
        dlq = DeadLetterQueue()

        # Add tasks
        task1 = Task(name="task1", payload="data1")
        task2 = Task(name="task2", payload="data2")

        dlq_id1 = dlq.add(task1, "Error 1")
        dlq_id2 = dlq.add(task2, "Error 2")

        self.assertEqual(dlq.size(), 2)

        # Purge one task
        purged = dlq.purge(dlq_id1)
        self.assertTrue(purged)
        self.assertEqual(dlq.size(), 1)

        # Verify correct task remains
        remaining = dlq.list()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].task_name, "task2")

        # Purging non-existent task returns False
        purged = dlq.purge(dlq_id1)
        self.assertFalse(purged)

    def test_dlq_clear(self) -> None:
        """Test clearing all tasks from DLQ."""
        dlq = DeadLetterQueue()

        # Add multiple tasks
        for i in range(5):
            task = Task(name=f"task{i}", payload=i)
            dlq.add(task, f"Error {i}")

        self.assertEqual(dlq.size(), 5)

        # Clear all
        dlq.clear()

        self.assertEqual(dlq.size(), 0)
        self.assertEqual(len(dlq.list()), 0)

    def test_dlq_statistics(self) -> None:
        """Test DLQ statistics."""
        dlq = DeadLetterQueue()

        # Add tasks with different types
        for i in range(3):
            task = Task(name="task_a", payload=i)
            dlq.add(task, f"Error", "ValueError")

        for i in range(2):
            task = Task(name="task_b", payload=i)
            dlq.add(task, f"Error", "RuntimeError")

        stats = dlq.statistics()

        self.assertEqual(stats["total_tasks"], 5)
        self.assertEqual(stats["by_task_name"]["task_a"], 3)
        self.assertEqual(stats["by_task_name"]["task_b"], 2)
        self.assertEqual(stats["by_error_type"]["ValueError"], 3)
        self.assertEqual(stats["by_error_type"]["RuntimeError"], 2)

    def test_dlq_successful_tasks_not_sent_to_dlq(self) -> None:
        """Test that successful tasks are not sent to DLQ."""
        self.registry.register("success", lambda x: x * 2)

        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            retry_policy=self.retry_policy,
            poll_interval=0.01,
        )
        worker.dlq = self.dlq

        # Enqueue successful task
        task = Task(name="success", payload=5)
        self.backend.enqueue(task)

        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        time.sleep(0.5)

        worker.stop()
        worker.join(timeout=2)

        # Verify DLQ is empty
        self.assertEqual(self.dlq.size(), 0)
        self.assertEqual(self.backend.size(), 0)

    def test_dlq_with_different_error_types(self) -> None:
        """Test DLQ with different error types."""
        def value_error_task():
            raise ValueError("Value error")

        def runtime_error_task():
            raise RuntimeError("Runtime error")

        self.registry.register("value_error", value_error_task)
        self.registry.register("runtime_error", runtime_error_task)

        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            retry_policy=simple_retry_policy(max_attempts=1, max_retries=0),
            poll_interval=0.01,
        )
        worker.dlq = self.dlq

        # Enqueue tasks with different error types
        self.backend.enqueue(Task(name="value_error"))
        self.backend.enqueue(Task(name="runtime_error"))

        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        time.sleep(0.5)

        worker.stop()
        worker.join(timeout=2)

        # Verify both tasks are in DLQ
        self.assertEqual(self.dlq.size(), 2)

        # Verify error types are preserved
        tasks = self.dlq.list()
        error_types = {t.error_type for t in tasks}
        self.assertEqual(error_types, {"ValueError", "RuntimeError"})


if __name__ == "__main__":
    unittest.main()