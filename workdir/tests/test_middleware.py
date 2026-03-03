"""
Tests for the middleware system.

This test suite covers:
- Middleware base class functionality
- Built-in middleware implementations
- Middleware pipeline composition and ordering
- Context propagation
- Error handling
"""

import logging
import logging.handlers
import time
from datetime import datetime
from typing import Any, Callable

import pytest

from python_task_queue.middleware import (
    ConditionalMiddleware,
    ErrorCaptureMiddleware,
    ExecutionContext,
    LoggingMiddleware,
    MetricsMiddleware,
    Middleware,
    MiddlewarePipeline,
    MiddlewarePipelineBuilder,
    TimingMiddleware,
    ValidationMiddleware,
)
from python_task_queue.models import Task, TaskStatus


# ============================================================================
# Test Fixtures
# ============================================================================


class CallOrderMiddleware(Middleware):
    """Middleware that tracks call order for testing."""

    def __init__(self, name: str, calls: list, next_middleware: Middleware = None):
        super().__init__(next_middleware)
        self.name = name
        self.calls = calls
        self.before_called = False
        self.after_called = False

    def before_execute(self, context: ExecutionContext, next_func: Callable) -> None:
        self.before_called = True
        self.calls.append(f"{self.name}.before")
        super().before_execute(context, next_func)

    def after_execute(self, context: ExecutionContext) -> None:
        self.after_called = True
        self.calls.append(f"{self.name}.after")
        super().after_execute(context)


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        name="test_task",
        payload={"data": "test_value"},
        priority=5,
    )


@pytest.fixture
def successful_task_func():
    """A successful task function."""
    return lambda: "success_result"


@pytest.fixture
def failing_task_func():
    """A task function that raises an exception."""
    def failing():
        raise ValueError("Task failed!")
    return failing


# ============================================================================
# ExecutionContext Tests
# ============================================================================


class TestExecutionContext:
    """Tests for ExecutionContext class."""

    def test_initialization(self, sample_task):
        """Test context initialization with task."""
        start_time = datetime.utcnow()
        context = ExecutionContext(task=sample_task, start_time=start_time)

        assert context.task == sample_task
        assert context.start_time == start_time
        assert context.end_time is None
        assert context.execution_time is None
        assert context.result is None
        assert context.error is None
        assert context.metadata == {}

    def test_record_end(self, sample_task):
        """Test recording end time and calculating duration."""
        start_time = datetime.utcnow()
        context = ExecutionContext(task=sample_task, start_time=start_time)

        time.sleep(0.01)  # Small delay
        context.record_end()

        assert context.end_time is not None
        assert context.execution_time is not None
        assert context.execution_time >= 0.01

    def test_is_complete(self, sample_task):
        """Test checking if execution is complete."""
        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        assert not context.is_complete()

        context.record_end()
        assert context.is_complete()

    def test_is_successful(self, sample_task):
        """Test checking if execution is successful."""
        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        assert not context.is_successful()

        context.record_end()
        assert context.is_successful()

        context.error = ValueError("Test error")
        assert not context.is_successful()


# ============================================================================
# Middleware Base Class Tests
# ============================================================================


class TestMiddleware:
    """Tests for Middleware base class."""

    def test_basic_chaining(self, sample_task):
        """Test basic middleware chaining."""
        calls = []
        middleware1 = CallOrderMiddleware("m1", calls)
        middleware2 = CallOrderMiddleware("m2", calls, next_middleware=middleware1)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        middleware2.process(context, lambda: "result")

        # Check that both were called
        assert middleware1.before_called
        assert middleware1.after_called
        assert middleware2.before_called
        assert middleware2.after_called

    def test_call_order(self, sample_task):
        """Test that middleware is called in correct order."""
        calls = []
        m1 = CallOrderMiddleware("m1", calls)
        m2 = CallOrderMiddleware("m2", calls, next_middleware=m1)
        m3 = CallOrderMiddleware("m3", calls, next_middleware=m2)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        m3.process(context, lambda: "result")

        # Before hooks: m3 -> m2 -> m1
        # After hooks: m1 -> m2 -> m3
        expected_calls = [
            "m3.before", "m2.before", "m1.before",  # Before execution
            "m1.after", "m2.after", "m3.after",  # After execution
        ]
        assert calls == expected_calls

    def test_successful_execution(self, sample_task, successful_task_func):
        """Test middleware with successful task execution."""
        calls = []
        middleware = CallOrderMiddleware("test", calls)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        result = middleware.process(context, successful_task_func)

        assert result == "success_result"
        assert context.result == "success_result"
        assert context.error is None

    def test_failed_execution(self, sample_task, failing_task_func):
        """Test middleware with failed task execution."""
        calls = []
        middleware = CallOrderMiddleware("test", calls)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        with pytest.raises(ValueError, match="Task failed!"):
            middleware.process(context, failing_task_func)

        assert context.error is not None
        assert isinstance(context.error, ValueError)


