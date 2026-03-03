"""
Unit tests for InMemoryBackend.

Tests cover:
- Basic enqueue/dequeue operations
- Priority queue semantics
- Thread safety with concurrent access
- All QueueBackend methods
- Edge cases and error handling
"""

import threading
import time
import unittest
from uuid import uuid4

from python_task_queue.backends.memory import InMemoryBackend
from python_task_queue.models import Task, TaskStatus
from python_task_queue.backends.base import TaskNotFoundError


class TestInMemoryBackendBasic(unittest.TestCase):
    """Basic functionality tests for InMemoryBackend."""

    def setUp(self):
        """Set up a new backend instance for each test."""
        self.backend = InMemoryBackend()

    def test_init(self):
        """Test backend initialization."""
        backend = InMemoryBackend()
        self.assertEqual(backend.size(), 0)
        self.assertIsNone(backend.peek())
        self.assertIsNone(backend.dequeue())

    def test_enqueue_single_task(self):
        """Test enqueuing a single task."""
        task = Task(name="test_task", priority=5)
        self.backend.enqueue(task)
        
        self.assertEqual(self.backend.size(), 1)
        peeked = self.backend.peek()
        self.assertIsNotNone(peeked)
        self.assertEqual(peeked.id, task.id)
        self.assertEqual(peeked.name, "test_task")

    def test_enqueue_multiple_tasks(self):
        """Test enqueuing multiple tasks."""
        task1 = Task(name="task1", priority=5)
        task2 = Task(name="task2", priority=3)
        task3 = Task(name="task3", priority=7)
        
        self.backend.enqueue(task1)
        self.backend.enqueue(task2)
        self.backend.enqueue(task3)
        
        self.assertEqual(self.backend.size(), 3)

    def test_dequeue_empty_queue(self):
        """Test dequeuing from an empty queue."""
        self.assertIsNone(self.backend.dequeue())

    def test_enqueue_duplicate_task(self):
        """Test that enqueuing the same task twice raises an error."""
        task = Task(name="duplicate_task")
        self.backend.enqueue(task)
        
        with self.assertRaises(ValueError) as context:
            self.backend.enqueue(task)
        
        self.assertIn("already in the queue", str(context.exception))

    def test_enqueue_invalid_status(self):
        """Test that enqueuing a task with invalid status raises an error."""
        task = Task(name="running_task", status=TaskStatus.RUNNING)
        
        with self.assertRaises(ValueError) as context:
            self.backend.enqueue(task)
        
        self.assertIn("Cannot enqueue task", str(context.exception))


class TestInMemoryBackendPriority(unittest.TestCase):
    """Priority queue semantics tests."""

    def setUp(self):
        """Set up a new backend instance for each test."""
        self.backend = InMemoryBackend()

    def test_priority_order_lowest_first(self):
        """Test that lower priority numbers are processed first."""
        task1 = Task(name="low_priority", priority=10)
        task2 = Task(name="high_priority", priority=1)
        task3 = Task(name="medium_priority", priority=5)
        
        # Enqueue in random order
        self.backend.enqueue(task3)
        self.backend.enqueue(task1)
        self.backend.enqueue(task2)
        
        # Should come out in priority order
        first = self.backend.dequeue()
        self.assertEqual(first.id, task2.id)  # priority 1
        
        second = self.backend.dequeue()
        self.assertEqual(second.id, task3.id)  # priority 5
        
        third = self.backend.dequeue()
        self.assertEqual(third.id, task1.id)  # priority 10

    def test_fifo_same_priority(self):
        """Test FIFO ordering for tasks with the same priority."""
        task1 = Task(name="first", priority=5)
        task2 = Task(name="second", priority=5)
        task3 = Task(name="third", priority=5)
        
        self.backend.enqueue(task1)
        self.backend.enqueue(task2)
        self.backend.enqueue(task3)
        
        first = self.backend.dequeue()
        self.assertEqual(first.id, task1.id)
        
        second = self.backend.dequeue()
        self.assertEqual(second.id, task2.id)
        
        third = self.backend.dequeue()
        self.assertEqual(third.id, task3.id)

    def test_peek_returns_highest_priority(self):
        """Test that peek returns the highest priority task."""
        task1 = Task(name="low", priority=10)
        task2 = Task(name="high", priority=1)
        
        self.backend.enqueue(task1)
        self.backend.enqueue(task2)
        
        peeked = self.backend.peek()
        self.assertIsNotNone(peeked)
        self.assertEqual(peeked.id, task2.id)
        self.assertEqual(self.backend.size(), 2)  # Not removed


