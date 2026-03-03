"""
Tests for the middleware system.

Tests cover:
- Middleware base class
- MiddlewarePipeline
- LoggingMiddleware
- Execution context
- Middleware chaining
- Error handling
"""

import unittest
import logging
import io
import sys
from typing import Any, Dict
from unittest.mock import Mock, patch, MagicMock

from python_task_queue.middleware import (
    Middleware,
    MiddlewarePipeline,
    LoggingMiddleware,
    ExecutionContext,
)


class TestMiddleware(unittest.TestCase):
    """Tests for the base Middleware class."""

    def test_middleware_before_call(self) -> None:
        """Test before_call method."""

        class TestMiddleware(Middleware):
            def __init__(self, name, tracker):
                super().__init__(name)
                self.tracker = tracker

            def before_call(self, context: ExecutionContext) -> None:
                self.tracker.append("before")
                super().before_call(context)

        tracker = []
        middleware = TestMiddleware("test", tracker)
        context = ExecutionContext(name="test_task", payload={})

        middleware.before_call(context)

        self.assertEqual(tracker, ["before"])

    def test_middleware_after_call(self) -> None:
        """Test after_call method."""

        class TestMiddleware(Middleware):
            def __init__(self, name, tracker):
                super().__init__(name)
                self.tracker = tracker

            def after_call(self, context: ExecutionContext, result: Any) -> Any:
                self.tracker.append("after")
                return super().after_call(context, result)

        tracker = []
        middleware = TestMiddleware("test", tracker)
        context = ExecutionContext(name="test_task", payload={})
        result = "test_result"

        result = middleware.after_call(context, result)

        self.assertEqual(tracker, ["after"])
        self.assertEqual(result, "test_result")

    def test_middleware_on_error(self) -> None:
        """Test on_error method."""

        class TestMiddleware(Middleware):
            def __init__(self, name, tracker):
                super().__init__(name)
                self.tracker = tracker

            def on_error(self, context: ExecutionContext, error: Exception) -> None:
                self.tracker.append(("error", str(error)))
                super().on_error(context, error)

        tracker = []
        middleware = TestMiddleware("test", tracker)
        context = ExecutionContext(name="test_task", payload={})
        error = ValueError("test error")

        middleware.on_error(context, error)

        self.assertEqual(tracker, [("error", "test error")])


class TestExecutionContext(unittest.TestCase):
    """Tests for ExecutionContext."""

    def test_context_creation(self) -> None:
        """Test creating execution context."""
        context = ExecutionContext(
            name="test_task",
            payload={"key": "value"},
            task_id="123",
            metadata={"custom": "data"},
        )

        self.assertEqual(context.name, "test_task")
        self.assertEqual(context.payload, {"key": "value"})
        self.assertEqual(context.task_id, "123")
        self.assertEqual(context.metadata, {"custom": "data"})

    def test_context_with_defaults(self) -> None:
        """Test context with default values."""
        context = ExecutionContext(name="test_task", payload={})

        self.assertEqual(context.name, "test_task")
        self.assertEqual(context.payload, {})
        self.assertIsNone(context.task_id)
        self.assertEqual(context.metadata, {})

    def test_context_set_get(self) -> None:
        """Test setting and getting context values."""
        context = ExecutionContext(name="test", payload={})

        context["custom_key"] = "custom_value"
        self.assertEqual(context["custom_key"], "custom_value")

    def test_context_get_missing_key_default(self) -> None:
        """Test getting missing key with default."""
        context = ExecutionContext(name="test", payload={})

        result = context.get("missing", "default")
        self.assertEqual(result, "default")

    def test_context_get_missing_key_no_default(self) -> None:
        """Test getting missing key without default returns None."""
        context = ExecutionContext(name="test", payload={})

        result = context.get("missing")
        self.assertIsNone(result)


