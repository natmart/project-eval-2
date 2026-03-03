"""
Tests for the Worker implementation.

Test coverage:
- Worker initialization and configuration
- Worker lifecycle (start, stop, join)
- Task processing with registered handlers
- Retry logic with exponential backoff
- Middleware chain execution
- Graceful shutdown via Event
- Error handling and logging
- Statistics tracking
- Integration with backends, registry, retry logic, middleware, and config
"""

import threading
import time
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from python_task_queue import (
    Task,
    TaskStatus,
    InMemoryBackend,
    TaskRegistry,
    RetryPolicy,
    RetryStrategy,
    RetryDecisionReason,
    simple_retry_policy,
    Worker,
    WorkerStats,
    create_worker,
    LoggingMiddleware,
    Middleware,
    MiddlewarePipeline,
    ExecutionContext,
)


class TestWorkerStats(unittest.TestCase):
    """Tests for WorkerStats dataclass."""
    
    def test_worker_stats_initialization(self):
        """Test that WorkerStats initializes with correct defaults."""
        stats = WorkerStats()
        
        self.assertEqual(stats.tasks_processed, 0)
        self.assertEqual(stats.tasks_succeeded, 0)
        self.assertEqual(stats.tasks_failed, 0)
        self.assertEqual(stats.tasks_retried, 0)
        self.assertEqual(stats.total_execution_time, 0.0)
        self.assertIsNone(stats.start_time)
        self.assertIsNone(stats.last_activity_time)
    
    def test_worker_stats_str(self):
        """Test WorkerStats string representation."""
        stats = WorkerStats()
        stats_str = str(stats)
        
        self.assertIn("WorkerStats", stats_str)
        self.assertIn("processed=0", stats_str)
        self.assertIn("succeeded=0", stats_str)
        self.assertIn("failed=0", stats_str)


class TestWorkerInitialization(unittest.TestCase):
    """Tests for Worker initialization."""
    
    def test_worker_default_initialization(self):
        """Test worker initialization with defaults."""
        worker = Worker()
        
        self.assertIsNotNone(worker.config)
        self.assertIsNotNone(worker.backend)
        self.assertIsInstance(worker.backend, InMemoryBackend)
        self.assertIsNotNone(worker.registry)
        self.assertIsNotNone(worker.retry_policy)
        self.assertIsNotNone(worker.shutdown_event)
        self.assertEqual(worker.poll_interval, worker.config.poll_interval)
        self.assertEqual(worker.max_retries, worker.config.max_retries)
        self.assertEqual(worker.backoff_base, worker.config.backoff_base)
        self.assertFalse(worker.is_running())
    
    def test_worker_custom_initialization(self):
        """Test worker initialization with custom parameters."""
        backend = InMemoryBackend()
        registry = TaskRegistry()
        retry_policy = simple_retry_policy(max_retries=5)
        shutdown_event = threading.Event()
        
        worker = Worker(
            backend=backend,
            registry=registry,
            retry_policy=retry_policy,
            poll_interval=2.0,
            max_retries=10,
            backoff_base=3.0,
            shutdown_event=shutdown_event,
        )
        
        self.assertIs(worker.backend, backend)
        self.assertIs(worker.registry, registry)
        self.assertIs(worker.retry_policy, retry_policy)
        self.assertEqual(worker.poll_interval, 2.0)
        self.assertEqual(worker.max_retries, 10)
        self.assertEqual(worker.backoff_base, 3.0)
        self.assertIs(worker.shutdown_event, shutdown_event)
    
    def test_worker_with_middleware(self):
        """Test worker initialization with middleware."""
        middleware = [LoggingMiddleware()]
        worker = Worker(middleware=middleware)
        
        self.assertEqual(len(worker.middleware), 1)
        self.assertIsInstance(worker.middleware[0], LoggingMiddleware)
        self.assertIsInstance(worker.middleware_pipeline, MiddlewarePipeline)
    
    def test_create_worker_factory(self):
        """Test the create_worker factory function."""
        worker = create_worker(poll_interval=2.0, max_retries=5)
        
        self.assertIsInstance(worker, Worker)
        self.assertEqual(worker.poll_interval, 2.0)
        self.assertEqual(worker.max_retries, 5)


