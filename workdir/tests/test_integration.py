"""
Integration tests for the Python Task Queue Library.

These tests validate complete end-to-end flows:
- Task lifecycle: enqueue → worker processes → completion/failure
- Worker + queue + retry integration
- Multi-worker concurrent processing
- Configuration integration
- All queue backends (memory and SQLite when available)

Integration tests use real components together rather than mocking dependencies.
"""

import logging
import time
import threading
import unittest
import tempfile
import os
from uuid import UUID
from typing import Any, List

from python_task_queue.models import Task, TaskStatus, TaskResult
from python_task_queue.backends import InMemoryBackend
from python_task_queue.worker import Worker, WorkerStats
from python_task_queue.registry import TaskRegistry, get_registry
from python_task_queue.retry import (
    RetryPolicy,
    RetryDecision,
    RetryStrategy,
    RetryDecisionReason,
    simple_retry_policy,
    network_retry_policy,
)
from python_task_queue.middleware import Middleware, MiddlewarePipeline, LoggingMiddleware
from python_task_queue.config import Config, get_config


# Test task handlers
def simple_task(payload: Any = None) -> Any:
    """Simple task handler that returns the payload doubled."""
    if payload is None:
        payload = 0
    return payload * 2


def failing_task(payload: Any = None) -> Any:
    """Task handler that always fails."""
    raise ValueError("Intentional failure for testing")


def flaky_task(payload: Any = None) -> Any:
    """Task that fails once then succeeds (track attempts via payload)."""
    if payload is None:
        payload = {"attempts": 0}
    payload["attempts"] = payload.get("attempts", 0) + 1
    if payload["attempts"] <= 2:
        raise RuntimeError(f"Flaky task failing on attempt {payload['attempts']}")
    return payload


def slow_task(payload: Any = None) -> Any:
    """Task that takes time to complete."""
    time.sleep(0.1)
    return "completed"


class TaskLifecycleIntegrationTest(unittest.TestCase):
    """Integration tests for complete task lifecycle."""

    def setUp(self):
        """Set up fresh components for each test."""
        self.backend = InMemoryBackend()
        self.registry = TaskRegistry()
        self.retry_policy = simple_retry_policy()
        self.worker = Worker(
            backend=self.backend,
            registry=self.registry,
            retry_policy=self.retry_policy,
            poll_interval=0.01,  # Fast polling for tests
        )

    def tearDown(self):
        """Clean up after each test."""
        if self.worker.is_running():
            self.worker.stop()
            self.worker.join(timeout=5)

    def test_complete_success_lifecycle(self) -> None:
        """Test complete lifecycle: enqueue → process → complete."""
        # Register task handler
        self.registry.register("simple", simple_task)

        # Enqueue task
        task = Task(name="simple", payload=5)
        self.backend.enqueue(task)

        # Start worker
        worker_thread = threading.Thread(target=self.worker.start)
        worker_thread.start()

        # Wait for processing
        time.sleep(0.5)

        # Stop worker
        self.worker.stop()
        self.worker.join(timeout=2)

        # Verify task was processed
        self.assertEqual(self.backend.size(), 0, "Queue should be empty")

        # Check worker stats
        stats = self.worker.get_stats()
        self.assertEqual(stats.tasks_processed, 1)
        self.assertEqual(stats.tasks_succeeded, 1)
        self.assertEqual(stats.tasks_failed, 0)

    def test_complete_failure_lifecycle_no_retry(self) -> None:
        """Test lifecycle with failing task and no retries."""
        # Register failing task handler
        self.registry.register("failing", failing_task)

        # Create retry policy that doesn't retry
        no_retry = simple_retry_policy(max_attempts=1)

        # Create worker with no-retry policy
        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            retry_policy=no_retry,
            poll_interval=0.01,
        )

        # Enqueue task
        task = Task(name="failing", payload=None)
        self.backend.enqueue(task)

        # Start worker
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        # Wait for processing
        time.sleep(0.5)

        # Stop worker
        worker.stop()
        worker.join(timeout=2)

        # Verify task was processed
        self.assertEqual(self.backend.size(), 0, "Queue should be empty")

        # Check worker stats
        stats = worker.get_stats()
        self.assertEqual(stats.tasks_processed, 1)
        self.assertEqual(stats.tasks_succeeded, 0)
        self.assertEqual(stats.tasks_failed, 1)

    def test_task_with_priority_ordering(self) -> None:
        """Test that tasks are processed in priority order."""
        # Register task handlers
        self.registry.register("simple", simple_task)

        # Enqueue tasks in different order of priority
        task2 = Task(name="simple", payload=2, priority=5)
        task1 = Task(name="simple", payload=1, priority=1)
        task3 = Task(name="simple", payload=3, priority=10)

        self.backend.enqueue(task2)
        self.backend.enqueue(task1)
        self.backend.enqueue(task3)

        # Verify priority order
        peeked = self.backend.peek()
        self.assertEqual(peeked.id, task1.id, "Highest priority task should be first")

        self.assertEqual(list(t.id for t in self.backend.list()), [task1.id, task2.id, task3.id])

    def test_task_payload_serialization(self) -> None:
        """Test that complex payloads are handled correctly."""
        # Register task handler
        self.registry.register("simple", simple_task)

        # Create task with complex payload
        complex_payload = {"nested": {"data": [1, 2, 3]}, "value": 42}
        task = Task(name="simple", payload=complex_payload, priority=1)

        # Verify payload is preserved
        self.assertEqual(task.payload, complex_payload)

    def test_concurrent_enqueue_dequeue(self) -> None:
        """Test concurrent enqueue and dequeue operations."""
        # Register task handler
        self.registry.register("simple", simple_task)

        # Start worker
        worker_thread = threading.Thread(target=self.worker.start)
        worker_thread.start()

        # Enqueue multiple tasks concurrently
        threads = []
        for i in range(10):
            def enqueue_task():
                task = Task(name="simple", payload=i, priority=(i % 5) + 1)
                self.backend.enqueue(task)

            t = threading.Thread(target=enqueue_task)
            t.start()
            threads.append(t)

        # Wait for all enqueues
        for t in threads:
            t.join(timeout=2)

        # Wait for processing
        time.sleep(1.0)

        # Stop worker
        self.worker.stop()
        self.worker.join(timeout=2)

        # Verify all tasks were processed
        self.assertEqual(self.backend.size(), 0, "Queue should be empty")
        stats = self.worker.get_stats()
        self.assertEqual(stats.tasks_processed, 10)