# ============================================================================
# LoggingMiddleware Tests
# ============================================================================


class TestLoggingMiddleware:
    """Tests for LoggingMiddleware."""

    def test_logs_task_start(self, sample_task, successful_task_func, caplog):
        """Test logging task start."""
        middleware = LoggingMiddleware(log_level=20)  # INFO level

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        middleware.process(context, successful_task_func)

        assert any("Task started" in record.message for record in caplog.records)

    def test_logs_task_completion(self, sample_task, successful_task_func, caplog):
        """Test logging task completion."""
        middleware = LoggingMiddleware(log_level=20)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        middleware.process(context, successful_task_func)

        assert any("completed" in record.message for record in caplog.records)

    def test_logs_task_failure(self, sample_task, failing_task_func, caplog):
        """Test logging task failure."""
        middleware = LoggingMiddleware(log_level=20)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        try:
            middleware.process(context, failing_task_func)
        except ValueError:
            pass

        assert any("failed" in record.message for record in caplog.records)

    def test_logs_with_payloads(self, sample_task, successful_task_func, caplog):
        """Test logging with task payloads."""
        middleware = LoggingMiddleware(log_level=20, log_payloads=True)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        middleware.process(context, successful_task_func)

        assert any("payload=" in record.message for record in caplog.records)

    def test_custom_logger(self, sample_task, successful_task_func):
        """Test using custom logger."""
        custom_logger = logging.getLogger("custom.test")
        handler = logging.handlers.MemoryHandler(capacity=100)
        custom_logger.addHandler(handler)

        middleware = LoggingMiddleware(logger=custom_logger)
        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        middleware.process(context, successful_task_func)

        assert len(handler.buffer) > 0


# ============================================================================
# TimingMiddleware Tests
# ============================================================================


class TestTimingMiddleware:
    """Tests for TimingMiddleware."""

    def test_measures_execution_time(self, sample_task):
        """Test that timing middleware measures execution time."""
        middleware = TimingMiddleware()

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        def slow_task():
            time.sleep(0.05)
            return "done"

        result = middleware.process(context, slow_task)

        assert result == "done"
        assert context.execution_time is not None
        assert context.execution_time >= 0.05

    def test_stores_timing_in_metadata(self, sample_task):
        """Test storing timing in context metadata."""
        middleware = TimingMiddleware(store_in_metadata=True, timing_key="my_timing")

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        middleware.process(context, lambda: "result")

        assert "my_timing" in context.metadata
        assert context.metadata["my_timing"] is not None
        assert context.metadata["my_timing"] > 0

    def test_histogram_tracking(self, sample_task):
        """Test histogram tracking of execution times."""
        middleware = TimingMiddleware(
            store_in_metadata=True,
            enable_histogram=True,
            histogram_buckets=[0.01, 0.1, 1.0],
        )

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        middleware.process(context, lambda: "result")

        assert "execution_time_seconds_histogram" in context.metadata
        histogram = context.metadata["execution_time_seconds_histogram"]
        assert len(histogram) > 0

    def test_log_timing(self, sample_task, caplog):
        """Test logging timing information."""
        middleware = TimingMiddleware(log_timing=True)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        middleware.process(context, lambda: "result")

        assert any("completed in" in record.message for record in caplog.records)


# ============================================================================
# ErrorCaptureMiddleware Tests
# ============================================================================


