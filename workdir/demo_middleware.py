#!/usr/bin/env python3
"""
Demonstration of the Middleware System for Python Task Queue Library.

This script showcases:
1. Basic middleware usage
2. Built-in middleware (logging, timing, error capture)
3. Middleware pipeline composition
4. Custom middleware creation
5. Conditional middleware
"""

import logging
import time
from typing import Callable

from python_task_queue import (
    ConditionalMiddleware,
    ErrorCaptureMiddleware,
    ExecutionContext,
    LoggingMiddleware,
    MetricsMiddleware,
    Middleware,
    MiddlewarePipeline,
    MiddlewarePipelineBuilder,
    Task,
    TaskStatus,
    TimingMiddleware,
    ValidationMiddleware,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


# ============================================================================
# Custom Middleware Examples
# ============================================================================


class AuditMiddleware(Middleware):
    """Custom middleware that audits task execution."""

    def __init__(self, audit_log: list = None, next_middleware: Middleware = None):
        super().__init__(next_middleware)
        self.audit_log = audit_log or []

    def before_execute(self, context: ExecutionContext, next_func: Callable) -> None:
        # Log task start
        self.audit_log.append({
            'event': 'task_started',
            'task_name': context.task.name,
            'task_id': str(context.task.id),
            'timestamp': context.start_time.isoformat(),
        })
        print(f"  [AUDIT] Task started: {context.task.name}")
        super().before_execute(context, next_func)

    def after_execute(self, context: ExecutionContext) -> None:
        # Log task completion
        self.audit_log.append({
            'event': 'task_completed' if context.error is None else 'task_failed',
            'task_name': context.task.name,
            'task_id': str(context.task.id),
            'success': context.error is None,
            'execution_time': context.execution_time,
        })
        status = "SUCCESS" if context.error is None else "FAILED"
        print(f"  [AUDIT] Task {status}: {context.task.name}")
        super().after_execute(context)


class RetryMiddleware(Middleware):
    """Custom middleware that automatically retries failed tasks."""

    def __init__(self, max_attempts: int = 3, next_middleware: Middleware = None):
        super().__init__(next_middleware)
        self.max_attempts = max_attempts

    def process(self, context: ExecutionContext, execute_func: Callable):
        attempts = 0
        last_error = None

        while attempts < self.max_attempts:
            attempts += 1

            try:
                # Try to execute
                self.before_execute(context, execute_func)

                try:
                    result = execute_func()
                    context.result = result
                    return result
                except Exception as e:
                    context.error = e
                    last_error = e
                    raise
                finally:
                    self.after_execute(context)

            except Exception as e:
                print(f"  [RETRY] Attempt {attempts}/{self.max_attempts} failed: {e}")

                if attempts < self.max_attempts:
                    # Pause before retry
                    time.sleep(0.1)
                    context.error = None  # Reset error for next attempt
                    continue
                else:
                    # Max attempts reached, raise the last error
                    raise last_error


# ============================================================================
# Task Functions
# ============================================================================


def successful_task():
    """A task that always succeeds."""
    print("  [TASK] Executing successful task...")
    return {"status": "completed", "data": "result_123"}


def slow_task():
    """A task that takes some time."""
    print("  [TASK] Executing slow task (simulating work)...")
    time.sleep(0.2)
    return {"status": "completed", "data": "slow_result"}


def failing_task():
    """A task that always fails."""
    print("  [TASK] Executing failing task...")
    raise ValueError("This task always fails!")


def flaky_task(attempts=[0]):
    """A task that fails the first time but succeeds on retry."""
    print(f"  [TASK] Executing flaky task (attempt {attempts[0] + 1})...")
    attempts[0] += 1

    if attempts[0] == 1:
        raise RuntimeError("First attempt failed!")

    return {"status": "completed", "attempts": attempts[0]}


def invalid_payload_task():
    """A task with validation issues."""
    print("  [TASK] Executing invalid task...")
    return {"data": "should_be_in_metadata_only"}


# ============================================================================
# Demonstrations
# ============================================================================


def demo_basic_middleware():
    """Demonstrate basic middleware usage."""
    print("\n" + "=" * 70)
    print("DEMO 1: Basic Middleware Usage")
    print("=" * 70)

    task = Task(name="basic_task", payload={"key": "value"})

    # Create a simple pipeline
    pipeline = MiddlewarePipeline()
    pipeline.add(LoggingMiddleware(log_level=logging.INFO))

    print("\nExecuting task with logging middleware:")
    result = pipeline.execute(task, successful_task)
    print(f"Result: {result}")


def demo_timing_middleware():
    """Demonstrate timing middleware."""
    print("\n" + "=" * 70)
    print("DEMO 2: Timing Middleware")
    print("=" * 70)

    task = Task(name="slow_task", payload={"speed": "slow"})

    # Create pipeline with timing
    pipeline = MiddlewarePipeline()
    pipeline.add(TimingMiddleware(log_timing=True))

    print("\nExecuting slow task with timing:")
    result = pipeline.execute(task, slow_task)
    print(f"Result: {result}")


def demo_error_capture():
    """Demonstrate error capture middleware."""
    print("\n" + "=" * 70)
    print("DEMO 3: Error Capture Middleware")
    print("=" * 70)

    task = Task(name="failing_task", payload={"will_fail": True})

    # Create pipeline with error capture
    pipeline = MiddlewarePipeline()
    pipeline.add(ErrorCaptureMiddleware(capture_traceback=True))

    print("\nExecuting failing task with error capture:")
    try:
        result = pipeline.execute(task, failing_task)
    except ValueError as e:
        print(f"Caught expected error: {e}")


def demo_validation():
    """Demonstrate validation middleware."""
    print("\n" + "=" * 70)
    print("DEMO 4: Validation Middleware")
    print("=" * 70)

    # Valid task
    valid_task = Task(name="valid_task", payload={"required": "field"})

    def payload_validator(payload):
        return isinstance(payload, dict) and "required" in payload

    pipeline = MiddlewarePipeline()
    pipeline.add(
        ValidationMiddleware(
            payload_validator=payload_validator,
            strict=True
        )
    )

    print("\nValid task:")
    result = pipeline.execute(valid_task, lambda: "success")
    print(f"Result: {result}")

    # Invalid task
    invalid_task = Task(name="invalid_task", payload={"no_required": "field"})

    print("\nInvalid task:")
    try:
        result = pipeline.execute(invalid_task, lambda: "should_not_reach")
        print("ERROR: Should have failed validation!")
    except ValueError as e:
        print(f"Validation failed as expected: {e}")


def demo_pipeline_builder():
    """Demonstrate pipeline builder."""
    print("\n" + "=" * 70)
    print("DEMO 5: Pipeline Builder")
    print("=" * 70)

    task = Task(name="builder_task", payload={"source": "builder"})

    # Build pipeline using builder
    pipeline = (
        MiddlewarePipelineBuilder()
        .with_logging(log_payloads=True)
        .with_timing(log_timing=True)
        .with_error_capture(capture_traceback=False)
        .with_metrics()
        .build()
    )

    print(f"Built pipeline with {len(pipeline)} middleware components")
    print("Executing task:")
    result = pipeline.execute(task, successful_task)
    print(f"Result: {result}")


def demo_custom_middleware():
    """Demonstrate custom middleware."""
    print("\n" + "=" * 70)
    print("DEMO 6: Custom Middleware")
    print("=" * 70)

    task = Task(name="audit_task", payload={"audit": "me"})

    audit_log = []
    pipeline = MiddlewarePipeline()
    pipeline.add(AuditMiddleware(audit_log=audit_log))
    pipeline.add(LoggingMiddleware(log_level=logging.WARNING))  # Higher level

    print("\nExecuting task with audit middleware:")
    result = pipeline.execute(task, successful_task)

    print("\nAudit log:")
    for entry in audit_log:
        print(f"  - {entry}")


def demo_conditional_middleware():
    """Demonstrate conditional middleware."""
    print("\n" + "=" * 70)
    print("DEMO 7: Conditional Middleware")
    print("=" * 70)

    # High priority task (should log)
    high_priority_task = Task(
        name="high_priority_task",
        payload={"priority": "high"},
        priority=2  # Lower number = higher priority
    )

    # Low priority task (should not log)
    low_priority_task = Task(
        name="low_priority_task",
        payload={"priority": "low"},
        priority=8
    )

    logging_middleware = LoggingMiddleware(log_level=logging.INFO)

    # Only apply logging for high priority tasks
    conditional = ConditionalMiddleware(
        condition=lambda ctx: ctx.task.priority <= 5,
        wrapped=logging_middleware
    )

    pipeline = MiddlewarePipeline()
    pipeline.add(conditional)

    print("\nHigh priority task (priority=2, should log):")
    result = pipeline.execute(high_priority_task, successful_task)

    print("\nLow priority task (priority=8, should not log):")
    result = pipeline.execute(low_priority_task, successful_task)


def demo_retry_middleware():
    """Demonstrate retry middleware."""
    print("\n" + "=" * 70)
    print("DEMO 8: Retry Middleware")
    print("=" * 70)

    flaky_task_obj = Task(name="flaky_task", payload={"retries": True})

    pipeline = MiddlewarePipeline()
    pipeline.add(RetryMiddleware(max_attempts=3))
    pipeline.add(LoggingMiddleware(log_level=logging.INFO))

    print("\nExecuting flaky task with retry middleware:")
    result = pipeline.execute(flaky_task_obj, flaky_task)
    print(f"Result: {result}")


def demo_full_pipeline():
    """Demonstrate a comprehensive pipeline."""
    print("\n" + "=" * 70)
    print("DEMO 9: Full Production Pipeline")
    print("=" * 70)

    task = Task(
        name="production_task",
        payload={"user_id": 12345, "action": "process"},
        priority=3
    )

    # Build comprehensive pipeline
    pipeline = MiddlewarePipeline()

    # 1. Validation first
    pipeline.add(
        ValidationMiddleware(
            strict=True,
            payload_validator=lambda p: isinstance(p, dict) and "user_id" in p
        )
    )

    # 2. Logging
    pipeline.add(LoggingMiddleware(log_level=logging.INFO, log_payloads=False))

    # 3. Timing
    pipeline.add(TimingMiddleware(log_timing=False, enable_histogram=True))

    # 4. Metrics
    pipeline.add(MetricsMiddleware())

    # 5. Error capture (outermost, catches everything)
    pipeline.add(ErrorCaptureMiddleware(capture_traceback=True, reraise=True))

    print("\nExecuting task through full pipeline:")
    print(f"Middleware chain: {[m.__class__.__name__ for m in pipeline.middleware]}")

    # Simulate a slow task
    def production_task():
        print("  [TASK] Processing data...")
        time.sleep(0.1)
        return {"status": "success", "processed": True}

    context = pipeline.execute(task, production_task)

    print(f"\nExecution completed!")
    print(f"Execution time: {context.execution_time:.3f}s")
    print(f"Result: {context.result}")

    if "metrics" in context.metadata:
        metrics = context.metadata["metrics"]
        print(f"\nMetrics:")
        print(f"  - Success: {metrics.get('success_count', 0)}")
        print(f"  - Failures: {metrics.get('failure_count', 0)}")


def demo_metrics_collection():
    """Demonstrate metrics collection across multiple tasks."""
    print("\n" + "=" * 70)
    print("DEMO 10: Metrics Collection")
    print("=" * 70)

    pipeline = MiddlewarePipeline()
    pipeline.add(TimingMiddleware())
    pipeline.add(MetricsMiddleware())

    # Execute multiple tasks
    tasks = [
        Task(name="task_1", payload={"id": 1}),
        Task(name="task_2", payload={"id": 2}),
        Task(name="task_3", payload={"id": 3}),
    ]

    print("\nExecuting multiple tasks to collect metrics...")

    # Define functions that take task context
    results = []
    for task in tasks:
        def task_fn(t=task):
            time.sleep(0.05 * t.name.split('_')[1])  # Variable duration
            if int(t.name.split('_')[1]) == 2:
                raise ValueError("Simulated failure")
            return f"result_{t.name}"

        try:
            result = pipeline.execute(task, task_fn)
            results.append((task.name, result, None))
        except Exception as e:
            results.append((task.name, None, str(e)))

    print("\nResults:")
    for name, result, error in results:
        if result:
            print(f"  - {name}: {result}")
        else:
            print(f"  - {name}: FAILED - {error}")

    # Show aggregated metrics
    if results:
        last_context = pipeline.execute(tasks[-1], lambda: "dummy")
        print("\nNote: Metrics are task-specific in the current implementation")


# ============================================================================
# Main
# ============================================================================


def main():
    """Run all demonstrations."""
    print("\n")
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║         Python Task Queue - Middleware System Demo            ║")
    print("╚════════════════════════════════════════════════════════════════╝")

    try:
        demo_basic_middleware()
        demo_timing_middleware()
        demo_error_capture()
        demo_validation()
        demo_pipeline_builder()
        demo_custom_middleware()
        demo_conditional_middleware()
        demo_retry_middleware()
        demo_full_pipeline()
        demo_metrics_collection()

        print("\n" + "=" * 70)
        print("All demonstrations completed successfully!")
        print("=" * 70)
        print("\nKey takeaways:")
        print("  ✓ Middleware provides cross-cutting concerns (logging, timing, etc.)")
        print("  ✓ Chain of responsibility pattern for ordered execution")
        print("  ✓ Built-in middleware for common needs")
        print("  ✓ Easy to create custom middleware")
        print("  ✓ Composable and configurable pipelines")
        print()

    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())