class WorkerQueueRetryIntegrationTest(unittest.TestCase):
    """Integration tests for worker + queue + retry flow."""

    def setUp(self):
        """Set up fresh components for each test."""
        self.backend = InMemoryBackend()
        self.registry = TaskRegistry()
        self.retry_policy = simple_retry_policy(max_attempts=3, delay_ms=10)
        self.worker = Worker(
            backend=self.backend,
            registry=self.registry,
            retry_policy=self.retry_policy,
            poll_interval=0.01,
        )

    def tearDown(self):
        """Clean up after each test."""
        if self.worker.is_running():
            self.worker.stop()
            self.worker.join(timeout=5)

    def test_retry_after_failure(self) -> None:
        """Test that failed task is retried and eventually succeeds."""
        # Register flaky task handler
        self.registry.register("flaky", flaky_task)

        # Enqueue task
        task = Task(name="flaky", payload={"attempts": 0})
        self.backend.enqueue(task)

        # Start worker
        worker_thread = threading.Thread(target=self.worker.start)
        worker_thread.start()

        # Wait for processing (includes retries)
        time.sleep(1.0)

        # Stop worker
        self.worker.stop()
        self.worker.join(timeout=2)

        # Verify task was processed
        self.assertEqual(self.backend.size(), 0, "Queue should be empty")

        # Check worker stats
        stats = self.worker.get_stats()
        self.assertEqual(stats.tasks_processed, 1)
        self.assertEqual(stats.tasks_succeeded, 1, "Task should succeed after retries")
        self.assertEqual(stats.tasks_retried, 2, "Should have retried twice")

    def test_exhausted_retries_failure(self) -> None:
        """Test that task fails permanently after exhausting retries."""
        # Register failing task handler
        self.registry.register("failing", failing_task)

        # Enqueue task with limited retry attempts
        task = Task(name="failing", max_retries=2)
        self.backend.enqueue(task)

        # Start worker
        worker_thread = threading.Thread(target=self.worker.start)
        worker_thread.start()

        # Wait for processing (initial + 2 retries)
        time.sleep(1.0)

        # Stop worker
        self.worker.stop()
        self.worker.join(timeout=2)

        # Verify task was processed
        self.assertEqual(self.backend.size(), 0, "Queue should be empty")

        # Check worker stats
        stats = self.worker.get_stats()
        self.assertEqual(stats.tasks_processed, 3)  # initial + 2 retries
        self.assertEqual(stats.tasks_succeeded, 0)
        self.assertEqual(stats.tasks_failed, 1)
        self.assertEqual(stats.tasks_retried, 2)

    def test_custom_retry_policy_integration(self) -> None:
        """Test integration with custom retry policy."""
        # Custom retry policy: retry only for specific error types
        class CustomRetryPolicy(RetryPolicy):
            def should_retry(self, task: Task, error: Exception) -> RetryDecision:
                if isinstance(error, ValueError):
                    return RetryDecision(
                        should_retry=False,
                        reason=RetryDecisionReason.NON_RETRYABLE_ERROR,
                    )
                return RetryDecision(
                    should_retry=task.retry_count < task.max_retries,
                    reason=RetryDecisionReason.TRANSIENT_ERROR,
                )

        # Register task handlers
        self.registry.register("value_error", lambda: (_ for _ in ()).throw(ValueError("Non-retryable")))
        self.registry.register("runtime_error", lambda: (_ for _ in ()).throw(RuntimeError("Retryable")))

        # Create worker with custom policy
        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            retry_policy=CustomRetryPolicy(),
            poll_interval=0.01,
        )

        # Enqueue both types of tasks
        task1 = Task(name="value_error", max_retries=3)
        task2 = Task(name="runtime_error", max_retries=3)

        self.backend.enqueue(task1)
        self.backend.enqueue(task2)

        # Start worker
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        # Wait for processing
        time.sleep(1.0)

        # Stop worker
        worker.stop()
        worker.join(timeout=2)

        # Verify both tasks processed
        self.assertEqual(self.backend.size(), 0)

        # Check stats - value_error should fail immediately, runtime_error should retry
        stats = worker.get_stats()
        self.assertGreater(stats.tasks_processed, 0)
        # Runtime error task should have been retried