class TestWorkerLifecycle(unittest.TestCase):
    """Tests for Worker lifecycle management."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.backend = InMemoryBackend()
        self.registry = TaskRegistry()
        self.worker = Worker(backend=self.backend, registry=self.registry)
    
    def test_start_and_stop_worker(self):
        """Test starting and stopping a worker."""
        self.assertFalse(self.worker.is_running())
        
        self.worker.start()
        time.sleep(0.1)  # Give it a moment to start
        self.assertTrue(self.worker.is_running())
        
        self.worker.stop()
        self.worker.join(timeout=2.0)
        self.assertFalse(self.worker.is_running())
    
    def test_start_daemon_worker(self):
        """Test starting a worker as a daemon thread."""
        self.worker.start(daemon=True)
        time.sleep(0.1)
        
        self.assertTrue(self.worker.is_running())
        self.assertTrue(self.worker._worker_thread.daemon)
        
        self.worker.stop()
        self.worker.join(timeout=2.0)
    
    def test_start_already_running_worker(self):
        """Test that starting an already running worker is idempotent."""
        self.worker.start()
        time.sleep(0.1)
        
        # Should not raise an exception
        self.worker.start()
        time.sleep(0.1)
        
        self.assertTrue(self.worker.is_running())
        self.worker.stop()
        self.worker.join(timeout=2.0)
    
    def test_stop_not_running_worker(self):
        """Test that stopping a non-running worker is idempotent."""
        self.assertFalse(self.worker.is_running())
        
        # Should not raise an exception
        self.worker.stop()
        self.assertFalse(self.worker.is_running())
    
    def test_worker_join(self):
        """Test joining a worker thread."""
        self.worker.start()
        time.sleep(0.1)
        
        self.worker.stop()
        self.worker.join(timeout=5.0)
        
        self.assertFalse(self.worker.is_running())
    
    def test_worker_repr(self):
        """Test worker string representation."""
        worker = Worker(backend=self.backend, registry=self.registry)
        
        repr_str = repr(worker)
        self.assertIn("Worker", repr_str)
        self.assertIn("stopped", repr_str)
        self.assertIn("processed=0", repr_str)


class TestTaskProcessing(unittest.TestCase):
    """Tests for task processing functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.backend = InMemoryBackend()
        self.registry = TaskRegistry()
        self.worker = Worker(backend=self.backend, registry=self.registry)
        
        # Register a simple handler
        @self.registry.register("add_numbers")
        def add_numbers(payload):
            return payload["a"] + payload["b"]
        
        @self.registry.register("failing_task")
        def failing_task(payload):
            raise ValueError("This task always fails")
    
    def test_process_once_empty_queue(self):
        """Test processing when queue is empty."""
        result = self.worker.process_once()
        
        self.assertFalse(result)
    
    def test_process_once_success(self):
        """Test processing a single successful task."""
        task = Task(
            name="add_numbers",
            payload={"a": 5, "b": 3},
        )
        self.backend.enqueue(task)
        
        result = self.worker.process_once()
        
        self.assertTrue(result)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.result.value, 8)
        self.assertEqual(self.worker.stats.tasks_processed, 1)
        self.assertEqual(self.worker.stats.tasks_succeeded, 1)
        self.assertEqual(self.worker.stats.tasks_failed, 0)
    
    def test_process_once_handler_not_found(self):
        """Test processing a task with no registered handler."""
        task = Task(
            name="unknown_task",
            payload={"data": "test"},
        )
        self.backend.enqueue(task)
        
        result = self.worker.process_once()
        
        self.assertTrue(result)
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertIn("Handler not found", task.error)
        self.assertEqual(self.worker.stats.tasks_processed, 1)
        self.assertEqual(self.worker.stats.tasks_succeeded, 0)
        self.assertEqual(self.worker.stats.tasks_failed, 1)
    
    def test_process_once_handler_fails(self):
        """Test processing a task whose handler raises an exception."""
        task = Task(
            name="failing_task",
            payload={"data": "test"},
        )
        self.backend.enqueue(task)
        
        result = self.worker.process_once()
        
        self.assertTrue(result)
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertIsNotNone(task.error)
        self.assertEqual(self.worker.stats.tasks_processed, 1)
        self.assertEqual(self.worker.stats.tasks_succeeded, 0)
        self.assertEqual(self.worker.stats.tasks_failed, 1)
    
    def test_process_task_direct(self):
        """Test processing a task directly without dequeuing."""
        task = Task(
            name="add_numbers",
            payload={"a": 10, "b": 20},
        )
        
        self.worker.process_task(task)
        
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertEqual(task.result.value, 30)
    
    def test_process_multiple_tasks(self):
        """Test processing multiple tasks sequentially."""
        tasks = [
            Task(name="add_numbers", payload={"a": 1, "b": 2}),
            Task(name="add_numbers", payload={"a": 3, "b": 4}),
            Task(name="add_numbers", payload={"a": 5, "b": 6}),
        ]
        
        for task in tasks:
            self.backend.enqueue(task)
        
        while self.worker.process_once():
            pass
        
        self.assertEqual(self.worker.stats.tasks_processed, 3)
        self.assertEqual(self.worker.stats.tasks_succeeded, 3)
        self.assertEqual(self.worker.stats.tasks_failed, 0)
        
        # Check all tasks completed successfully
        self.assertEqual(tasks[0].result.value, 3)
        self.assertEqual(tasks[1].result.value, 7)
        self.assertEqual(tasks[2].result.value, 11)