class TestErrorCaptureMiddleware:
    """Tests for ErrorCaptureMiddleware."""

    def test_captures_error(self, sample_task, failing_task_func):
        """Test error capture."""
        middleware = ErrorCaptureMiddleware(capture_traceback=False)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        with pytest.raises(ValueError):
            middleware.process(context, failing_task_func)

        assert context.error is not None
        assert isinstance(context.error, ValueError)

    def test_captures_traceback(self, sample_task, failing_task_func):
        """Test traceback capture."""
        middleware = ErrorCaptureMiddleware(capture_traceback=True)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        with pytest.raises(ValueError):
            middleware.process(context, failing_task_func)

        assert "error_traceback" in context.metadata
        assert context.metadata["error_traceback"] is not None

    def test_stores_error_info_in_metadata(self, sample_task, failing_task_func):
        """Test storing error information in metadata."""
        middleware = ErrorCaptureMiddleware(capture_traceback=False)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        with pytest.raises(ValueError):
            middleware.process(context, failing_task_func)

        assert "error_type" in context.metadata
        assert context.metadata["error_type"] == "ValueError"
        assert "error_message" in context.metadata

    def test_custom_error_handler(self, sample_task, failing_task_func):
        """Test custom error handler."""
        error_captured = []

        def handler(ctx: ExecutionContext, error: Exception):
            error_captured.append((ctx.task.name, type(error).__name__))

        middleware = ErrorCaptureMiddleware(error_handler=handler, reraise=True)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        with pytest.raises(ValueError):
            middleware.process(context, failing_task_func)

        assert len(error_captured) == 1
        assert error_captured[0] == ("test_task", "ValueError")

    def test_no_reraise(self, sample_task, failing_task_func):
        """Test disabling error re-raising."""
        middleware = ErrorCaptureMiddleware(reraise=False)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        # Should not raise error
        result = middleware.process(context, failing_task_func)

        assert context.error is not None
        assert result is None


# ============================================================================
# ValidationMiddleware Tests
# ============================================================================


class TestValidationMiddleware:
    """Tests for ValidationMiddleware."""

    def test_valid_task_passes(self, sample_task, successful_task_func):
        """Test that valid tasks pass validation."""
        middleware = ValidationMiddleware(strict=True)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        result = middleware.process(context, successful_task_func)

        assert result == "success_result"

    def test_invalid_priority_raises(self, sample_task):
        """Test that invalid priority raises error in strict mode."""
        sample_task.priority = 15  # Invalid
        middleware = ValidationMiddleware(strict=True)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        def task_func():
            return "result"

        with pytest.raises(ValueError, match="Priority"):
            middleware.process(context, task_func)

    def test_invalid_name_raises(self, sample_task):
        """Test that invalid name raises error in strict mode."""
        sample_task.name = ""
        middleware = ValidationMiddleware(strict=True)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        with pytest.raises(ValueError, match="name"):
            middleware.process(context, lambda: "result")

    def test_custom_payload_validator(self, sample_task):
        """Test custom payload validator."""
        def validate_payload(payload: Any) -> bool:
            return isinstance(payload, dict) and "data" in payload

        middleware = ValidationMiddleware(payload_validator=validate_payload, strict=True)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        result = middleware.process(context, lambda: "result")

        assert result == "result"

    def test_custom_payload_validator_failure(self, sample_task):
        """Test custom payload validator failure."""
        def validate_payload(payload: Any) -> bool:
            return isinstance(payload, dict) and "required_field" in payload

        middleware = ValidationMiddleware(payload_validator=validate_payload, strict=True)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        with pytest.raises(ValueError, match="validation"):
            middleware.process(context, lambda: "result")

    def test_non_strict_mode(self, sample_task):
        """Test non-strict validation mode."""
        sample_task.priority = 15  # Invalid
        middleware = ValidationMiddleware(strict=False)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        result = middleware.process(context, lambda: "result")

        # Should still execute task
        assert result == "result"
        # But should have validation errors in metadata
        assert "validation_errors" in context.metadata


# ============================================================================
# MetricsMiddleware Tests
# ============================================================================


