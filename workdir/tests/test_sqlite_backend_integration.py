"""
SQLite backend integration tests.

Tests complete integration with SQLite backend including:
- Complete task lifecycle with SQLite
- Persistence across worker sessions
- Thread-safe concurrent operations
"""

import os
import tempfile
import threading
import time
import unittest
from typing import Any

from python_task_queue.backends import SQLiteBackend
from python_task_queue.models import Task, TaskStatus
from python_task_queue.worker import Worker
from python_task_queue.registry import TaskRegistry
from python_task_queue.retry import simple_retry_policy


def simple_task(payload: Any = None) -> Any:
    """Simple task handler."""
    if payload is None:
        payload = 0
    return payload * 2


def failing_task(payload: Any = None) -> Any:
    """Failing task handler."""
    raise ValueError("Intentional failure")


class SQLiteBackendIntegrationTest(unittest.TestCase):
    """Integration tests for SQLite backend."""

    def setUp(self):
        """Set up fresh SQLite database for each test."""
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(self.db_fd)
        self.backend = SQLiteBackend(self.db_path)

    def tearDown(self):
        """Clean up database file."""
        os.unlink(self.db_path)

    def test_sqlite_complete_lifecycle(self) -> None:
        """Test complete task lifecycle with SQLite backend."""
        registry = TaskRegistry()
        registry.register("simple", simple_task)

        worker = Worker(
            backend=self.backend,
            registry=registry,
            poll_interval=0.01,
        )

        # Enqueue task
        task = Task(name="simple", payload=5)
        self.backend.enqueue(task)

        self.assertEqual(self.backend.size(), 1)

        # Start worker
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        # Wait for processing
        time.sleep(0.5)

        # Stop worker
        worker.stop()
        worker.join(timeout=2)

        # Verify task processed
        self.assertEqual(self.backend.size(), 0)
        stats = worker.get_stats()
        self.assertEqual(stats.tasks_processed, 1)
        self.assertEqual(stats.tasks_succeeded, 1)

    def test_sqlite_persistence_across_sessions(self) -> None:
        """Test that tasks persist across worker sessions."""
        # Enqueue task in first session
        task = Task(name="simple", payload=10)
        self.backend.enqueue(task)

        self.assertEqual(self.backend.size(), 1)

        # Create new backend instance (simulating new process/session)
        new_backend = SQLiteBackend(self.db_path)
        self.assertEqual(new_backend.size(), 1, "Task should persist")

        # Process task in new session
        registry = TaskRegistry()
        registry.register("simple", simple_task)

        worker = Worker(
            backend=new_backend,
            registry=registry,
            poll_interval=0.01,
        )

        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        time.sleep(0.5)

        worker.stop()
        worker.join(timeout=2)

        self.assertEqual(new_backend.size(), 0)

    def test_sqlite_priority_ordering(self) -> None:
        """Test priority ordering with SQLite backend."""
        # Enqueue tasks in different order
        task1 = Task(name="test", payload=1, priority=5)
        task2 = Task(name="test", payload=2, priority=1)
        task3 = Task(name="test", payload=3, priority=3)

        self.backend.enqueue(task1)
        self.backend.enqueue(task2)
        self.backend.enqueue(task3)

        # Verify priority order
        tasks = self.backend.list()
        self.assertEqual(len(tasks), 3)
        self.assertEqual(tasks[0].id, task2.id)  # priority 1
        self.assertEqual(tasks[1].id, task3.id)  # priority 3
        self.assertEqual(tasks[2].id, task1.id)  # priority 5

        # Peek should return highest priority
        peeked = self.backend.peek()
        self.assertEqual(peeked.id, task2.id)

    def test_sqlite_concurrent_operations(self) -> None:
        """Test thread-safe concurrent operations with SQLite."""
        errors = []
        lock = threading.Lock()

        def enqueue_task(i):
            try:
                task = Task(name="test", payload=i, priority=(i % 5) + 1)
                self.backend.enqueue(task)
            except Exception as e:
                with lock:
                    errors.append(e)

        # Enqueue tasks concurrently
        threads = []
        for i in range(20):
            t = threading.Thread(target=enqueue_task, args=(i,))
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=2)

        # Verify no errors
        self.assertEqual(len(errors), 0, f"errors occurred: {errors}")

        # Verify count
        self.assertEqual(self.backend.size(), 20)

    def test_sqlite_retry_integration(self) -> None:
        """Test retry behavior with SQLite backend."""
        registry = TaskRegistry()
        registry.register("failing", failing_task)

        worker = Worker(
            backend=self.backend,
            registry=registry,
            retry_policy=simple_retry_policy(max_attempts=3, max_retries=2, delay_ms=10),
            poll_interval=0.01,
        )

        # Enqueue task that will fail and retry
        task = Task(name="failing", max_retries=2)
        self.backend.enqueue(task)

        # Start worker
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        # Wait for processing (initial + retries)
        time.sleep(1.0)

        # Stop worker
        worker.stop()
        worker.join(timeout=2)

        # Verify task processed
        self.assertEqual(self.backend.size(), 0)

        stats = worker.get_stats()
        self.assertEqual(stats.tasks_processed, 3)  # initial + 2 retries
        self.assertEqual(stats.tasks_failed, 1)
        self.assertEqual(stats.tasks_retried, 2)

    def test_sqlite_task_update(self) -> None:
        """Test task update operations with SQLite."""
        task = Task(name="test", payload="original")
        self.backend.enqueue(task)

        # Update task (simulate retry)
        updated = self.backend.update_task(
            str(task.id),
            status=TaskStatus.RETRYING,
            retry_count=1,
            error="Test error"
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, TaskStatus.RETRYING)
        self.assertEqual(updated.retry_count, 1)
        self.assertEqual(updated.error, "Test error")

    def test_sqlite_task_deletion(self) -> None:
        """Test task deletion with SQLite."""
        task = Task(name="test", payload="test")
        self.backend.enqueue(task)

        self.assertEqual(self.backend.size(), 1)

        # Delete task
        deleted = self.backend.delete_task(str(task.id))

        self.assertTrue(deleted)
        self.assertEqual(self.backend.size(), 0)

        # Deleting non-existent task should return False
        deleted = self.backend.delete_task(str(task.id))
        self.assertFalse(deleted)

    def test_sqlite_get_task(self) -> None:
        """Test getting task by ID with SQLite."""
        task = Task(name="test", payload="test")
        self.backend.enqueue(task)

        # Get task
        retrieved = self.backend.get_task(str(task.id))

        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, task.id)
        self.assertEqual(retrieved.name, task.name)
        self.assertEqual(retrieved.payload, task.payload)

    def test_sqlite_clear(self) -> None:
        """Test clearing all tasks with SQLite."""
        for i in range(10):
            task = Task(name="test", payload=i)
            self.backend.enqueue(task)

        self.assertEqual(self.backend.size(), 10)

        self.backend.clear()

        self.assertEqual(self.backend.size(), 0)

    def test_sqlite_multiple_workers(self) -> None:
        """Test SQLite backend with multiple workers."""
        registry = TaskRegistry()
        registry.register("simple", simple_task)

        # Enqueue tasks
        for i in range(10):
            task = Task(name="simple", payload=i)
            self.backend.enqueue(task)

        # Create multiple workers
        workers = []
        worker_threads = []

        for _ in range(3):
            worker = Worker(
                backend=self.backend,
                registry=registry,
                poll_interval=0.01,
            )
            workers.append(worker)

            t = threading.Thread(target=worker.start)
            t.start()
            worker_threads.append(t)

        # Wait for processing
        time.sleep(2.0)

        # Stop workers
        for worker in workers:
            worker.stop()

        for t in worker_threads:
            t.join(timeout=2)

        # Verify all tasks processed
        self.assertEqual(self.backend.size(), 0)

        total_processed = sum(w.get_stats().tasks_processed for w in workers)
        self.assertEqual(total_processed, 10)


if __name__ == "__main__":
    unittest.main()