class TestRetryLogic(unittest.TestCase):
    """Tests for retry logic integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.backend = InMemoryBackend()
        self.registry = TaskRegistry()
        self.retry_policy = simple_retry_policy(max_retries=3)
        self.worker = Worker(
            backend=self.backend,
            registry=self.registry,
            retry_policy=self.retry_policy,
        )
        
        # Track call count
        self.call_count = 0
        
        @self.registry.register("retryable_task")
        def retryable_task(payload):
            self.call_count += 1
            if self.call_count < 3:
                raise RuntimeError("Temporary failure")
            return "success"
    
    def test_task_retry_on_failure(self):
        """Test that tasks are retried on temporary failures."""
        task = Task(
            name="retryable_task",
            payload={},
            max_retries=3,
        )
        self.backend.enqueue(task)
        
        # Process once - should fail and schedule retry
        self.worker.process_once()
        
        # Task should be in RETRYING status
        self.assertEqual(task.status, TaskStatus.RETRYING)
        self.assertEqual(self.worker.stats.tasks_retried, 1)
        self.assertEqual(task.retry_count, 1)
    
    def test_task_retry_exhausted(self):
        """Test that tasks are marked as FAILED after max retries."""
        @self.registry.register("always_fails")
        def always_fails(payload):
            raise RuntimeError("Always fails")
        
        task = Task(
            name="always_fails",
            payload={},
            max_retries=0,  # No retries
        )
        self.backend.enqueue(task)
        
        self.worker.process_once()
        
        # Should fail immediately without retry
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertEqual(self.worker.stats.tasks_retried, 0)
    
    def test_custom_retry_policy(self):
        """Test that custom retry policies are respected."""
        custom_policy = RetryPolicy(
            max_retries=5,
            strategy=RetryStrategy.EXPONENTIAL,
            initial_delay=2.0,
        )
        
        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            retry_policy=custom_policy,
        )
        
        @self.registry.register("failing_with_custom_policy")
        def failing_task(payload):
            raise RuntimeError("Fail")
        
        task = Task(
            name="failing_with_custom_policy",
            payload={},
            max_retries=5,
        )
        self.backend.enqueue(task)
        
        worker.process_once()
        
        # Should retry based on custom policy
        self.assertEqual(task.status, TaskStatus.RETRYING)


class TestMiddleware(unittest.TestCase):
    """Tests for middleware integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.backend = InMemoryBackend()
        self.registry = TaskRegistry()
        
        @self.registry.register("test_task")
        def test_task(payload):
            return payload["value"] * 2
    
    def test_middleware_before_execution(self):
        """Test that middleware before_execution hooks are called."""
        before_called = []
        
        class TestMiddleware(Middleware):
            def before_execution(self, context: ExecutionContext) -> None:
                before_called.append(context.task.name)
            
            def after_execution(self, context: ExecutionContext) -> None:
                pass
        
        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            middleware=[TestMiddleware()],
        )
        
        task = Task(name="test_task", payload={"value": 5})
        worker.process_task(task)
        
        self.assertEqual(before_called, ["test_task"])
        self.assertEqual(task.result.value, 10)
    
    def test_middleware_after_execution(self):
        """Test that middleware after_execution hooks are called."""
        after_called = []
        
        class TestMiddleware(Middleware):
            def before_execution(self, context: ExecutionContext) -> None:
                pass
            
            def after_execution(self, context: ExecutionContext) -> None:
                after_called.append((context.task.name, context.result))
        
        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            middleware=[TestMiddleware()],
        )
        
        task = Task(name="test_task", payload={"value": 5})
        worker.process_task(task)
        
        self.assertEqual(len(after_called), 1)
        self.assertEqual(after_called[0][0], "test_task")
        self.assertEqual(after_called[0][1], 10)
    
    def test_middleware_chain(self):
        """Test that multiple middleware are called in order."""
        call_order = []
        
        class Middleware1(Middleware):
            def before_execution(self, context: ExecutionContext) -> None:
                call_order.append("m1_before")
            
            def after_execution(self, context: ExecutionContext) -> None:
                call_order.append("m1_after")
        
        class Middleware2(Middleware):
            def before_execution(self, context: ExecutionContext) -> None:
                call_order.append("m2_before")
            
            def after_execution(self, context: ExecutionContext) -> None:
                call_order.append("m2_after")
        
        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            middleware=[Middleware1(), Middleware2()],
        )
        
        task = Task(name="test_task", payload={"value": 5})
        worker.process_task(task)
        
        # Before hooks in order, after hooks in reverse order
        self.assertEqual(call_order, ["m1_before", "m2_before", "m2_after", "m1_after"])
    
    def test_middleware_with_error(self):
        """Test that after_execution is called even when handler fails."""
        after_called = []
        
        @self.registry.register("failing_task")
        def failing_task(payload):
            raise RuntimeError("Handler failed")
        
        class TestMiddleware(Middleware):
            def before_execution(self, context: ExecutionContext) -> None:
                pass
            
            def after_execution(self, context: ExecutionContext) -> None:
                after_called.append(context.error)
        
        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            middleware=[TestMiddleware()],
        )
        
        task = Task(name="failing_task", payload={})
        worker.process_task(task)
        
        self.assertEqual(len(after_called), 1)
        self.assertIsInstance(after_called[0], RuntimeError)
    
    def test_add_middleware(self):
        """Test adding middleware to a running worker."""
        worker = Worker(backend=self.backend, registry=self.registry)
        
        middleware = LoggingMiddleware()
        worker.add_middleware(middleware)
        
        self.assertEqual(len(worker.middleware), 1)
        self.assertIsInstance(worker.middleware[0], LoggingMiddleware)