class TestInMemoryAcknowledge(unittest.TestCase):
    """Tests for task acknowledgment."""

    def setUp(self):
        """Set up a new backend instance for each test."""
        self.backend = InMemoryBackend()

    def test_acknowledge_task(self):
        """Test acknowledging a task marks it as completed."""
        task = Task(name="task_to_complete")
        self.backend.enqueue(task)
        
        self.backend.acknowledge(task.id)
        
        updated = self.backend.get_task(task.id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, TaskStatus.COMPLETED)
        self.assertIsNotNone(updated.completed_at)

    def test_acknowledge_nonexistent_task(self):
        """Test acknowledging a non-existent task raises an error."""
        fake_id = uuid4()
        
        with self.assertRaises(TaskNotFoundError):
            self.backend.acknowledge(fake_id)

    def test_acknowledged_task_not_in_queue(self):
        """Test that acknowledged tasks are not returned by dequeue."""
        task = Task(name="task")
        self.backend.enqueue(task)
        
        self.backend.acknowledge(task.id)
        
        # Should not be returned as it's completed
        dequeued = self.backend.dequeue()
        self.assertIsNone(dequeued)


class TestInMemoryFail(unittest.TestCase):
    """Tests for task failure."""

    def setUp(self):
        """Set up a new backend instance for each test."""
        self.backend = InMemoryBackend()

    def test_fail_task_permanent(self):
        """Test failing a task marks it as failed when no retries left."""
        task = Task(name="fail_task", max_retries=0)
        self.backend.enqueue(task)
        
        self.backend.fail(task.id, "Task failed")
        
        updated = self.backend.get_task(task.id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, TaskStatus.FAILED)
        self.assertIsNotNone(updated.error)

    def test_fail_task_with_retry(self):
        """Test failing a task marks it for retry if retries available."""
        task = Task(name="retry_task", max_retries=3)
        self.backend.enqueue(task)
        
        self.backend.fail(task.id, "Temporary error")
        
        updated = self.backend.get_task(task.id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, TaskStatus.RETRYING)
        self.assertEqual(updated.retry_count, 1)

    def test_fail_nonexistent_task(self):
        """Test failing a non-existent task raises an error."""
        fake_id = uuid4()
        
        with self.assertRaises(TaskNotFoundError):
            self.backend.fail(fake_id, "Error")


class TestInMemoryGetTask(unittest.TestCase):
    """Tests for get_task method."""

    def setUp(self):
        """Set up a new backend instance for each test."""
        self.backend = InMemoryBackend()

    def test_get_existing_task(self):
        """Test retrieving an existing task."""
        task = Task(name="retrieve_me")
        self.backend.enqueue(task)
        
        retrieved = self.backend.get_task(task.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, task.id)
        self.assertEqual(retrieved.name, "retrieve_me")

    def test_get_nonexistent_task(self):
        """Test retrieving a non-existent task returns None."""
        fake_id = uuid4()
        retrieved = self.backend.get_task(fake_id)
        self.assertIsNone(retrieved)

    def test_get_task_by_status(self):
        """Test retrieving tasks in various statuses."""
        task_pending = Task(name="pending")
        task_completed = Task(name="completed")
        task_failed = Task(name="failed", max_retries=0)
        
        self.backend.enqueue(task_pending)
        self.backend.enqueue(task_completed)
        self.backend.enqueue(task_failed)
        
        # Acknowledge one
        self.backend.acknowledge(task_completed.id)
        
        # Fail one
        self.backend.fail(task_failed.id, "Error")
        
        # Should still be able to retrieve all
        self.assertIsNotNone(self.backend.get_task(task_pending.id))
        self.assertIsNotNone(self.backend.get_task(task_completed.id))
        self.assertIsNotNone(self.backend.get_task(task_failed.id))


