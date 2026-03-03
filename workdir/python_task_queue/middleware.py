"""
Middleware system for the Python Task Queue Library.

This module implements a flexible middleware system using the Chain of Responsibility
pattern. Middleware components can hook into the task execution lifecycle to provide
cross-cutting concerns like logging, timing, error capture, etc.

The middleware system supports:
- Before/after task execution hooks
- Chain of responsibility pattern for ordered composition
- Built-in middleware for logging, timing, and error capture
- Easy extensibility for custom middleware
"""

from __future__ import annotations

import logging
import sys
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type

from python_task_queue.models import Task, TaskStatus


# ============================================================================
# Context Classes
# ============================================================================


@dataclass
class ExecutionContext:
    """
    Context object passed through the middleware chain.

    Contains information about the task being executed and the current
    execution state. Middleware can read and modify this context.

    Attributes:
        task: The task being executed
        start_time: Timestamp when execution started
        end_time: Timestamp when execution completed (None if not completed)
        execution_time: Duration of execution in seconds (None if not completed)
        result: The result of task execution (None if not completed)
        error: Exception if execution failed (None if successful)
        metadata: Additional metadata for middleware to store information
        next_middleware: The next middleware in the chain (for internal use)
    """

    task: Task
    start_time: datetime
    end_time: Optional[datetime] = None
    execution_time: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def record_end(self) -> None:
        """Record the end time and calculate execution duration."""
        self.end_time = datetime.utcnow()
        if self.start_time:
            delta = self.end_time - self.start_time
            self.execution_time = delta.total_seconds()

    def is_complete(self) -> bool:
        """Check if execution has completed (successfully or with error)."""
        return self.end_time is not None

    def is_successful(self) -> bool:
        """Check if execution completed successfully."""
        return self.is_complete() and self.error is None


# ============================================================================
# Middleware Base Classes
# ============================================================================


class Middleware(ABC):
    """
    Abstract base class for middleware components.

    Middleware components are chained together in the Chain of Responsibility
    pattern. Each middleware can:
    - Perform operations before task execution
    - Optionally call the next middleware in the chain
    - Perform operations after task execution
    - Modify the execution result or context

    Implementation Note:
        Subclasses must implement `before_execute` and `after_execute`.
        The `process` method provides the orchestration logic.

    Example:
        >>> class CustomMiddleware(Middleware):
        ...     def before_execute(self, context: ExecutionContext, next: Callable) -> None:
        ...         print(f"Before: {context.task.name}")
        ...         super().before_execute(context, next)
        ...
        ...     def after_execute(self, context: ExecutionContext) -> None:
        ...         print(f"After: {context.task.name}, success={context.is_successful()}")
        ...         super().after_execute(context)
    """

    def __init__(self, next_middleware: Optional[Middleware] = None) -> None:
        """
        Initialize middleware with optional next middleware in chain.

        Args:
            next_middleware: The next middleware to call in the chain
        """
        self.next_middleware = next_middleware

    def before_execute(self, context: ExecutionContext, next_func: Callable) -> None:
        """
        Hook called before task execution.

        This method is called before the task function is executed.
        Subclasses can override this to perform pre-execution logic.

        Args:
            context: The execution context containing task information
            next_func: Function to call the next middleware (must be called to continue chain)
        """
        # Call next middleware in chain
        if self.next_middleware:
            self.next_middleware.before_execute(context, next_func)

    def after_execute(self, context: ExecutionContext) -> None:
        """
        Hook called after task execution.

        This method is called after the task function completes (successfully or not).
        Subclasses can override this to perform post-execution logic.

        Args:
            context: The execution context updated with execution results
        """
        # Call next middleware in chain (in reverse order by default)
        if self.next_middleware:
            self.next_middleware.after_execute(context)

    def process(self, context: ExecutionContext, execute_func: Callable) -> Any:
        """
        Process the task through the middleware chain.

        This method orchestrates the middleware execution:
        1. Calls `before_execute` on all middleware in the chain
        2. Executes the task function
        3. Calls `after_execute` on all middleware in reverse order

        Args:
            context: The execution context
            execute_func: The actual task function to execute

        Returns:
            The result of task execution

        Raises:
            Any exception raised by the task execution
        """
        # Phase 1: Before execution (forward through chain)
        self.before_execute(context, execute_func)

        try:
            # Phase 2: Execute task
            result = execute_func()
            context.result = result
            return result
        except Exception as e:
            context.error = e
            raise
        finally:
            # Phase 3: After execution (reverse through chain happens via recursion)
            self.after_execute(context)