class TestLoggingMiddleware(unittest.TestCase):
    """Tests for LoggingMiddleware."""

    def setUp(self):
        """Set up logging capture."""
        self.log_stream = io.StringIO()
        self.handler = logging.StreamHandler(self.log_stream)
        self.logger = logging.getLogger("python_task_queue.middleware")
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)

    def tearDown(self):
        """Clean up logging."""
        self.logger.removeHandler(self.handler)

    def test_logging_middleware_before_call(self) -> None:
        """Test logging middleware before call."""
        middleware = LoggingMiddleware()
        context = ExecutionContext(name="test_task", payload={"data": "value"})

        middleware.before_call(context)

        logs = self.log_stream.getvalue()
        self.assertIn("test_task", logs)
        self.assertIn("before", logs.lower())

    def test_logging_middleware_after_call(self) -> None:
        """Test logging middleware after call."""
        middleware = LoggingMiddleware()
        context = ExecutionContext(name="test_task", payload={})

        result = middleware.after_call(context, "test_result")

        logs = self.log_stream.getvalue()
        self.assertIn("test_task", logs)
        self.assertEqual(result, "test_result")

    def test_logging_middleware_on_error(self) -> None:
        """Test logging middleware on error."""
        middleware = LoggingMiddleware()
        context = ExecutionContext(name="test_task", payload={})
        error = RuntimeError("test error")

        middleware.on_error(context, error)

        logs = self.log_stream.getvalue()
        self.assertIn("test_task", logs)
        self.assertIn("test error", logs)
        self.assertIn("error", logs.lower())


class TestMiddlewarePipeline(unittest.TestCase):
    """Tests for MiddlewarePipeline."""

    def test_pipeline_creation(self) -> None:
        """Test creating middleware pipeline."""
        mw1 = LoggingMiddleware()
        mw2 = LoggingMiddleware()

        pipeline = MiddlewarePipeline([mw1, mw2])

        self.assertEqual(len(pipeline.middleware), 2)

    def test_pipeline_empty(self) -> None:
        """Test pipeline with no middleware."""
        pipeline = MiddlewarePipeline([])

        context = ExecutionContext(name="test", payload={})
        result = pipeline.execute(context, lambda ctx: "result")

        self.assertEqual(result, "result")

    def test_pipeline_execution_order(self) -> None:
        """Test middleware execute in order."""
        order = []

        class OrderMiddleware(Middleware):
            def before_call(self, context: ExecutionContext) -> None:
                order.append(f"before_{self.name}")

            def after_call(self, context: ExecutionContext, result: Any) -> Any:
                order.append(f"after_{self.name}")
                return result

        mw1 = OrderMiddleware("mw1")
        mw2 = OrderMiddleware("mw2")

        pipeline = MiddlewarePipeline([mw1, mw2])
        context = ExecutionContext(name="test", payload={})

        pipeline.execute(context, lambda ctx: "result")

        expected = ["before_mw1", "before_mw2", "result", "after_mw2", "after_mw1"]
        self.assertEqual(order, expected)

    def test_pipeline_with_error(self) -> None:
        """Test pipeline handles errors correctly."""
        error_handler_called = []

        class ErrorMiddleware(Middleware):
            def on_error(self, context: ExecutionContext, error: Exception) -> None:
                error_handler_called.append(self.name)
                super().on_error(context, error)

        mw = ErrorMiddleware("error_mw")
        pipeline = MiddlewarePipeline([mw])
        context = ExecutionContext(name="test", payload={})

        def failing_handler(ctx):
            raise ValueError("test error")

        with self.assertRaises(ValueError):
            pipeline.execute(context, failing_handler)

        self.assertIn("error_mw", error_handler_called)

    def test_pipeline_middleware_modifies_result(self) -> None:
        """Test middleware can modify result."""
        class ModifyingMiddleware(Middleware):
            def after_call(self, context: ExecutionContext, result: Any) -> Any:
                return f"{result}_modified"

        mw = ModifyingMiddleware("mod")
        pipeline = MiddlewarePipeline([mw])
        context = ExecutionContext(name="test", payload={})

        result = pipeline.execute(context, lambda ctx: "base")

        self.assertEqual(result, "base_modified")

    def test_pipeline_add_middleware(self) -> None:
        """Test adding middleware to pipeline."""
        pipeline = MiddlewarePipeline([])

        mw = LoggingMiddleware()
        pipeline.add(middleware=mw)

        self.assertEqual(len(pipeline.middleware), 1)

    def test_pipeline_remove_middleware(self) -> None:
        """Test removing middleware from pipeline."""
        mw1 = LoggingMiddleware()
        mw2 = LoggingMiddleware()

        pipeline = MiddlewarePipeline([mw1, mw2])
        pipeline.remove(middleware=mw1)

        self.assertEqual(len(pipeline.middleware), 1)

    def test_pipeline_clear(self) -> None:
        """Test clearing all middleware from pipeline."""
        pipeline = MiddlewarePipeline([LoggingMiddleware(), LoggingMiddleware()])

        pipeline.clear()

        self.assertEqual(len(pipeline.middleware), 0)