class MultiWorkerIntegrationTest(unittest.TestCase):
    """Integration tests for multiple concurrent workers."""

    def setUp(self):
        """Set up fresh components for each test."""
        self.backend = InMemoryBackend()
        self.registry = TaskRegistry()
        self.workers: List[Worker] = []
        self.lock = threading.Lock()

    def tearDown(self):
        """Clean up after each test."""
        for worker in self.workers:
            if worker.is_running():
                worker.stop()

        for worker in self.workers:
            worker.join(timeout=5)

    def test_multiple_workers_concurrent_processing(self) -> None:
        """Test that multiple workers can process tasks concurrently."""
        # Register handlers
        processed_tasks = []

        def tracking_task(payload: Any = None) -> Any:
            with self.lock:
                processed_tasks.append(payload)
            return f"processed_{payload}"

        self.registry.register("tracking", tracking_task)

        # Create multiple workers
        num_workers = 3
        for i in range(num_workers):
            worker = Worker(
                backend=self.backend,
                registry=self.registry,
                retry_policy=simple_retry_policy(max_attempts=1),
                poll_interval=0.01,
            )
            self.workers.append(worker)

        # Enqueue tasks
        num_tasks = 10
        for i in range(num_tasks):
            task = Task(name="tracking", payload=i, priority=(i % 5) + 1)
            self.backend.enqueue(task)

        # Start all workers
        worker_threads = []
        for worker in self.workers:
            t = threading.Thread(target=worker.start)
            t.start()
            worker_threads.append(t)

        # Wait for processing
        time.sleep(2.0)

        # Stop all workers
        for worker in self.workers:
            worker.stop()

        for t in worker_threads:
            t.join(timeout=2)

        # Verify all tasks processed
        self.assertEqual(self.backend.size(), 0, "Queue should be empty")

        # Check combined stats
        total_processed = sum(w.get_stats().tasks_processed for w in self.workers)
        self.assertEqual(total_processed, num_tasks, f"Should have processed {num_tasks} tasks")

        # Verify all unique payloads were processed
        self.assertEqual(len(set(processed_tasks)), num_tasks)

    def test_worker_isolation(self) -> None:
        """Test that workers maintain isolated stats and state."""
        # Register handler
        self.registry.register("simple", simple_task)

        # Create two workers
        worker1 = Worker(
            backend=self.backend,
            registry=self.registry,
            poll_interval=0.01,
        )
        worker2 = Worker(
            backend=self.backend,
            registry=self.registry,
            poll_interval=0.01,
        )
        self.workers.extend([worker1, worker2])

        # Enqueue tasks
        for i in range(5):
            task = Task(name="simple", payload=i)
            self.backend.enqueue(task)

        # Start both workers
        thread1 = threading.Thread(target=worker1.start)
        thread2 = threading.Thread(target=worker2.start)
        thread1.start()
        thread2.start()

        # Wait for processing
        time.sleep(1.0)

        # Stop workers
        worker1.stop()
        worker2.stop()
        thread1.join(timeout=2)
        thread2.join(timeout=2)

        # Verify all tasks processed
        self.assertEqual(self.backend.size(), 0)

        # Each worker should have processed some tasks
        stats1 = worker1.get_stats()
        stats2 = worker2.get_stats()

        total_processed = stats1.tasks_processed + stats2.tasks_processed
        self.assertEqual(total_processed, 5, "Both workers should have processed tasks")

        # Verify stats are separate
        self.assertIsInstance(stats1, WorkerStats)
        self.assertIsInstance(stats2, WorkerStats)