class ConditionalMiddleware(Middleware):
    """
    Middleware wrapper that conditionally applies middleware based on a predicate.

    This allows middleware to be enabled or disabled dynamically based on
    task properties, configuration, or runtime conditions.

    Attributes:
        condition: Function that returns True if the wrapped middleware should be applied
        wrapped: The middleware to conditionally apply

    Example:
        >>> # Only apply timing middleware for high-priority tasks
        >>> conditional = ConditionalMiddleware(
        ...     condition=lambda ctx: ctx.task.priority <= 3,
        ...     wrapped=TimingMiddleware()
        ... )
    """

    def __init__(
        self,
        condition: Callable[[ExecutionContext], bool],
        wrapped: Middleware,
        next_middleware: Optional[Middleware] = None,
    ) -> None:
        """
        Initialize conditional middleware.

        Args:
            condition: Predicate function returning True to apply wrapped middleware
            wrapped: The middleware to conditionally apply
            next_middleware: Next middleware in chain
        """
        super().__init__(next_middleware)
        self.condition = condition
        self.wrapped = wrapped

    def before_execute(self, context: ExecutionContext, next_func: Callable) -> None:
        """Call before_execute only if condition is met."""
        if self.condition(context):
            # Temporarily set next_middleware on wrapped middleware
            old_next = self.wrapped.next_middleware
            self.wrapped.next_middleware = self.next_middleware
            try:
                self.wrapped.before_execute(context, next_func)
            finally:
                self.wrapped.next_middleware = old_next
        else:
            # Skip wrapped middleware, call next directly
            super().before_execute(context, next_func)

    def after_execute(self, context: ExecutionContext) -> None:
        """Call after_execute only if condition is met."""
        if self.condition(context):
            old_next = self.wrapped.next_middleware
            self.wrapped.next_middleware = self.next_middleware
            try:
                self.wrapped.after_execute(context)
            finally:
                self.wrapped.next_middleware = old_next
        else:
            super().after_execute(context)


# ============================================================================
# Built-in Middleware Implementations
# ============================================================================