class TestMiddlewareChaining(unittest.TestCase):
    """Tests for complex middleware chaining."""

    def test_nested_middleware_calls(self) -> None:
        """Test nested middleware execution."""
        calls = []

        class TrackerMiddleware(Middleware):
            def __init__(self, name, tracker):
                super().__init__(name)
                self.tracker = tracker

            def before_call(self, context: ExecutionContext) -> None:
                self.tracker.append(f"{self.name}_before")

            def after_call(self, context: ExecutionContext, result: Any) -> Any:
                self.tracker.append(f"{self.name}_after")
                return result

        mw1 = TrackerMiddleware("mw1", calls)
        mw2 = TrackerMiddleware("mw2", calls)
        mw3 = TrackerMiddleware("mw3", calls)

        pipeline = MiddlewarePipeline([mw1, mw2, mw3])
        context = ExecutionContext(name="test", payload={})

        pipeline.execute(context, lambda ctx: "executed")

        expected = [
            "mw1_before",
            "mw2_before",
            "mw3_before",
            "mw3_after",
            "mw2_after",
            "mw1_after",
        ]
        self.assertEqual(calls, expected)


class TestMiddlewareRealWorldScenarios(unittest.TestCase):
    """Tests for real-world middleware scenarios."""

    def test_authentication_middleware(self) -> None:
        """Test authentication middleware pattern."""

        class AuthMiddleware(Middleware):
            def __init__(self):
                super().__init__("auth")

            def before_call(self, context: ExecutionContext) -> None:
                token = context.payload.get("auth_token")
                if not token:
                    raise ValueError("Authentication required")
                context["user_id"] = "user123"

        class BusinessLogicMiddleware(Middleware):
            def __init__(self):
                super().__init__("business")

            def after_call(self, context: ExecutionContext, result: Any) -> Any:
                return {"user_id": context.get("user_id"), "result": result}

        pipeline = MiddlewarePipeline([
            AuthMiddleware(),
            BusinessLogicMiddleware(),
        ])

        context = ExecutionContext(
            name="protected_task",
            payload={"auth_token": "secret", "data": "value"},
        )

        result = pipeline.execute(context, lambda ctx: ctx.payload["data"])

        self.assertEqual(result["user_id"], "user123")
        self.assertEqual(result["result"], "value")

    def test_metrics_middleware(self) -> None:
        """Test metrics collection middleware."""

        class MetricsMiddleware(Middleware):
            def __init__(self):
                super().__init__("metrics")
                self.metrics = {}

            def before_call(self, context: ExecutionContext) -> None:
                context["start_time"] = 1000

            def after_call(self, context: ExecutionContext, result: Any) -> Any:
                end_time = 1100
                duration = end_time - context.get("start_time", 0)
                task_name = context.name
                if task_name not in self.metrics:
                    self.metrics[task_name] = {"count": 0, "total_duration": 0}
                self.metrics[task_name]["count"] += 1
                self.metrics[task_name]["total_duration"] += duration
                return result

        mw = MetricsMiddleware()
        pipeline = MiddlewarePipeline([mw])

        context = ExecutionContext(name="slow_task", payload={})
        pipeline.execute(context, lambda ctx: "result")

        self.assertEqual(mw.metrics["slow_task"]["count"], 1)
        self.assertEqual(mw.metrics["slow_task"]["total_duration"], 100)


if __name__ == "__main__":
    unittest.main()