class TestInMemoryListTasks(unittest.TestCase):
    """Tests for list_tasks method."""

    def setUp(self):
        """Set up a new backend instance for each test."""
        self.backend = InMemoryBackend()

    def test_list_all_tasks(self):
        """Test listing all tasks."""
        task1 = Task(name="task1")
        task2 = Task(name="task2")
        task3 = Task(name="task3")
        
        self.backend.enqueue(task1)
        self.backend.enqueue(task2)
        self.backend.enqueue(task3)
        
        tasks = self.backend.list_tasks()
        self.assertEqual(len(tasks), 3)
        task_ids = {t.id for t in tasks}
        self.assertIn(task1.id, task_ids)
        self.assertIn(task2.id, task_ids)
        self.assertIn(task3.id, task_ids)

    def test_list_tasks_by_status_pending(self):
        """Test listing tasks filtered by PENDING status."""
        task1 = Task(name="pending")
        task2 = Task(name="to_complete")
        
        self.backend.enqueue(task1)
        self.backend.enqueue(task2)
        
        # Complete one
        self.backend.acknowledge(task2.id)
        
        pending_tasks = self.backend.list_tasks(TaskStatus.PENDING)
        self.assertEqual(len(pending_tasks), 1)
        self.assertEqual(pending_tasks[0].id, task1.id)

    def test_list_tasks_by_status_completed(self):
        """Test listing tasks filtered by COMPLETED status."""
        task = Task(name="task")
        self.backend.enqueue(task)
        self.backend.acknowledge(task.id)
        
        completed = self.backend.list_tasks(TaskStatus.COMPLETED)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].id, task.id)

    def test_list_tasks_empty_queue(self):
        """Test listing tasks from an empty queue."""
        tasks = self.backend.list_tasks()
        self.assertEqual(len(tasks), 0)

    def test_list_tasks_no_matches(self):
        """Test listing tasks with a filter that matches no tasks."""
        task = Task(name="task")
        self.backend.enqueue(task)
        
        failed = self.backend.list_tasks(TaskStatus.FAILED)
        self.assertEqual(len(failed), 0)