class LoggingMiddleware(Middleware):
    """
    Middleware that logs task execution events.

    Provides comprehensive logging of task lifecycle events including
    start, completion, failure, and timing information. Supports
    configurable logging levels and custom loggers.

    Attributes:
        logger: Custom logger instance (uses 'task_queue.middleware' by default)
        log_level: Logging level for events
        log_payloads: Whether to include task payloads in logs
        log_metadata: Whether to include task metadata in logs
        log_results: Whether to include task results in logs

    Example:
        >>> middleware = LoggingMiddleware(
        ...     log_payloads=True,
        ...     log_results=True
        ... )
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        log_level: int = logging.INFO,
        log_payloads: bool = False,
        log_metadata: bool = False,
        log_results: bool = False,
        next_middleware: Optional[Middleware] = None,
    ) -> None:
        """
        Initialize logging middleware.

        Args:
            logger: Custom logger (default: 'task_queue.middleware')
            log_level: Logging level for messages
            log_payloads: Include task payloads in logs
            log_metadata: Include task metadata in logs
            log_results: Include task results in logs
            next_middleware: Next middleware in chain
        """
        super().__init__(next_middleware)
        self.logger = logger or logging.getLogger("task_queue.middleware")
        self.log_level = log_level
        self.log_payloads = log_payloads
        self.log_metadata = log_metadata
        self.log_results = log_results

    def before_execute(self, context: ExecutionContext, next_func: Callable) -> None:
        """Log task execution start."""
        # Build log message
        msg_parts = [f"Task started: {context.task.name} (id={context.task.id})"]
        msg_parts.append(f"priority={context.task.priority}")

        if self.log_payloads and context.task.payload is not None:
            msg_parts.append(f"payload={context.task.payload!r}")

        if self.log_metadata and context.task.metadata:
            msg_parts.append(f"metadata={context.task.metadata}")

        self.logger.log(self.log_level, " | ".join(msg_parts))

        # Call next in chain
        super().before_execute(context, next_func)

    def after_execute(self, context: ExecutionContext) -> None:
        """Log task execution completion."""
        # Determine status
        if context.error is None:
            status = "completed"
        else:
            status = "failed"

        # Build log message
        msg_parts = [f"Task {status}: {context.task.name} (id={context.task.id})"]

        if context.execution_time is not None:
            msg_parts.append(f"duration={context.execution_time:.3f}s")

        if self.log_results and context.result is not None and context.error is None:
            msg_parts.append(f"result={context.result!r}")

        if context.error is not None:
            msg_parts.append(f"error_type={type(context.error).__name__}")
            msg_parts.append(f"error={str(context.error)!r}")

        # Log at appropriate level
        if context.error is not None:
            self.logger.error(" | ".join(msg_parts))
        else:
            self.logger.log(self.log_level, " | ".join(msg_parts))

        # Call next in chain
        super().after_execute(context)


class TimingMiddleware(Middleware):
    """
    Middleware that tracks and records task execution timing.

    Measures execution time and stores it in the context metadata.
    Optionally logs timing information and tracks historical statistics.

    Attributes:
        store_in_metadata: Whether to store timing in context.metadata
        timing_key: Key used to store timing in metadata
        log_timing: Whether to log timing information
        enable_histogram: Enable histogram buckets for statistics
        histogram_buckets: Timing buckets in seconds for histogram

    Example:
        >>> middleware = TimingMiddleware(
        ...     log_timing=True,
        ...     enable_histogram=True,
        ...     histogram_buckets=[0.01, 0.1, 1.0, 10.0]
        ... )
    """

    def __init__(
        self,
        store_in_metadata: bool = True,
        timing_key: str = "execution_time_seconds",
        log_timing: bool = False,
        enable_histogram: bool = False,
        histogram_buckets: Optional[List[float]] = None,
        next_middleware: Optional[Middleware] = None,
    ) -> None:
        """
        Initialize timing middleware.

        Args:
            store_in_metadata: Store timing in context.metadata
            timing_key: Metadata key for timing data
            log_timing: Log timing information
            enable_histogram: Enable histogram tracking
            histogram_buckets: Timing bucket thresholds in seconds
            next_middleware: Next middleware in chain
        """
        super().__init__(next_middleware)
        self.store_in_metadata = store_in_metadata
        self.timing_key = timing_key
        self.log_timing = log_timing
        self.enable_histogram = enable_histogram
        self.histogram_buckets = histogram_buckets or [0.01, 0.1, 0.5, 1.0, 5.0, 10.0]

    def process(self, context: ExecutionContext, execute_func: Callable) -> Any:
        """
        Process with timing measurement.

        Overrides the base process to add accurate timing measurement.
        """
        import time

        start_time = time.perf_counter()

        try:
            # Call parent process which handles the chain
            result = super().process(context, execute_func)
            return result
        finally:
            end_time = time.perf_counter()
            execution_time = end_time - start_time

            # Update context
            context.execution_time = execution_time

            # Store in metadata if enabled
            if self.store_in_metadata:
                context.metadata[self.timing_key] = execution_time

                if self.enable_histogram:
                    bucket = self._get_histogram_bucket(execution_time)
                    histogram_key = f"{self.timing_key}_histogram"
                    if histogram_key not in context.metadata:
                        context.metadata[histogram_key] = {}
                    context.metadata[histogram_key][bucket] = (
                        context.metadata[histogram_key].get(bucket, 0) + 1
                    )

            # Log timing if enabled
            if self.log_timing:
                self._log_timing(context)

    def _get_histogram_bucket(self, execution_time: float) -> str:
        """Determine which histogram bucket the execution time falls into."""
        for i, bucket in enumerate(self.histogram_buckets):
            if execution_time < bucket:
                return f"<{bucket}s"
        return f">={self.histogram_buckets[-1]}s"

    def _log_timing(self, context: ExecutionContext) -> None:
        """Log timing information."""
        logger = logging.getLogger("task_queue.timing")

        if context.error is None:
            logger.info(
                f"Task {context.task.name} completed in {context.execution_time:.3f}s"
            )
        else:
            logger.warning(
                f"Task {context.task.name} failed after {context.execution_time:.3f}s"
            )


class ErrorCaptureMiddleware(Middleware):
    """
    Middleware that captures and handles task execution errors.

    Provides detailed error information including stack traces,
    error types, and custom error handling strategies. Can
    optionally send errors to external services or perform
    custom error handling.

    Attributes:
        capture_traceback: Whether to capture full stack traces
        max_traceback_length: Maximum length of captured traceback
        error_handler: Optional custom error handler function
        reraise: Whether to re-raise captured errors (default: True)

    Example:
        >>> def handle_error(context: ExecutionContext, error: Exception) -> None:
        ...     # Send to external monitoring service
        ...     send_alert(f"Task failed: {context.task.name}")
        >>>
        >>> middleware = ErrorCaptureMiddleware(
        ...     capture_traceback=True,
        ...     error_handler=handle_error
        ... )
    """

    def __init__(
        self,
        capture_traceback: bool = True,
        max_traceback_length: int = 10000,
        error_handler: Optional[Callable[[ExecutionContext, Exception], None]] = None,
        reraise: bool = True,
        next_middleware: Optional[Middleware] = None,
    ) -> None:
        """
        Initialize error capture middleware.

        Args:
            capture_traceback: Capture full stack traces
            max_traceback_length: Maximum characters of traceback to store
            error_handler: Custom error handler function
            reraise: Re-raise captured errors after handling
            next_middleware: Next middleware in chain
        """
        super().__init__(next_middleware)
        self.capture_traceback = capture_traceback
        self.max_traceback_length = max_traceback_length
        self.error_handler = error_handler
        self.reraise = reraise
        self.logger = logging.getLogger("task_queue.errors")

    def process(self, context: ExecutionContext, execute_func: Callable) -> Any:
        """
        Process with error capture.

        Overrides base process to capture and handle errors.
        """
        try:
            # Call parent process which handles the chain
            result = super().process(context, execute_func)
            return result
        except Exception as error:
            # Capture error details
            context.error = error

            # Store error in metadata
            context.metadata["error_type"] = type(error).__name__
            context.metadata["error_message"] = str(error)

            if self.capture_traceback:
                tb_str = "".join(traceback.format_exception(
                    type(error), error, error.__traceback__
                ))
                if self.max_traceback_length > 0:
                    tb_str = tb_str[:self.max_traceback_length]
                context.metadata["error_traceback"] = tb_str

            # Log error
            self._log_error(context, error)

            # Call custom error handler if provided
            if self.error_handler:
                try:
                    self.error_handler(context, error)
                except Exception as handler_error:
                    self.logger.error(
                        f"Error in error handler: {handler_error}"
                    )

            # Re-raise if configured
            if self.reraise:
                raise

    def _log_error(self, context: ExecutionContext, error: Exception) -> None:
        """Log captured error."""
        self.logger.error(
            f"Task {context.task.name} (id={context.task.id}) failed: "
            f"{type(error).__name__}: {error}"
        )


class ValidationMiddleware(Middleware):
    """
    Middleware that validates task before execution.

    Performs validation checks on task properties and payload
    before execution. Can prevent execution of invalid tasks.

    Attributes:
        validate_task_properties: Validate task property constraints
        validate_payload: Validate task payload (if validator is set)
        payload_validator: Custom payload validation function
        strict: Throw error on validation failure vs just logging

    Example:
        >>> def validate_user_task(payload: Any) -> bool:
        ...     return isinstance(payload, dict) and 'user_id' in payload
        >>>
        >>> middleware = ValidationMiddleware(
        ...     payload_validator=validate_user_task,
        ...     strict=True
        ... )
    """

    def __init__(
        self,
        validate_task_properties: bool = True,
        validate_payload: bool = True,
        payload_validator: Optional[Callable[[Any], bool]] = None,
        strict: bool = True,
        next_middleware: Optional[Middleware] = None,
    ) -> None:
        """
        Initialize validation middleware.

        Args:
            validate_task_properties: Validate task property constraints
            validate_payload: Validate task payload
            payload_validator: Custom payload validator
            strict: Raise error on validation failure
            next_middleware: Next middleware in chain
        """
        super().__init__(next_middleware)
        self.validate_task_properties = validate_task_properties
        self.validate_payload = validate_payload
        self.payload_validator = payload_validator
        self.strict = strict
        self.logger = logging.getLogger("task_queue.validation")

    def before_execute(self, context: ExecutionContext, next_func: Callable) -> None:
        """
        Validate task before execution.

        Raises ValidationError if validation fails and strict=True.
        """
        validation_errors: List[str] = []

        # Validate task properties
        if self.validate_task_properties:
            property_errors = self._validate_properties(context.task)
            validation_errors.extend(property_errors)

        # Validate payload
        if self.validate_payload:
            payload_errors = self._validate_payload(context.task)
            validation_errors.extend(payload_errors)

        # Handle validation errors
        if validation_errors:
            error_msg = f"Task validation failed: {'; '.join(validation_errors)}"
            context.metadata["validation_errors"] = validation_errors

            if self.strict:
                raise ValueError(error_msg)
            else:
                self.logger.warning(error_msg)

        # Call next in chain if validation passed
        super().before_execute(context, next_func)

    def _validate_properties(self, task: Task) -> List[str]:
        """Validate task properties."""
        errors: List[str] = []

        # Priority range
        if not 1 <= task.priority <= 10:
            errors.append(f"Priority {task.priority} not in range [1, 10]")

        # Name validation
        if not task.name or not task.name.strip():
            errors.append("Task name is empty")

        # Status validation
        if task.status != TaskStatus.PENDING:
            errors.append(f"Task status is {task.status.value}, expected pending")

        return errors

    def _validate_payload(self, task: Task) -> List[str]:
        """Validate task payload."""
        errors: List[str] = []

        # Use custom validator if provided
        if self.payload_validator:
            try:
                is_valid = self.payload_validator(task.payload)
                if not is_valid:
                    errors.append("Payload validation failed")
            except Exception as e:
                errors.append(f"Payload validator error: {e}")

        return errors


class MetricsMiddleware(Middleware):
    """
    Middleware that collects execution metrics.

    Tracks various metrics including success rate, execution times,
    error types, and throughput. Can be used for monitoring and
    performance analysis.

    Attributes:
        metrics_key: Key to store metrics in context metadata
        track_execution_time: Track execution time statistics
        track_error_types: Track error type frequencies
        track_success_rate: Track overall success/failure ratio

    Example:
        >>> middleware = MetricsMiddleware(
        ...     track_execution_time=True,
        ...     track_error_types=True,
        ...     track_success_rate=True
        ... )
    """

    def __init__(
        self,
        metrics_key: str = "metrics",
        track_execution_time: bool = True,
        track_error_types: bool = True,
        track_success_rate: bool = True,
        next_middleware: Optional[Middleware] = None,
    ) -> None:
        """
        Initialize metrics middleware.

        Args:
            metrics_key: Key for metrics in context metadata
            track_execution_time: Track execution time statistics
            track_error_types: Track error type frequencies
            track_success_rate: Track success/failure counts
            next_middleware: Next middleware in chain
        """
        super().__init__(next_middleware)
        self.metrics_key = metrics_key
        self.track_execution_time = track_execution_time
        self.track_error_types = track_error_types
        self.track_success_rate = track_success_rate

    def after_execute(self, context: ExecutionContext) -> None:
        """Collect metrics after execution."""
        # Initialize metrics in context
        if self.metrics_key not in context.metadata:
            context.metadata[self.metrics_key] = {
                "success_count": 0,
                "failure_count": 0,
                "error_types": {},
            }

        metrics = context.metadata[self.metrics_key]

        # Track success/failure
        if context.error is None:
            metrics["success_count"] += 1
        else:
            metrics["failure_count"] += 1

            # Track error types
            if self.track_error_types:
                error_type = type(context.error).__name__
                metrics["error_types"][error_type] = (
                    metrics["error_types"].get(error_type, 0) + 1
                )

        # Track execution time
        if self.track_execution_time and context.execution_time is not None:
            if "execution_times" not in metrics:
                metrics["execution_times"] = []
            metrics["execution_times"].append(context.execution_time)

        # Call next in chain
        super().after_execute(context)


# ============================================================================
# Middleware Pipeline
# ============================================================================


class MiddlewarePipeline:
    """
    Pipeline for composing and executing middleware.

    Provides a fluent interface building middleware chains:
    - Add middleware in order (first added = outermost)
    - Configure ordering and composition
    - Execute tasks through the full chain

    Attributes:
        middleware: List of middleware in the pipeline

    Example:
        >>> pipeline = MiddlewarePipeline()
        >>> pipeline.add(LoggingMiddleware())
        >>> pipeline.add(TimingMiddleware())
        >>> pipeline.add(ErrorCaptureMiddleware())
        >>>
        >>> result = pipeline.execute(task, lambda: expensive_operation())
    """

    def __init__(self, middleware: Optional[List[Middleware]] = None) -> None:
        """
        Initialize middleware pipeline.

        Args:
            middleware: Initial list of middleware (order matters)
        """
        self.middleware: List[Middleware] = middleware or []

    def add(self, middleware: Middleware) -> "MiddlewarePipeline":
        """
        Add middleware to the pipeline.

        Middleware is added to the end of the chain. The order of
        addition determines execution order for before_execute hooks
        and reversed order for after_execute hooks.

        Args:
            middleware: Middleware to add

        Returns:
            Self for method chaining
        """
        self.middleware.append(middleware)
        return self

    def add_multiple(self, *middleware_items: Middleware) -> "MiddlewarePipeline":
        """
        Add multiple middleware at once.

        Args:
            *middleware_items: Middleware to add in order

        Returns:
            Self for method chaining
        """
        self.middleware.extend(middleware_items)
        return self

    def insert(self, index: int, middleware: Middleware) -> "MiddlewarePipeline":
        """
        Insert middleware at specific position.

        Args:
            index: Position to insert at
            middleware: Middleware to insert

        Returns:
            Self for method chaining
        """
        self.middleware.insert(index, middleware)
        return self

    def remove(self, middleware_type: Type[Middleware]) -> "MiddlewarePipeline":
        """
        Remove middleware of type from pipeline.

        Args:
            middleware_type: Type of middleware to remove

        Returns:
            Self for method chaining

        Raises:
            ValueError: If middleware type not found
        """
        for i, m in enumerate(self.middleware):
            if isinstance(m, middleware_type):
                self.middleware.pop(i)
                return self
        raise ValueError(f"Middleware of type {middleware_type.__name__} not found")

    def clear(self) -> "MiddlewarePipeline":
        """
        Clear all middleware from pipeline.

        Returns:
            Self for method chaining
        """
        self.middleware.clear()
        return self

    def _build_chain(self) -> Optional[Middleware]:
        """
        Build the middleware chain from the list.

        Returns:
            The outermost middleware in the chain, or None if empty
        """
        if not self.middleware:
            return None

        # Build chain in reverse order (last middleware becomes innermost)
        chain = None
        for middleware in reversed(self.middleware):
            middleware.next_middleware = chain
            chain = middleware

        return chain

    def execute(
        self,
        task: Task,
        execute_func: Callable[[], Any],
    ) -> Any:
        """
        Execute a task through the middleware pipeline.

        Args:
            task: The task to execute
            execute_func: The task execution function

        Returns:
            The result of task execution

        Raises:
            Any exception from task execution
        """
        # Create execution context
        context = ExecutionContext(task=task, start_time=datetime.utcnow())

        # Build middleware chain
        chain = self._build_chain()

        # Execute with or without middleware
        if chain is None:
            # No middleware, execute directly
            context.record_end()
            try:
                result = execute_func()
                context.result = result
                return result
            except Exception as e:
                context.error = e
                raise
        else:
            # Execute through middleware chain
            result = chain.process(context, execute_func)
            return result

    def __len__(self) -> int:
        """Return number of middleware in pipeline."""
        return len(self.middleware)

    def __repr__(self) -> str:
        """Return string representation."""
        middleware_names = [type(m).__name__ for m in self.middleware]
        return f"MiddlewarePipeline({middleware_names})"


# ============================================================================
# Builder for Middleware Pipeline
# ============================================================================


class MiddlewarePipelineBuilder:
    """
    Builder for creating configured middleware pipelines.

    Provides a fluent API for building pipelines with common
    middleware configurations.

    Example:
        >>> pipeline = (
        >>>     MiddlewarePipelineBuilder()
        >>>     .with_logging()
        >>>     .with_timing()
        >>>     .with_error_capture()
        >>>     .with_metrics()
        >>>     .build()
        >>> )
    """

    def __init__(self) -> None:
        """Initialize builder."""
        self.pipeline = MiddlewarePipeline()

    def with_logging(
        self,
        log_level: int = logging.INFO,
        log_payloads: bool = False,
        log_results: bool = False,
    ) -> "MiddlewarePipelineBuilder":
        """
        Add logging middleware to pipeline.

        Args:
            log_level: Logging level
            log_payloads: Log task payloads
            log_results: Log task results

        Returns:
            Self for chaining
        """
        middleware = LoggingMiddleware(
            log_level=log_level,
            log_payloads=log_payloads,
            log_results=log_results,
        )
        self.pipeline.add(middleware)
        return self

    def with_timing(
        self,
        log_timing: bool = False,
        enable_histogram: bool = True,
    ) -> "MiddlewarePipelineBuilder":
        """
        Add timing middleware to pipeline.

        Args:
            log_timing: Log timing information
            enable_histogram: Enable histogram tracking

        Returns:
            Self for chaining
        """
        middleware = TimingMiddleware(
            log_timing=log_timing,
            enable_histogram=enable_histogram,
        )
        self.pipeline.add(middleware)
        return self

    def with_error_capture(
        self,
        capture_traceback: bool = True,
        error_handler: Optional[Callable[[ExecutionContext, Exception], None]] = None,
    ) -> "MiddlewarePipelineBuilder":
        """
        Add error capture middleware to pipeline.

        Args:
            capture_traceback: Capture stack traces
            error_handler: Custom error handler

        Returns:
            Self for chaining
        """
        middleware = ErrorCaptureMiddleware(
            capture_traceback=capture_traceback,
            error_handler=error_handler,
        )
        self.pipeline.add(middleware)
        return self

    def with_metrics(
        self,
        track_execution_time: bool = True,
        track_error_types: bool = True,
    ) -> "MiddlewarePipelineBuilder":
        """
        Add metrics middleware to pipeline.

        Args:
            track_execution_time: Track execution times
            track_error_types: Track error type frequencies

        Returns:
            Self for chaining
        """
        middleware = MetricsMiddleware(
            track_execution_time=track_execution_time,
            track_error_types=track_error_types,
        )
        self.pipeline.add(middleware)
        return self

    def with_validation(
        self,
        strict: bool = True,
        payload_validator: Optional[Callable[[Any], bool]] = None,
    ) -> "MiddlewarePipelineBuilder":
        """
        Add validation middleware to pipeline.

        Args:
            strict: Raise error on validation failure
            payload_validator: Custom payload validator

        Returns:
            Self for chaining
        """
        middleware = ValidationMiddleware(
            strict=strict,
            payload_validator=payload_validator,
        )
        self.pipeline.add(middleware)
        return self

    def with_custom(
        self,
        middleware: Middleware,
    ) -> "MiddlewarePipelineBuilder":
        """
        Add custom middleware to pipeline.

        Args:
            middleware: Custom middleware instance

        Returns:
            Self for chaining
        """
        self.pipeline.add(middleware)
        return self

    def build(self) -> MiddlewarePipeline:
        """
        Build and return the pipeline.

        Returns:
            Configured middleware pipeline
        """
        return self.pipeline