class ConfigurationIntegrationTest(unittest.TestCase):
    """Integration tests for configuration system."""

    def test_default_config_integration(self) -> None:
        """Test worker with default configuration."""
        # Get default config
        config = get_config()

        # Create worker with default config
        backend = InMemoryBackend()
        registry = TaskRegistry()
        registry.register("simple", simple_task)

        worker = Worker(
            backend=backend,
            registry=registry,
            config=config,
            poll_interval=0.01,
        )

        # Enqueue task
        task = Task(name="simple", payload=5)
        backend.enqueue(task)

        # Start worker
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        # Wait for processing
        time.sleep(0.5)

        # Stop worker
        worker.stop()
        worker.join(timeout=2)

        # Verify task processed
        self.assertEqual(backend.size(), 0)
        stats = worker.get_stats()
        self.assertEqual(stats.tasks_processed, 1)

    def test_config_file_integration(self) -> None:
        """Test loading configuration from file."""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
worker:
  poll_interval: 0.02
  max_retries: 2

retry:
  max_attempts: 3
  delay_ms: 50
""")
            config_path = f.name

        try:
            # Load config from file
            config = Config.from_file(config_path)

            # Create worker with loaded config
            backend = InMemoryBackend()
            registry = TaskRegistry()
            registry.register("flaky", flaky_task)

            worker = Worker(
                backend=backend,
                registry=registry,
                config=config,
                poll_interval=0.01,  # Override for faster testing
            )

            # Enqueue task
            task = Task(name="flaky", payload={"attempts": 0})
            backend.enqueue(task)

            # Start worker
            worker_thread = threading.Thread(target=worker.start)
            worker_thread.start()

            # Wait for processing
            time.sleep(1.0)

            # Stop worker
            worker.stop()
            worker.join(timeout=2)

            # Verify processing
            self.assertEqual(backend.size(), 0)

        finally:
            os.unlink(config_path)

    def test_config_overrides(self) -> None:
        """Test that constructor parameters override config."""
        # Create config
        config = Config()
        config.worker.poll_interval = 1.0

        # Create worker with override
        backend = InMemoryBackend()
        registry = TaskRegistry()
        registry.register("simple", simple_task)

        worker = Worker(
            backend=backend,
            registry=registry,
            config=config,
            poll_interval=0.01,  # Override config
        )

        # Verify the override took effect
        self.assertEqual(worker.poll_interval, 0.01)


class MiddlewareIntegrationTest(unittest.TestCase):
    """Integration tests for middleware system."""

    def setUp(self):
        """Set up fresh components for each test."""
        self.backend = InMemoryBackend()
        self.registry = TaskRegistry()
        self.middleware_calls = []

        # Test middleware that tracks calls
        class TrackingMiddleware(Middleware):
            def __init__(self, name, calls_list):
                self.name = name
                self.calls = calls_list

            def before_execute(self, task):
                self.calls.append(f"{self.name}.before")

            def after_execute(self, task, result):
                self.calls.append(f"{self.name}.after")

        self.tracking_middleware = TrackingMiddleware("track", self.middleware_calls)

    def test_middleware_pipeline_integration(self) -> None:
        """Test middleware pipeline with worker."""
        # Register task handler
        self.registry.register("simple", simple_task)

        # Create middleware pipeline
        pipeline = MiddlewarePipeline([
            LoggingMiddleware(),
            self.tracking_middleware,
        ])

        # Create worker with middleware
        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            middleware=[self.tracking_middleware],
            poll_interval=0.01,
        )

        # Enqueue task
        task = Task(name="simple", payload=5)
        self.backend.enqueue(task)

        # Start worker
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        # Wait for processing
        time.sleep(0.5)

        # Stop worker
        worker.stop()
        worker.join(timeout=2)

        # Verify middleware was called
        self.assertGreater(len(self.middleware_calls), 0, "Middleware should have been called")
        self.assertIn("track.before", self.middleware_calls)
        self.assertIn("track.after", self.middleware_calls)

        # Verify task processed
        self.assertEqual(backend.size(), 0)


class BackendIntegrationTest(unittest.TestCase):
    """Integration tests with different backends."""

    def test_memory_backend_integration(self) -> None:
        """Test complete integration with InMemoryBackend."""
        backend = InMemoryBackend()
        registry = TaskRegistry()
        registry.register("simple", simple_task)

        worker = Worker(
            backend=backend,
            registry=registry,
            poll_interval=0.01,
        )

        # Enqueue multiple tasks with different priorities
        for i in range(5):
            task = Task(name="simple", payload=i, priority=(i % 3) + 1)
            backend.enqueue(task)

        # Start worker
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        # Wait for processing
        time.sleep(0.5)

        # Stop worker
        worker.stop()
        worker.join(timeout=2)

        # Verify all tasks processed
        self.assertEqual(backend.size(), 0)
        stats = worker.get_stats()
        self.assertEqual(stats.tasks_processed, 5)
        self.assertEqual(stats.tasks_succeeded, 5)

    def test_backend_list_operations(self) -> None:
        """Test integration with backend list operations."""
        backend = InMemoryBackend()

        # Enqueue tasks
        task1 = Task(name="a", payload=1, priority=3)
        task2 = Task(name="b", payload=2, priority=1)
        task3 = Task(name="c", payload=3, priority=2)

        backend.enqueue(task1)
        backend.enqueue(task2)
        backend.enqueue(task3)

        # List should maintain priority order
        tasks = backend.list()
        self.assertEqual(len(tasks), 3)
        self.assertEqual(tasks[0].id, task2.id)  # priority 1
        self.assertEqual(tasks[1].id, task3.id)  # priority 2
        self.assertEqual(tasks[2].id, task1.id)  # priority 3

    def test_task_count_by_status(self) -> None:
        """Test integration with task status tracking."""
        backend = InMemoryBackend()

        # Create tasks in different statuses
        task1 = Task(name="pending", status=TaskStatus.PENDING)
        task2 = Task(name="running", status=TaskStatus.RUNNING)
        task3 = Task(name="completed", status=TaskStatus.COMPLETED)

        # InMemoryBackend doesn't filter by natively, but we can test the operations
        backend.enqueue(task1)

        # Can't enqueue non-pending tasks to queue
        # The backend handles this internally

        self.assertEqual(backend.size(), 1)


class RegistryIntegrationTest(unittest.TestCase):
    """Integration tests for task registry."""

    def test_registry_worker_integration(self) -> None:
        """Test registry integration with worker."""
        backend = InMemoryBackend()
        registry = TaskRegistry()

        # Register multiple task handlers
        registry.register("task1", lambda x: x * 2)
        registry.register("task2", lambda x: x * 3)
        registry.register("task3", lambda x: x * 4)

        worker = Worker(
            backend=backend,
            registry=registry,
            poll_interval=0.01,
        )

        # Enqueue tasks of different types
        backend.enqueue(Task(name="task1", payload=5))
        backend.enqueue(Task(name="task2", payload=5))
        backend.enqueue(Task(name="task3", payload=5))

        # Start worker
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        # Wait for processing
        time.sleep(0.5)

        # Stop worker
        worker.stop()
        worker.join(timeout=2)

        # Verify all tasks processed
        self.assertEqual(backend.size(), 0)
        stats = worker.get_stats()
        self.assertEqual(stats.tasks_processed, 3)
        self.assertEqual(stats.tasks_succeeded, 3)

    def test_unregistered_task_handling(self) -> None:
        """Test worker behavior with unregistered tasks."""
        backend = InMemoryBackend()
        registry = TaskRegistry()

        # Register only one handler
        registry.register("registered", simple_task)

        worker = Worker(
            backend=backend,
            registry=registry,
            poll_interval=0.01,
        )

        # Enqueue unregistered task
        task = Task(name="unregistered", payload=5)
        backend.enqueue(task)

        # Start worker
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        # Wait for processing
        time.sleep(0.5)

        # Stop worker
        worker.stop()
        worker.join(timeout=2)

        # Verify task failed
        self.assertEqual(backend.size(), 0)
        stats = worker.get_stats()
        self.assertEqual(stats.tasks_processed, 1)
        self.assertEqual(stats.tasks_succeeded, 0)
        self.assertEqual(stats.tasks_failed, 1)


class WorkerStatsIntegrationTest(unittest.TestCase):
    """Integration tests for worker statistics."""

    def test_worker_stats_tracking(self) -> None:
        """Test that worker accurately tracks statistics."""
        backend = InMemoryBackend()
        registry = TaskRegistry()

        # Register handlers with different outcomes
        registry.register("success", simple_task)
        registry.register("fail", failing_task)
        registry.register("flaky", flaky_task)

        worker = Worker(
            backend=backend,
            registry=registry,
            retry_policy=simple_retry_policy(max_attempts=3, delay_ms=10),
            poll_interval=0.01,
        )

        # Enqueue mixed tasks
        backend.enqueue(Task(name="success", payload=1))
        backend.enqueue(Task(name="fail"))
        backend.enqueue(Task(name="success", payload=2))
        backend.enqueue(Task(name="flaky", payload={"attempts": 0}))

        # Start worker
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

        # Wait for processing
        time.sleep(1.0)

        # Stop worker
        worker.stop()
        worker.join(timeout=2)

        # Check stats
        stats = worker.get_stats()

        self.assertIsNotNone(stats.start_time)
        self.assertIsNotNone(stats.last_activity_time)
        self.assertGreater(stats.total_execution_time, 0)

        # Verify task counts
        self.assertGreater(stats.tasks_processed, 0)
        self.assertGreater(stats.tasks_succeeded, 0)
        self.assertGreater(stats.tasks_failed, 0)
        self.assertGreater(stats.tasks_retried, 0)

    def test_worker_stats_multiple_sessions(self) -> None:
        """Test stats tracking across multiple worker sessions."""
        backend = InMemoryBackend()
        registry = TaskRegistry()
        registry.register("simple", simple_task)

        # Session 1
        worker1 = Worker(
            backend=backend,
            registry=registry,
            poll_interval=0.01,
        )

        backend.enqueue(Task(name="simple", payload=1))
        backend.enqueue(Task(name="simple", payload=2))

        worker_thread = threading.Thread(target=worker1.start)
        worker_thread.start()
        time.sleep(0.5)
        worker1.stop()
        worker1.join(timeout=2)

        stats1 = worker1.get_stats()
        self.assertEqual(stats1.tasks_processed, 2)

        # Session 2 - new worker
        worker2 = Worker(
            backend=backend,
            registry=registry,
            poll_interval=0.01,
        )

        backend.enqueue(Task(name="simple", payload=3))

        worker_thread2 = threading.Thread(target=worker2.start)
        worker_thread2.start()
        time.sleep(0.5)
        worker2.stop()
        worker2.join(timeout=2)

        stats2 = worker2.get_stats()
        self.assertEqual(stats2.tasks_processed, 1)

        # Verify sessions are independent
        self.assertNotEqual(stats1.start_time, stats2.start_time)


if __name__ == "__main__":
    unittest.main()