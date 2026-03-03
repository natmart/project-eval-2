#!/usr/bin/env python3
"""
Demo script for the Worker implementation.

This script demonstrates:
- Creating and configuring a worker
- Registering task handlers
- Processing tasks with the worker
- Using retry logic
- Integrating middleware
- Graceful shutdown
- Worker statistics
"""

import time
import logging
from python_task_queue import (
    Task,
    InMemoryBackend,
    TaskRegistry,
    simple_retry_policy,
    Worker,
    create_worker,
    LoggingMiddleware,
    Middleware,
    MiddlewarePipeline,
    ExecutionContext,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Custom middleware example
class TimingMiddleware(Middleware):
    """Middleware that measures execution time."""
    
    def before_execution(self, context: ExecutionContext) -> None:
        context.metadata["start_time"] = time.time()
        logger.info(f"[TimingMiddleware] Starting execution of {context.task.name}")
    
    def after_execution(self, context: ExecutionContext) -> None:
        if "start_time" in context.metadata:
            elapsed = time.time() - context.metadata["start_time"]
            logger.info(
                f"[TimingMiddleware] Task {context.task.name} "
                f"completed in {elapsed:.3f}s"
            )


# Task handlers
def process_data_handler(payload):
    """Example handler that processes data."""
    data = payload.get("data", 0)
    result = data * 2
    logger.info(f"Processing Data: {data} -> {result}")
    return result


def send_email_handler(payload):
    """Example handler that sends an email."""
    to = payload.get("to", "unknown")
    subject = payload.get("subject", "No subject")
    logger.info(f"Sending email to {to}: {subject}")
    return {"status": "sent", "to": to}


def failing_task_handler(payload):
    """Example handler that fails."""
    logger.info("Failing task handler called")
    raise RuntimeError("This task always fails!")


def flaky_task_handler(payload):
    """Example handler that fails initially but succeeds on retry."""
    attempt = payload.get("attempt", 1)
    logger.info(f"Flaky task handler called (attempt {attempt})")
    
    if attempt < 3:
        raise RuntimeError(f"Temporary failure (attempt {attempt})")
    
    logger.info("Flaky task succeeded!")
    return {"status": "success", "attempts": attempt}


def slow_task_handler(payload):
    """Example handler that takes a long time to execute."""
    duration = payload.get("duration", 2.0)
    logger.info(f"Slow task starting (will take {duration}s)")
    time.sleep(duration)
    logger.info("Slow task completed")
    return {"status": "done", "duration": duration}


# Demo 1: Basic Worker Usage
def demo_basic_worker():
    """Demonstrate basic worker usage."""
    logger.info("\n" + "="*60)
    logger.info("Demo 1: Basic Worker Usage")
    logger.info("="*60 + "\n")
    
    # Create registry and register handlers
    registry = TaskRegistry()
    registry.register("process_data")(process_data_handler)
    registry.register("send_email")(send_email_handler)
    
    # Create worker
    backend = InMemoryBackend()
    worker = Worker(backend=backend, registry=registry, poll_interval=0.5)
    
    # Enqueue tasks
    task1 = Task(name="process_data", payload={"data": 10})
    task2 = Task(name="send_email", payload={"to": "user@example.com", "subject": "Hello"})
    task3 = Task(name="send_email", payload={"to": "admin@example.com", "subject": "Alert"})
    
    backend.enqueue(task1)
    backend.enqueue(task2)
    backend.enqueue(task3)
    
    logger.info(f"Enqueued {backend.size()} tasks")
    
    # Process tasks
    worker.start()
    time.sleep(2.0)  # Give time to process
    worker.stop()
    worker.join(timeout=5.0)
    
    # Show statistics
    stats = worker.get_stats()
    logger.info(f"\nStatistics: {stats}")
    logger.info(f"Task statuses:")
    logger.info(f"  - Task 1 ({task1.name}): {task1.status}")
    logger.info(f"  - Task 2 ({task2.name}): {task2.status}")
    logger.info(f"  - Task 3 ({task3.name}): {task3.status}")


# Demo 2: Worker with Retry Logic
def demo_worker_with_retry():
    """Demonstrate retry logic."""
    logger.info("\n" + "="*60)
    logger.info("Demo 2: Worker with Retry Logic")
    logger.info("="*60 + "\n")
    
    # Create registry with handlers
    registry = TaskRegistry()
    registry.register("flaky_task")(flaky_task_handler)
    registry.register("failing_task")(failing_task_handler)
    
    # Create worker with retry policy
    backend = InMemoryBackend()
    retry_policy = simple_retry_policy(max_retries=5)
    worker = Worker(
        backend=backend,
        registry=registry,
        retry_policy=retry_policy,
    )
    
    # Enqueue tasks
    flaky_task = Task(name="flaky_task", payload={"attempt": 1}, max_retries=5)
    failing_task = Task(name="failing_task", payload={}, max_retries=3)
    
    backend.enqueue(flaky_task)
    backend.enqueue(failing_task)
    
    logger.info("Enqueued flaky task and failing task")
    
    # Process tasks
    worker.start()
    time.sleep(3.0)  # Give time for retries
    worker.stop()
    worker.join(timeout=5.0)
    
    # Show results
    logger.info(f"\nStatistics: {worker.get_stats()}")
    logger.info(f"Flaky task: {flaky_task.status} (retries: {flaky_task.retry_count})")
    logger.info(f"Failing task: {failing_task.status} (retries: {failing_task.retry_count})")


# Demo 3: Worker with Middleware
def demo_worker_with_middleware():
    """Demonstrate middleware integration."""
    logger.info("\n" + "="*60)
    logger.info("Demo 3: Worker with Middleware")
    logger.info("="*60 + "\n")
    
    # Create registry
    registry = TaskRegistry()
    registry.register("process_data")(process_data_handler)
    registry.register("slow_task")(slow_task_handler)
    
    # Create worker with middleware
    backend = InMemoryBackend()
    middleware = [
        LoggingMiddleware(level=logging.INFO),
        TimingMiddleware(),
    ]
    worker = Worker(
        backend=backend,
        registry=registry,
        middleware=middleware,
    )
    
    # Enqueue tasks
    task1 = Task(name="process_data", payload={"data": 42})
    task2 = Task(name="slow_task", payload={"duration": 1.5})
    
    backend.enqueue(task1)
    backend.enqueue(task2)
    
    logger.info("Enqueued tasks with middleware")
    
    # Process tasks
    while worker.process_once():
        pass  # Process all tasks
    
    # Show statistics
    logger.info(f"\nStatistics: {worker.get_stats()}")


# Demo 4: Graceful Shutdown
def demo_graceful_shutdown():
    """Demonstrate graceful shutdown."""
    logger.info("\n" + "="*60)
    logger.info("Demo 4: Graceful Shutdown")
    logger.info("="*60 + "\n")
    
    # Create registry
    registry = TaskRegistry()
    registry.register("slow_task")(slow_task_handler)
    
    # Create worker
    backend = InMemoryBackend()
    worker = Worker(backend=backend, registry=registry)
    
    # Enqueue multiple slow tasks
    for i in range(5):
        task = Task(name="slow_task", payload={"duration": 0.5})
        backend.enqueue(task)
    
    logger.info(f"Enqueued {backend.size()} slow tasks")
    
    # Start worker
    worker.start()
    time.sleep(1.0)  # Let it process a couple tasks
    
    logger.info("Initiating graceful shutdown...")
    worker.stop(timeout=1.0)
    worker.join(timeout=5.0)
    
    logger.info(f"Worker stopped. Statistics: {worker.get_stats()}")
    logger.info(f"Tasks remaining in queue: {backend.size()}")


# Demo 5: Manual Task Processing
def demo_manual_processing():
    """Demonstrate manual task processing (not in worker loop)."""
    logger.info("\n" + "="*60)
    logger.info("Demo 5: Manual Task Processing")
    logger.info("="*60 + "\n")
    
    # Create registry
    registry = TaskRegistry()
    registry.register("process_data")(process_data_handler)
    
    # Create worker (don't start the loop)
    backend = InMemoryBackend()
    worker = Worker(backend=backend, registry=registry)
    
    # Enqueue a task
    task = Task(name="process_data", payload={"data": 100})
    backend.enqueue(task)
    
    logger.info("Processing task manually (not using worker loop)...")
    
    # Process manually
    worker.process_once()
    
    logger.info(f"Task processed: {task.status}, result: {task.result.value}")
    logger.info(f"Statistics: {worker.get_stats()}")


# Demo 6: Factory Function
def demo_factory_function():
    """Demonstrate the create_worker factory function."""
    logger.info("\n" + "="*60)
    logger.info("Demo 6: Factory Function")
    logger.info("="*60 + "\n")
    
    # Create registry
    registry = TaskRegistry()
    registry.register("process_data")(process_data_handler)
    
    # Use factory function
    worker = create_worker(
        registry=registry,
        poll_interval=0.5,
        max_retries=3,
        middleware=[LoggingMiddleware()],
    )
    
    # Add task
    task = Task(name="process_data", payload={"data": 777})
    worker.backend.enqueue(task)
    
    logger.info("Worker created via factory function")
    
    # Process
    worker.process_once()
    
    logger.info(f"Task result: {task.result.value}")


# Demo 7: Adding Middleware Dynamically
def demo_dynamic_middleware():
    """Demonstrate adding middleware after worker creation."""
    logger.info("\n" + "="*60)
    logger.info("Demo 7: Dynamic Middleware Addition")
    logger.info("="*60 + "\n")
    
    # Create registry
    registry = TaskRegistry()
    registry.register("process_data")(process_data_handler)
    
    # Create worker without middleware
    worker = Worker(backend=InMemoryBackend(), registry=registry)
    
    # Add middleware dynamically
    worker.add_middleware(LoggingMiddleware())
    worker.add_middleware(TimingMiddleware())
    
    # Process a task
    task = Task(name="process_data", payload={"data": 999})
    worker.backend.enqueue(task)
    worker.process_once()
    
    logger.info(f"Task processed with dynamically added middleware")
    logger.info(f"Statistics: {worker.get_stats()}")


# Demo 8: Statistics Tracking
def demo_statistics():
    """Demonstrate statistics tracking."""
    logger.info("\n" + "="*60)
    logger.info("Demo 8: Statistics Tracking")
    logger.info("="*60 + "\n")
    
    # Create registry
    registry = TaskRegistry()
    registry.register("process_data")(process_data_handler)
    registry.register("failing_task")(failing_task_handler)
    
    # Create worker
    backend = InMemoryBackend()
    worker = Worker(backend=backend, registry=registry)
    
    # Enqueue mixed tasks
    for i in range(5):
        backend.enqueue(Task(name="process_data", payload={"data": i}))
    
    for _ in range(3):
        backend.enqueue(Task(name="failing_task", payload={}))
    
    logger.info(f"Enqueued {backend.size()} tasks (5 success, 3 failures)")
    
    # Process all tasks
    while worker.process_once():
        pass
    
    # Show detailed statistics
    stats = worker.get_stats()
    logger.info(f"\nDetailed Statistics:")
    logger.info(f"  Tasks Processed: {stats.tasks_processed}")
    logger.info(f"  Tasks Succeeded: {stats.tasks_succeeded}")
    logger.info(f"  Tasks Failed: {stats.tasks_failed}")
    logger.info(f"  Tasks Retried: {stats.tasks_retried}")
    logger.info(f"  Total Execution Time: {stats.total_execution_time:.3f}s")
    logger.info(f"  Started At: {stats.start_time}")
    logger.info(f"  Last Activity: {stats.last_activity_time}")


# Run all demos
def main():
    """Run all demos."""
    logger.info("\n" + "="*60)
    logger.info("WORKER DEMONSTRATIONS")
    logger.info("="*60)
    
    try:
        demo_basic_worker()
        demo_worker_with_retry()
        demo_worker_with_middleware()
        demo_graceful_shutdown()
        demo_manual_processing()
        demo_factory_function()
        demo_dynamic_middleware()
        demo_statistics()
        
        logger.info("\n" + "="*60)
        logger.info("ALL DEMOS COMPLETED SUCCESSFULLY")
        logger.info("="*60 + "\n")
        
    except Exception as e:
        logger.error(f"\nDemo failed with error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())