class TestMetricsMiddleware:
    """Tests for MetricsMiddleware."""

    def test_tracks_success_count(self, sample_task):
        """Test tracking successful task counts."""
        middleware = MetricsMiddleware(metrics_key="my_metrics")

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        middleware.process(context, lambda: "success")

        metrics = context.metadata["my_metrics"]
        assert metrics["success_count"] == 1
        assert metrics["failure_count"] == 0

    def test_tracks_failure_count(self, sample_task, failing_task_func):
        """Test tracking failed task counts."""
        middleware = MetricsMiddleware()

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        try:
            middleware.process(context, failing_task_func)
        except ValueError:
            pass

        metrics = context.metadata["metrics"]
        assert metrics["success_count"] == 0
        assert metrics["failure_count"] == 1

    def test_tracks_error_types(self, sample_task):
        """Test tracking error types."""
        middleware = MetricsMiddleware(track_error_types=True)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        def failing():
            raise ValueError("Test error")

        try:
            middleware.process(context, failing)
        except ValueError:
            pass

        metrics = context.metadata["metrics"]
        assert "error_types" in metrics
        assert metrics["error_types"].get("ValueError", 0) == 1

    def test_tracks_execution_times(self, sample_task):
        """Test tracking execution times."""
        middleware = MetricsMiddleware(track_execution_time=True)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        middleware.process(context, lambda: "result")

        metrics = context.metadata["metrics"]
        assert "execution_times" in metrics
        assert len(metrics["execution_times"]) == 1


# ============================================================================
# ConditionalMiddleware Tests
# ============================================================================


class TestConditionalMiddleware:
    """Tests for ConditionalMiddleware."""

    def test_condition_true_applies_middleware(self, sample_task, caplog):
        """Test that middleware is applied when condition is true."""
        logging_middleware = LoggingMiddleware(log_level=20)

        conditional = ConditionalMiddleware(
            condition=lambda ctx: ctx.task.priority <= 5,
            wrapped=logging_middleware,
        )

        sample_task.priority = 3  # Condition should be true
        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        conditional.process(context, lambda: "result")

        # Should have logged
        assert len(caplog.records) > 0

    def test_condition_false_skips_middleware(self, sample_task, caplog):
        """Test that middleware is skipped when condition is false."""
        logging_middleware = LoggingMiddleware(log_level=20)

        conditional = ConditionalMiddleware(
            condition=lambda ctx: ctx.task.priority <= 5,
            wrapped=logging_middleware,
        )

        sample_task.priority = 8  # Condition should be false
        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())
        conditional.process(context, lambda: "result")

        # Should not have logged
        assert len(caplog.records) == 0


# ============================================================================
# MiddlewarePipeline Tests
# ============================================================================