class TestStatistics(unittest.TestCase):
    """Tests for worker statistics."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.backend = InMemoryBackend()
        self.registry = TaskRegistry()
        self.worker = Worker(backend=self.backend, registry=self.registry)
        
        @self.registry.register("success_task")
        def success_task(payload):
            return "success"
        
        @self.registry.register("failure_task")
        def failure_task(payload):
            raise ValueError("failure")
    
    def test_statistics_tracking(self):
        """Test that statistics are tracked correctly."""
        # Process successful task
        task1 = Task(name="success_task", payload={})
        self.backend.enqueue(task1)
        self.worker.process_once()
        
        # Process failed task
        task2 = Task(name="failure_task", payload={})
        self.backend.enqueue(task2)
        self.worker.process_once()
        
        stats = self.worker.get_stats()
        
        self.assertEqual(stats.tasks_processed, 2)
        self.assertEqual(stats.tasks_succeeded, 1)
        self.assertEqual(stats.tasks_failed, 1)
        self.assertEqual(stats.tasks_retried, 0)
        self.assertIsInstance(stats.start_time, datetime)
        self.assertIsInstance(stats.last_activity_time, datetime)
    
    def test_get_stats_returns_copy(self):
        """Test that get_stats returns a copy, not the internal object."""
        task = Task(name="success_task", payload={})
        self.backend.enqueue(task)
        self.worker.process_once()
        
        stats1 = self.worker.get_stats()
        stats2 = self.worker.get_stats()
        
        self.assertIsNot(stats1, stats2)
        self.assertEqual(stats1.tasks_processed, stats2.tasks_processed)
    
    def test_reset_stats(self):
        """Test resetting worker statistics."""
        task = Task(name="success_task", payload={})
        self.backend.enqueue(task)
        self.worker.process_once()
        
        self.worker.reset_stats()
        
        stats = self.worker.get_stats()
        self.assertEqual(stats.tasks_processed, 0)
        self.assertEqual(stats.tasks_succeeded, 0)
        self.assertEqual(stats.tasks_failed, 0)
        self.assertIsInstance(stats.start_time, datetime)
    
    def test_execution_time_tracking(self):
        """Test that execution time is tracked."""
        task = Task(name="success_task", payload={})
        self.worker.process_task(task)
        
        stats = self.worker.get_stats()
        self.assertGreater(stats.total_execution_time, 0)


class TestGracefulShutdown(unittest.TestCase):
    """Tests for graceful shutdown functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.backend = InMemoryBackend()
        self.registry = TaskRegistry()
        self.worker = Worker(backend=self.backend, registry=self.registry)
    
    def test_shutdown_event_stops_worker(self):
        """Test that setting shutdown event stops the worker."""
        self.worker.start()
        time.sleep(0.1)
        
        self.assertTrue(self.worker.is_running())
        
        # Signal shutdown
        self.worker.shutdown_event.set()
        self.worker.join(timeout=2.0)
        
        self.assertFalse(self.worker.is_running())
    
    def test_stop_with_timeout(self):
        """Test stopping worker with timeout."""
        # Create a slow handler
        @self.registry.register("slow_task")
        def slow_task(payload):
            time.sleep(0.5)
            return "done"
        
        # Enqueue multiple tasks
        for _ in range(5):
            task = Task(name="slow_task", payload={})
            self.backend.enqueue(task)
        
        self.worker.start()
        time.sleep(0.2)
        
        # Stop with short timeout
        self.worker.stop(timeout=0.1)
        
        # Worker should stop (but might not complete all tasks)
        self.assertFalse(self.worker.is_running())
    
    def test_stop_during_task_execution(self):
        """Test stopping while a task is executing."""
        execution_started = threading.Event()
        
        @self.registry.register("long_task")
        def long_task(payload):
            execution_started.set()
            time.sleep(1.0)  # Long task
            return "done"
        
        task = Task(name="long_task", payload={})
        self.backend.enqueue(task)
        
        # Start worker in a thread
        worker_thread = threading.Thread(target=self.worker.process_once)
        worker_thread.start()
        
        # Wait for task to start
        execution_started.wait(timeout=0.5)
        
        # Stop the worker
        self.worker.shutdown_event.set()
        worker_thread.join(timeout=2.0)


