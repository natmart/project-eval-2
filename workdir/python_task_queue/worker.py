"""
Worker implementation for the Python Task Queue Library.

The Worker class polls the queue, executes task handlers via registry,
manages retries with exponential backoff, supports graceful shutdown,
and integrates with backends, retry logic, registry, middleware, and config.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from python_task_queue.backends import QueueBackend, InMemoryBackend
from python_task_queue.config import Config, get_config
from python_task_queue.models import Task, TaskResult, TaskStatus
from python_task_queue.registry import TaskRegistry, get_registry
from python_task_queue.retry import (
    RetryPolicy,
    RetryDecision,
    RetryStrategy,
    simple_retry_policy,
)
from python_task_queue.middleware import Middleware, MiddlewarePipeline


logger = logging.getLogger(__name__)


@dataclass
class WorkerStats:
    """
    Statistics for worker operations.
    
    Attributes:
        tasks_processed: Total number of tasks processed
        tasks_succeeded: Number of tasks that succeeded
        tasks_failed: Number of tasks that failed
        tasks_retried: Number of tasks that were retried
        total_execution_time: Total time spent executing tasks (seconds)
        start_time: Worker start time
        last_activity_time: Last time a task was processed
    """
    tasks_processed: int = 0
    tasks_succeeded: int = 0
    tasks_failed: int = 0
    tasks_retried: int = 0
    total_execution_time: float = 0.0
    start_time: Optional[datetime] = None
    last_activity_time: Optional[datetime] = None
    
    def __str__(self) -> str:
        return (
            f"WorkerStats(processed={self.tasks_processed}, "
            f"succeeded={self.tasks_succeeded}, failed={self.tasks_failed}, "
            f"retried={self.tasks_retried})"
        )


class Worker:
    """
    Task queue worker that processes tasks from a queue backend.
    
    The Worker class polls the queue for tasks, executes them using registered
    handlers, manages retries with exponential backoff, and supports graceful
    shutdown via threading.Event.
    
    Features:
    - Polling with configurable interval
    - Task execution through registry
    - Retry logic integration with exponential backoff
    - Middleware chain execution
    - Graceful shutdown on Event
    - Comprehensive error handling and logging
    - Worker statistics tracking
    
    Examples:
        >>> # Create and start a worker
        >>> worker = Worker()
        >>> worker.start()
        >>> 
        >>> # Stop the worker gracefully
        >>> worker.stop()
        >>> worker.join()
    """
    
    def __init__(
        self,
        backend: Optional[QueueBackend] = None,
        registry: Optional[TaskRegistry] = None,
        retry_policy: Optional[RetryPolicy] = None,
        middleware: Optional[List[Middleware]] = None,
        config: Optional[Config] = None,
        poll_interval: Optional[float] = None,
        max_retries: Optional[int] = None,
        backoff_base: Optional[float] = None,
        shutdown_event: Optional[threading.Event] = None,
    ):
        """
        Initialize a worker.
        
        Args:
            backend: Queue backend to use (defaults to InMemoryBackend)
            registry: Task registry to use (defaults to global registry)
            retry_policy: Retry policy to use (defaults to simple_retry_policy)
            middleware: List of middleware to apply to task execution
            config: Configuration object (defaults to global config)
            poll_interval: Polling interval in seconds (overrides config)
            max_retries: Maximum number of retries (overrides config)
            backoff_base: Base multiplier for exponential backoff (overrides config)
            shutdown_event: Event for graceful shutdown (creates new one if None)
        """
        # Get defaults if not provided
        self.config = config or get_config()
        self.backend = backend or InMemoryBackend()
        self.registry = registry or get_registry()
        self.retry_policy = retry_policy or simple_retry_policy()
        self.shutdown_event = shutdown_event or threading.Event()
        
        # Override config values if explicitly provided
        self.poll_interval = poll_interval or self.config.poll_interval
        self.max_retries = max_retries or self.config.max_retries
        self.backoff_base = backoff_base or self.config.backoff_base
        
        # Setup middleware pipeline
        self.middleware = middleware or []
        self.middleware_pipeline = MiddlewarePipeline(self.middleware)
        
        # Worker state
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # Statistics
        self.stats = WorkerStats()
        
        logger.debug(
            f"Worker initialized: poll_interval={self.poll_interval}s, "
            f"max_retries={self.max_retries}, backoff_base={self.backoff_base}"
        )
    
    def start(self, daemon: bool = False) -> None:
        """
        Start the worker in a background thread.
        
        Args:
            daemon: Whether to run the worker thread as a daemon
        """
        with self._lock:
            if self._running:
                logger.warning("Worker is already running")
                return
            
            self._running = True
            self.shutdown_event.clear()
            self.stats.start_time = datetime.utcnow()
            
            self._worker_thread = threading.Thread(
                target=self._run_loop,
                name="TaskQueueWorker",
                daemon=daemon,
            )
            self._worker_thread.start()
            
            logger.info("Worker started")
    
    def stop(self, timeout: Optional[float] = None) -> None:
        """
        Signal the worker to stop gracefully.
        
        Args:
            timeout: Optional timeout in seconds to wait for the worker to stop
        """
        with self._lock:
            if not self._running:
                logger.warning("Worker is not running")
                return
            
            logger.info("Stopping worker...")
            self.shutdown_event.set()
            self._running = False
        
        if timeout is not None and self._worker_thread:
            self._worker_thread.join(timeout)
    
    def is_running(self) -> bool:
        """
        Check if the worker is currently running.
        
        Returns:
            True if the worker is running, False otherwise
        """
        with self._lock:
            return self._running
    
    def join(self, timeout: Optional[float] = None) -> None:
        """
        Wait for the worker thread to finish.
        
        Args:
            timeout: Optional timeout in seconds
        """
        if self._worker_thread:
            self._worker_thread.join(timeout)
    
    def process_once(self) -> bool:
        """
        Process a single task from the queue (blocking call).
        
        This method dequeues a task, executes it, and handles the result.
        It runs once and returns, making it useful for manual task processing
        or testing.
        
        Returns:
            True if a task was processed, False if the queue was empty
        """
        task = self.backend.dequeue()
        if task is None:
            return False
        
        self._process_task(task)
        return True
    
    def process_task(self, task: Task) -> None:
        """
        Process a specific task (synchronous call).
        
        Args:
            task: The task to process
        """
        self._process_task(task)
    
    def _run_loop(self) -> None:
        """
        Main worker loop.
        
        Continuously polls the queue for tasks and processes them
        until shutdown is signaled.
        """
        logger.info("Worker loop started")
        
        try:
            while not self.shutdown_event.is_set():
                try:
                    # Process a task if available
                    if self.process_once():
                        stats_str = str(self.stats)
                        logger.debug(f"Worker stats: {stats_str}")
                    else:
                        # Queue empty, wait for poll interval
                        self.shutdown_event.wait(self.poll_interval)
                
                except Exception as e:
                    logger.exception(f"Unexpected error in worker loop: {e}")
                    # Wait before retrying to avoid tight error loop
                    self.shutdown_event.wait(min(self.poll_interval, 5.0))
        
        finally:
            logger.info("Worker loop finished")
    
    def _process_task(self, task: Task) -> None:
        """
        Process a single task.
        
        This method:
        1. Marks the task as running
        2. Retrieves the handler from the registry
        3. Executes the handler through the middleware pipeline
        4. Handles success/failure and updates task status
        5. Manages retries if applicable
        
        Args:
            task: The task to process
        """
        self.stats.tasks_processed += 1
        self.stats.last_activity_time = datetime.utcnow()
        
        logger.info(f"Processing task {task.name} (id={task.id})")
        
        # Update task status to running
        try:
            task.start()
        except ValueError:
            logger.warning(f"Task {task.id} is not in a startable state: {task.status}")
            # Still try to process the task
        
        # Get handler from registry
        try:
            handler = self.registry.get(task.name)
        except Exception as e:
            logger.error(f"Handler not found for task {task.name}: {e}")
            task.fail(
                error=f"Handler not found: {e}",
                error_type=type(e).__name__,
                can_retry=False,
            )
            self._handle_task_completion(task, success=False)
            return
        
        # Execute the handler
        start_time = time.time()
        success = False
        result_value = None
        error = None
        
        try:
            # Execute through middleware pipeline
            result_value = self.middleware_pipeline.execute(task, handler)
            success = True
            
        except Exception as e:
            error = e
            logger.exception(f"Task {task.name} failed with exception: {e}")
            
            # Check if we should retry
            retry_decision = self.retry_policy.get_retry_decision(task, e)
            
            if retry_decision.should_retry:
                # Retry the task
                task.retry_count += 1
                task.status = TaskStatus.RETRYING
                task.error = str(e)
                task.result = TaskResult.from_failure(
                    error=str(e),
                    error_type=type(e).__name__,
                    traceback=traceback.format_exc(),
                )
                
                self.stats.tasks_retried += 1
                
                logger.info(
                    f"Retrying task {task.name} (attempt {task.retry_count}/"
                    f"{self.max_retries}) after {retry_decision.delay:.2f}s"
                )
                
                # Re-enqueue with delay
                # Note: In a real implementation, we might use a separate
                # delayed queue or schedule the retry. For now, we just
                # re-enqueue and let the backoff be managed externally or
                # by the caller.
                threading.Thread(
                    target=self._retry_later,
                    args=(task, retry_decision.delay),
                    daemon=True,
                ).start()
                
                return
            else:
                task.fail(
                    error=str(e),
                    error_type=type(e).__name__,
                    traceback=traceback.format_exc(),
                    can_retry=False,
                )
        
        finally:
            execution_time = time.time() - start_time
            self.stats.total_execution_time += execution_time
            logger.debug(
                f"Task {task.name} execution time: {execution_time:.3f}s"
            )
        
        # Handle task completion
        if success:
            task.complete(result_value)
            self._handle_task_completion(task, success=True)
        elif error:
            self._handle_task_completion(task, success=False)
    
    def _retry_later(self, task: Task, delay: float) -> None:
        """
        Retry a task after a delay.
        
        Args:
            task: The task to retry
            delay: Delay in seconds before retry
        """
        if self.shutdown_event.is_set():
            logger.info(f"Not retrying task {task.id} due to shutdown")
            return
        
        time.sleep(delay)
        
        if self.shutdown_event.is_set():
            logger.info(f"Not retrying task {task.id} due to shutdown")
            return
        
        # Reset task status to pending for retry
        task.status = TaskStatus.PENDING
        logger.info(f"Re-enqueuing task {task.id} for retry")
        self.backend.enqueue(task)
    
    def _handle_task_completion(self, task: Task, success: bool) -> None:
        """
        Handle task completion, updating statistics and backend.
        
        Args:
            task: The completed task
            success: Whether the task succeeded
        """
        if success:
            self.stats.tasks_succeeded += 1
            logger.info(f"Task {task.name} completed successfully")
            try:
                self.backend.acknowledge(task.id)
            except Exception as e:
                logger.error(f"Failed to acknowledge task {task.id}: {e}")
        else:
            self.stats.tasks_failed += 1
            logger.warning(f"Task {task.name} failed")
            try:
                self.backend.fail(task.id, str(task.error or "Unknown error"))
            except Exception as e:
                logger.error(f"Failed to mark task {task.id} as failed: {e}")
    
    def get_stats(self) -> WorkerStats:
        """
        Get a snapshot of the worker statistics.
        
        Returns:
            WorkerStats object with current statistics
        """
        with self._lock:
            # Return a copy to avoid external modification
            return WorkerStats(
                tasks_processed=self.stats.tasks_processed,
                tasks_succeeded=self.stats.tasks_succeeded,
                tasks_failed=self.stats.tasks_failed,
                tasks_retried=self.stats.tasks_retried,
                total_execution_time=self.stats.total_execution_time,
                start_time=self.stats.start_time,
                last_activity_time=self.stats.last_activity_time,
            )
    
    def reset_stats(self) -> None:
        """Reset the worker statistics."""
        with self._lock:
            self.stats = WorkerStats(start_time=datetime.utcnow())
            logger.info("Worker statistics reset")
    
    def add_middleware(self, middleware: Middleware) -> None:
        """
        Add middleware to the worker's pipeline.
        
        Args:
            middleware: The middleware to add
        """
        with self._lock:
            self.middleware.append(middleware)
            self.middleware_pipeline = MiddlewarePipeline(self.middleware)
            logger.info(f"Added middleware: {type(middleware).__name__}")
    
    def __repr__(self) -> str:
        status = "running" if self.is_running() else "stopped"
        return (
            f"Worker(status={status}, "
            f"processed={self.stats.tasks_processed}, "
            f"succeeded={self.stats.tasks_succeeded}, "
            f"failed={self.stats.tasks_failed})"
        )


def create_worker(
    backend: Optional[QueueBackend] = None,
    registry: Optional[TaskRegistry] = None,
    retry_policy: Optional[RetryPolicy] = None,
    middleware: Optional[List[Middleware]] = None,
    **kwargs
) -> Worker:
    """
    Factory function to create a configured worker.
    
    This is a convenience function that provides a cleaner API for
    creating workers with common configurations.
    
    Args:
        backend: Queue backend to use
        registry: Task registry to use
        retry_policy: Retry policy to use
        middleware: List of middleware to apply
        **kwargs: Additional arguments passed to Worker.__init__
    
    Returns:
        Configured Worker instance
    
    Examples:
        >>> worker = create_worker(
        ...     poll_interval=2.0,
        ...     max_retries=5,
        ...     middleware=[LoggingMiddleware()]
        ... )
        >>> worker.start()
    """
    return Worker(
        backend=backend,
        registry=registry,
        retry_policy=retry_policy,
        middleware=middleware,
        **kwargs
    )