class TestMiddlewarePipeline:
    """Tests for MiddlewarePipeline."""

    def test_empty_pipeline(self, sample_task):
        """Test pipeline with no middleware."""
        pipeline = MiddlewarePipeline()

        context = pipeline.execute(sample_task, lambda: "result")

        assert context.result == "result"

    def test_add_single_middleware(self, sample_task):
        """Test adding single middleware to pipeline."""
        pipeline = MiddlewarePipeline()
        pipeline.add(LoggingMiddleware(log_level=20))

        # Should not raise
        result = pipeline.execute(sample_task, lambda: "result")
        assert result == "result"

    def test_add_multiple_middleware(self, sample_task):
        """Test adding multiple middleware."""
        pipeline = MiddlewarePipeline()
        pipeline.add(TimingMiddleware())
        pipeline.add(LoggingMiddleware(log_level=20))

        result = pipeline.execute(sample_task, lambda: "result")
        assert result == "result"

    def test_add_multiple_at_once(self, sample_task):
        """Test adding multiple middleware at once."""
        pipeline = MiddlewarePipeline()
        pipeline.add_multiple(
            TimingMiddleware(),
            LoggingMiddleware(log_level=20),
            ErrorCaptureMiddleware(),
        )

        result = pipeline.execute(sample_task, lambda: "result")
        assert result == "result"

    def test_insert_middleware(self, sample_task):
        """Test inserting middleware at specific position."""
        pipeline = MiddlewarePipeline()
        pipeline.add(LoggingMiddleware(log_level=20))
        pipeline.insert(0, TimingMiddleware())

        result = pipeline.execute(sample_task, lambda: "result")
        assert result == "result"

    def test_remove_middleware(self, sample_task):
        """Test removing middleware from pipeline."""
        pipeline = MiddlewarePipeline()
        pipeline.add(LoggingMiddleware(log_level=20))
        pipeline.add(TimingMiddleware())

        pipeline.remove(TimingMiddleware)

        assert len(pipeline.middleware) == 1
        assert not any(isinstance(m, TimingMiddleware) for m in pipeline.middleware)

    def test_remove_nonexistent_raises(self):
        """Test removing non-existent middleware raises error."""
        pipeline = MiddlewarePipeline()

        with pytest.raises(ValueError):
            pipeline.remove(TimingMiddleware)

    def test_clear_pipeline(self, sample_task):
        """Test clearing all middleware."""
        pipeline = MiddlewarePipeline()
        pipeline.add(LoggingMiddleware(log_level=20))
        pipeline.add(TimingMiddleware())

        pipeline.clear()

        assert len(pipeline.middleware) == 0

    def test_pipeline_length(self, sample_task):
        """Test pipeline length."""
        pipeline = MiddlewarePipeline()
        assert len(pipeline) == 0

        pipeline.add(LoggingMiddleware(log_level=20))
        assert len(pipeline) == 1

        pipeline.add(TimingMiddleware())
        assert len(pipeline) == 2

    def test_pipeline_repr(self, sample_task):
        """Test pipeline string representation."""
        pipeline = MiddlewarePipeline()
        pipeline.add(LoggingMiddleware(log_level=20))
        pipeline.add(TimingMiddleware())

        repr_str = repr(pipeline)
        assert "MiddlewarePipeline" in repr_str
        assert "LoggingMiddleware" in repr_str
        assert "TimingMiddleware" in repr_str

    def test_execution_time_tracking_in_pipeline(self, sample_task):
        """Test that execution time is tracked in pipeline."""
        pipeline = MiddlewarePipeline()
        pipeline.add(TimingMiddleware(store_in_metadata=True))

        context = pipeline.execute(sample_task, lambda: "result")

        assert "execution_time_seconds" in context.metadata
        assert context.metadata["execution_time_seconds"] >= 0

    def test_error_propagation_in_pipeline(self, sample_task):
        """Test that errors properly propagate through pipeline."""
        pipeline = MiddlewarePipeline()
        pipeline.add(ErrorCaptureMiddleware(capture_traceback=False))

        def failing():
            raise ValueError("Pipeline error")

        with pytest.raises(ValueError):
            pipeline.execute(sample_task, failing)


# ============================================================================
# MiddlewarePipelineBuilder Tests
# ============================================================================


class TestMiddlewarePipelineBuilder:
    """Tests for MiddlewarePipelineBuilder."""

    def test_build_empty_pipeline(self):
        """Test building empty pipeline."""
        builder = MiddlewarePipelineBuilder()
        pipeline = builder.build()

        assert isinstance(pipeline, MiddlewarePipeline)
        assert len(pipeline) == 0

    def test_with_logging(self):
        """Test builder with logging middleware."""
        builder = MiddlewarePipelineBuilder()
        pipeline = builder.with_logging(log_level=20).build()

        assert len(pipeline) == 1
        assert any(isinstance(m, LoggingMiddleware) for m in pipeline.middleware)

    def test_with_timing(self):
        """Test builder with timing middleware."""
        builder = MiddlewarePipelineBuilder()
        pipeline = builder.with_timing().build()

        assert len(pipeline) == 1
        assert any(isinstance(m, TimingMiddleware) for m in pipeline.middleware)

    def test_with_error_capture(self):
        """Test builder with error capture middleware."""
        builder = MiddlewarePipelineBuilder()
        pipeline = builder.with_error_capture().build()

        assert len(pipeline) == 1
        assert any(isinstance(m, ErrorCaptureMiddleware) for m in pipeline.middleware)

    def test_with_metrics(self):
        """Test builder with metrics middleware."""
        builder = MiddlewarePipelineBuilder()
        pipeline = builder.with_metrics().build()

        assert len(pipeline) == 1
        assert any(isinstance(m, MetricsMiddleware) for m in pipeline.middleware)

    def test_with_validation(self):
        """Test builder with validation middleware."""
        builder = MiddlewarePipelineBuilder()
        pipeline = builder.with_validation().build()

        assert len(pipeline) == 1
        assert any(isinstance(m, ValidationMiddleware) for m in pipeline.middleware)

    def test_with_custom(self):
        """Test builder with custom middleware."""
        custom = LoggingMiddleware(log_level=20)
        builder = MiddlewarePipelineBuilder()
        pipeline = builder.with_custom(custom).build()

        assert len(pipeline) == 1

    def test_chained_configuration(self):
        """Test builder with chained configuration."""
        builder = MiddlewarePipelineBuilder()
        pipeline = (
            builder
            .with_logging()
            .with_timing()
            .with_error_capture()
            .with_metrics()
            .with_validation()
            .build()
        )

        assert len(pipeline) == 5

    def test_built_pipeline_executes(self, sample_task):
        """Test that built pipeline executes correctly."""
        pipeline = (
            MiddlewarePipelineBuilder()
            .with_logging()
            .with_timing()
            .with_error_capture()
            .build()
        )

        result = pipeline.execute(sample_task, lambda: "result")
        assert result == "result"