class TestInMemoryThreadSafety(unittest.TestCase):
    """Thread safety tests."""

    def setUp(self):
        """Set up a new backend instance for each test."""
        self.backend = InMemoryBackend()

    def test_concurrent_enqueue(self):
        """Test enqueuing tasks from multiple threads."""
        num_tasks = 100
        num_threads = 10
        tasks_per_thread = num_tasks // num_threads
        
        exceptions = []
        
        def enqueue_tasks(thread_id):
            try:
                for i in range(tasks_per_thread):
                    task = Task(name=f"thread{thread_id}_task{i}")
                    self.backend.enqueue(task)
            except Exception as e:
                exceptions.append(e)
        
        threads = [
            threading.Thread(target=enqueue_tasks, args=(i,))
            for i in range(num_threads)
        ]
        
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # Check no exceptions occurred
        self.assertEqual(len(exceptions), 0, f"Exceptions: {exceptions}")
        
        # Check all tasks were enqueued
        self.assertEqual(self.backend.size(), num_tasks)

    def test_concurrent_dequeue(self):
        """Test dequeuing tasks from multiple threads."""
        num_tasks = 50
        num_threads = 5
        
        # Enqueue tasks
        for i in range(num_tasks):
            task = Task(name=f"task{i}")
            self.backend.enqueue(task)
        
        dequeued_tasks = []
        exceptions = []
        lock = threading.Lock()
        
        def dequeue_tasks():
            try:
                for _ in range(20):  # Try more times than tasks
                    task = self.backend.dequeue()
                    if task:
                        with lock:
                            dequeued_tasks.append(task)
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(e)
        
        threads = [
            threading.Thread(target=dequeue_tasks)
            for _ in range(num_threads)
        ]
        
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # Check no exceptions
        self.assertEqual(len(exceptions), 0, f"Exceptions: {exceptions}")
        
        # Check all tasks were dequeued exactly once
        self.assertEqual(len(dequeued_tasks), num_tasks)
        task_ids = [t.id for t in dequeued_tasks]
        self.assertEqual(len(task_ids), len(set(task_ids)))  # No duplicates

    def test_concurrent_enqueue_dequeue(self):
        """Test concurrent enqueue and dequeue operations."""
        num_operations = 100
        enqueued_count = [0]
        dequeued_count = [0]
        exceptions = []
        lock = threading.Lock()
        
        def producer():
            try:
                for i in range(num_operations // 2):
                    task = Task(name=f"producer_task{i}")
                    self.backend.enqueue(task)
                    with lock:
                        enqueued_count[0] += 1
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(e)
        
        def consumer():
            try:
                for _ in range(num_operations):
                    task = self.backend.dequeue()
                    if task:
                        with lock:
                            dequeued_count[0] += 1
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(e)
        
        threads = [
            threading.Thread(target=producer),
            threading.Thread(target=consumer),
        ]
        
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # Check no exceptions
        self.assertEqual(len(exceptions), 0, f"Exceptions: {exceptions}")
        
        # All enqueued tasks should have been dequeued
        self.assertEqual(enqueued_count[0], dequeued_count[0])

    def test_concurrent_get_task(self):
        """Test concurrent get_task operations."""
        task = Task(name="shared_task")
        self.backend.enqueue(task)
        
        results = []
        exceptions = []
        
        def get_task():
            try:
                for _ in range(100):
                    retrieved = self.backend.get_task(task.id)
                    if retrieved:
                        results.append(retrieved.id)
                    time.sleep(0.001)
            except Exception as e:
                exceptions.append(e)
        
        threads = [
            threading.Thread(target=get_task)
            for _ in range(5)
        ]
        
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # Check no exceptions
        self.assertEqual(len(exceptions), 0, f"Exceptions: {exceptions}")
        
        # All retrievals should have found the task
        self.assertEqual(len(results), 500)
        self.assertTrue(all(rid == task.id for rid in results))

    def test_concurrent_size(self):
        """Test concurrent size calls with modifications."""
        num_tasks = 50
        
        def add_tasks():
            for i in range(num_tasks):
                task = Task(name=f"task{i}")
                self.backend.enqueue(task)
                time.sleep(0.001)
        
        def check_size():
            for _ in range(100):
                size = self.backend.size()
                # Size should be between 0 and num_tasks
                self.assertGreaterEqual(size, 0)
                self.assertLessEqual(size, num_tasks)
                time.sleep(0.001)
        
        thread1 = threading.Thread(target=add_tasks)
        thread2 = threading.Thread(target=check_size)
        
        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()
        
        self.assertEqual(self.backend.size(), num_tasks)


class TestInMemoryClear(unittest.TestCase):
    """Tests for clear method."""

    def test_clear_empty_queue(self):
        """Test clearing an empty queue."""
        backend = InMemoryBackend()
        backend.clear()
        self.assertEqual(backend.size(), 0)

    def test_clear_with_tasks(self):
        """Test clearing a queue with tasks."""
        backend = InMemoryBackend()
        backend.enqueue(Task(name="task1"))
        backend.enqueue(Task(name="task2"))
        backend.enqueue(Task(name="task3"))
        
        backend.clear()
        
        self.assertEqual(backend.size(), 0)
        self.assertIsNone(backend.peek())
        self.assertIsNone(backend.get_task(uuid4()))  # Any task should be gone


class TestInMemoryEdgeCases(unittest.TestCase):
    """Edge case tests."""

    def setUp(self):
        """Set up a new backend instance for each test."""
        self.backend = InMemoryBackend()

    def test_enqueue_retrying_task(self):
        """Test that RETRYING tasks can be enqueued."""
        task = Task(name="retry_task", status=TaskStatus.RETRYING, retry_count=1)
        self.backend.enqueue(task)
        
        self.assertEqual(self.backend.size(), 1)
        retrieved = self.backend.get_task(task.id)
        self.assertEqual(retrieved.status, TaskStatus.RETRYING)

    def test_dequeue_skips_non_pending_tasks(self):
        """Test that dequeue skips tasks in non-pending states."""
        task1 = Task(name="task1", priority=1)
        task2 = Task(name="task2", priority=2)
        
        self.backend.enqueue(task1)
        self.backend.enqueue(task2)
        
        # Mark task1 as completed
        self.backend.acknowledge(task1.id)
        
        # Should get task2 instead
        dequeued = self.backend.dequeue()
        self.assertEqual(dequeued.id, task2.id)

    def test_peek_skips_non_pending_tasks(self):
        """Test that peek skips tasks in non-pending states."""
        task1 = Task(name="task1", priority=1)
        task2 = Task(name="task2", priority=2)
        
        self.backend.enqueue(task1)
        self.backend.enqueue(task2)
        
        # Mark task1 as completed
        self.backend.acknowledge(task1.id)
        
        # Should see task2 instead
        peeked = self.backend.peek()
        self.assertEqual(peeked.id, task2.id)

    def test_mixed_priorities_and_statuses(self):
        """Test complex scenario with mixed priorities and statuses."""
        task1 = Task(name="high", priority=1)
        task2 = Task(name="medium", priority=5)
        task3 = Task(name="low", priority=10)
        task4 = Task(name="high2", priority=1)
        
        self.backend.enqueue(task2)
        self.backend.enqueue(task4)
        self.backend.enqueue(task1)
        self.backend.enqueue(task3)
        
        # Complete one high priority task
        self.backend.acknowledge(task4.id)
        
        # Should get the other high priority task
        first = self.backend.dequeue()
        self.assertEqual(first.id, task1.id)
        
        # Then medium
        second = self.backend.dequeue()
        self.assertEqual(second.id, task2.id)
        
        # Then low
        third = self.backend.dequeue()
        self.assertEqual(third.id, task3.id)

    def test_size_counts_only_pending(self):
        """Test that size only counts pending tasks."""
        task1 = Task(name="pending")
        task2 = Task(name="completed")
        
        self.backend.enqueue(task1)
        self.backend.enqueue(task2)
        
        self.assertEqual(self.backend.size(), 2)
        
        self.backend.acknowledge(task2.id)
        
        self.assertEqual(self.backend.size(), 1)


if __name__ == "__main__":
    unittest.main()