class TestErrorHandling(unittest.TestCase):
    """Tests for error handling in the worker."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.backend = InMemoryBackend()
        self.registry = TaskRegistry()
        self.worker = Worker(backend=self.backend, registry=self.registry)
    
    def test_task_start_state_error(self):
        """Test handling of task with invalid starting state."""
        task = Task(name="test", payload={})
        task.status = TaskStatus.COMPLETED  # Invalid state to start
        
        @self.registry.register("test")
        def test_handler(payload):
            return "result"
        
        # Should still attempt to process
        self.worker.process_task(task)
    
    def test_middleware_exception_handled(self):
        """Test that exceptions in middleware are handled gracefully."""
        class FailingMiddleware(Middleware):
            def before_execution(self, context: ExecutionContext) -> None:
                raise RuntimeError("Middleware failed")
            
            def after_execution(self, context: ExecutionContext) -> None:
                raise RuntimeError("After failed")
        
        worker = Worker(
            backend=self.backend,
            registry=self.registry,
            middleware=[FailingMiddleware()],
        )
        
        @self.registry.register("test_task")
        def test_task(payload):
            return "result"
        
        task = Task(name="test_task", payload={})
        
        # Should handle middleware exceptions and still execute
        worker.process_task(task)
        
        # Task should complete despite middleware failure
        self.assertEqual(task.status, TaskStatus.COMPLETED)


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete worker system."""
    
    def test_full_worker_workflow(self):
        """Test complete workflow: enqueue -> process -> complete."""
        backend = InMemoryBackend()
        registry = TaskRegistry()
        
        @registry.register("process_data")
        def process_data(payload):
            return {"processed": payload["data"] * 2}
        
        worker = Worker(
            backend=backend,
            registry=registry,
            poll_interval=0.1,
        )
        
        # Enqueue tasks
        task1 = Task(name="process_data", payload={"data": 10})
        task2 = Task(name="process_data", payload={"data": 20})
        backend.enqueue(task1)
        backend.enqueue(task2)
        
        # Process tasks
        worker.start()
        time.sleep(0.5)  # Give time to process
        worker.stop()
        worker.join(timeout=2.0)
        
        # Verify results
        self.assertEqual(task1.status, TaskStatus.COMPLETED)
        self.assertEqual(task1.result.value, {"processed": 20})
        self.assertEqual(task2.status, TaskStatus.COMPLETED)
        self.assertEqual(task2.result.value, {"processed": 40})
        
        stats = worker.get_stats()
        self.assertEqual(stats.tasks_processed, 2)
        self.assertEqual(stats.tasks_succeeded, 2)
    
    def test_retry_workflow(self):
        """Test complete retry workflow with eventual success."""
        backend = InMemoryBackend()
        registry = TaskRegistry()
        
        attempt_count = 0
        
        @registry.register("flaky_task")
        def flaky_task(payload):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise RuntimeError("Temporary error")
            return "success"
        
        worker = Worker(
            backend=backend,
            registry=registry,
            retry_policy=simple_retry_policy(max_retries=5),
        )
        
        task = Task(name="flaky_task", payload={})
        backend.enqueue(task)
        
        # Process first attempt (will fail and schedule retry)
        worker.process_once()
        self.assertEqual(task.status, TaskStatus.RETRYING)
        
        # Wait for retry
        time.sleep(1.5)  # Wait for retry delay
        
        # Process the retry (will fail again and schedule another retry)
        self.backend.enqueue(task)  # Re-enqueue for retry
        worker.process_once()
        
        self.assertEqual(task.retry_count, 2)


if __name__ == "__main__":
    unittest.main()