# ============================================================================
# Integration Tests
# ============================================================================


class TestMiddlewareIntegration:
    """Integration tests for middleware system."""

    def test_full_pipeline_execution(self, sample_task):
        """Test executing a full pipeline with multiple middleware."""
        pipeline = (
            MiddlewarePipelineBuilder()
            .with_logging()
            .with_timing()
            .with_error_capture()
            .with_metrics()
            .build()
        )

        result = pipeline.execute(sample_task, lambda: "success")
        assert result == "success"

    def test_error_handling_through_full_pipeline(self, sample_task):
        """Test error handling through full pipeline."""
        pipeline = (
            MiddlewarePipelineBuilder()
            .with_logging()
            .with_timing()
            .with_error_capture()
            .build()
        )

        def failing():
            raise RuntimeError("Integration test error")

        with pytest.raises(RuntimeError):
            pipeline.execute(sample_task, failing)

    def test_multiple_successful_executions(self, sample_task):
        """Test multiple executions with same pipeline."""
        pipeline = (
            MiddlewarePipelineBuilder()
            .with_timing()
            .with_metrics()
            .build()
        )

        for i in range(3):
            task = Task(name=f"task_{i}", payload={"iteration": i})
            result = pipeline.execute(task, lambda i=i: f"result_{i}")
            assert result == f"result_{i}"

    def test_context_mutation(self, sample_task):
        """Test that middleware can mutate context."""
        context_changes = []

        class MutatingMiddleware(Middleware):
            def before_execute(self, context: ExecutionContext, next_func: Callable) -> None:
                context.metadata["custom_value"] = "mutated"
                super().before_execute(context, next_func)

        pipeline = MiddlewarePipeline()
        pipeline.add(MutatingMiddleware())

        context = pipeline.execute(sample_task, lambda: "result")
        assert "custom_value" in context.metadata
        assert context.metadata["custom_value"] == "mutated"


# ============================================================================
# Edge Cases and Error Conditions
# ============================================================================


class TestMiddlewareEdgeCases:
    """Test edge cases and error conditions."""

    def test_middleware_result_modifier(self, sample_task):
        """Test middleware that modifies task result."""
        class ResultModifierMiddleware(Middleware):
            def after_execute(self, context: ExecutionContext) -> None:
                if context.result is not None:
                    context.result = "modified:" + str(context.result)
                super().after_execute(context)

        pipeline = MiddlewarePipeline()
        pipeline.add(ResultModifierMiddleware())

        result = pipeline.execute(sample_task, lambda: "original")
        assert result == "modified:original"

    def test_deep_middleware_chain(self, sample_task):
        """Test with deeply nested middleware chain."""
        pipeline = MiddlewarePipeline()

        for i in range(10):
            pipeline.add(TimingMiddleware())

        result = pipeline.execute(sample_task, lambda: "result")
        assert result == "result"
        assert len(pipeline) == 10

    def test_empty_task_name_validation(self, sample_task):
        """Test handling of empty task name in validation."""
        sample_task.name = ""
        middleware = ValidationMiddleware(strict=True)

        context = ExecutionContext(task=sample_task, start_time=datetime.utcnow())

        with pytest.raises(ValueError, match="name"):
            middleware.process(context, lambda: "result")