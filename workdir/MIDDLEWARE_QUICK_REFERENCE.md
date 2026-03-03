# Middleware System - Quick Reference

## Installation

The middleware system is part of the Python Task Queue Library. No additional installation required.

```python
from python_task_queue import (
    Middleware,
    ExecutionContext,
    MiddlewarePipeline,
    MiddlewarePipelineBuilder,
    LoggingMiddleware,
    TimingMiddleware,
    ErrorCaptureMiddleware,
    MetricsMiddleware,
    ValidationMiddleware,
    ConditionalMiddleware,
    Task,
)
```

## Middleware Classes

### Base Class: Middleware

```python
class CustomMiddleware(Middleware):
    def before_execute(self, context: ExecutionContext, next_func: Callable):
        # Pre-execution logic
        super().before_execute(context, next_func)

    def after_execute(self, context: ExecutionContext):
        # Post-execution logic
        super().after_execute(context)
```

### Built-in Middleware

| Class | Purpose | Key Options |
|-------|---------|-------------|
| `LoggingMiddleware` | Log task events | `log_level`, `log_payloads`, `log_results` |
| `TimingMiddleware` | Measure execution time | `store_in_metadata`, `enable_histogram`, `log_timing` |
| `ErrorCaptureMiddleware` | Capture errors | `capture_traceback`, `error_handler`, `reraise` |
| `MetricsMiddleware` | Collect statistics | `track_execution_time`, `track_error_types` |
| `ValidationMiddleware` | Validate tasks | `strict`, `payload_validator` |
| `ConditionalMiddleware` | Conditional middleware | `condition`, `wrapped` |

## Creating Pipelines

### Direct Construction

```python
pipeline = MiddlewarePipeline()
pipeline.add(LoggingMiddleware())
pipeline.add(TimingMiddleware())
pipeline.add(ErrorCaptureMiddleware())

result = pipeline.execute(task, lambda: do_work())
```

### Using Builder (Fluent API)

```python
pipeline = (
    MiddlewarePipelineBuilder()
    .with_logging(log_payloads=True)
    .with_timing(log_timing=True)
    .with_error_capture()
    .with_metrics()
    .build()
)
```

### Adding Multiple Middleware

```python
pipeline.add_multiple(
    LoggingMiddleware(),
    TimingMiddleware(),
    MetricsMiddleware()
)
```

### Removing Middleware

```python
pipeline.remove(LoggingMiddleware)
```

### Clear All Middleware

```python
pipeline.clear()
```

## ExecutionContext

```python
@dataclass
class ExecutionContext:
    task: Task
    start_time: datetime
    end_time: Optional[datetime] = None
    execution_time: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def record_end(self) -> None:
        # Record end time and calculate duration

    def is_complete(self) -> bool:
        # Check if execution is complete

    def is_successful(self) -> bool:
        # Check if execution was successful
```

## Examples

### Example 1: Basic Logging and Timing

```python
from python_task_queue import MiddlewarePipeline, LoggingMiddleware, TimingMiddleware, Task

pipeline = MiddlewarePipeline()
pipeline.add(LoggingMiddleware(log_level=logging.INFO))
pipeline.add(TimingMiddleware(log_timing=True))

task = Task(name="process_data", payload={"file": "data.csv"})
result = pipeline.execute(task, lambda: process_data("data.csv"))
```

### Example 2: Error Handling

```python
from python_task_queue import ErrorCaptureMiddleware, Task

pipeline = MiddlewarePipeline()
pipeline.add(ErrorCaptureMiddleware(capture_traceback=True))

def my_task():
    raise ValueError("Something went wrong")

try:
    pipeline.execute(Task(name="failing_task"), my_task)
except ValueError:
    print("Task failed, but error was captured")
```

### Example 3: Custom Error Handler

```python
def handler(ctx: ExecutionContext, error: Exception):
    send_alert(f"Task failed: {ctx.task.name}")

pipeline.add(ErrorCaptureMiddleware(error_handler=handler))
```

### Example 4: Validation

```python
def validate_user(payload):
    return isinstance(payload, dict) and "user_id" in payload

pipeline.add(
    ValidationMiddleware(
        payload_validator=validate_user,
        strict=True
    )
)
```

### Example 5: Conditional Middleware

```python
# Only log high-priority tasks
conditional = ConditionalMiddleware(
    condition=lambda ctx: ctx.task.priority <= 3,
    wrapped=LoggingMiddleware()
)

pipeline.add(conditional)
```

### Example 6: Custom Middleware

```python
from python_task_queue import Middleware, ExecutionContext, Task

class AuditMiddleware(Middleware):
    def __init__(self, audit_log: list, **kwargs):
        super().__init__(**kwargs)
        self.audit_log = audit_log

    def after_execute(self, context: ExecutionContext):
        self.audit_log.append({
            'task': context.task.name,
            'success': context.error is None,
            'duration': context.execution_time
        })
        super().after_execute(context)

audit_trail = []
pipeline.add(AuditMiddleware(audit_trail))
```

### Example 7: Full Production Pipeline

```python
pipeline = (
    MiddlewarePipelineBuilder()
    .with_validation(strict=True)
    .with_logging(log_level=logging.INFO)
    .with_timing(log_timing=True, enable_histogram=True)
    .with_metrics()
    .with_error_capture(capture_traceback=True)
    .build()
)

context = pipeline.execute(task, task_func)

# Access metrics
metrics = context.metadata.get("metrics", {})
print(f"Successes: {metrics.get('success_count', 0)}")
print(f"Failures: {metrics.get('failure_count', 0)}")
```

## Best Practices

1. **Order Matters**: Place validation first, logging before timing, error capture last

2. **Use Builder**: Prefer `MiddlewarePipelineBuilder` for readability

3. **Conditional Logic**: Use `ConditionalMiddleware` for task-specific behavior

4. **Fail Fast**: Set validation to strict mode in production

5. **Monitor**: Always include metrics collection in production

6. **Logging**: Balance verbosity - log critical events, not everything

7. **Custom Middleware**: Keep middleware focused on single responsibility

## Common Patterns

### Retry Middleware

```python
class RetryMiddleware(Middleware):
    def __init__(self, max_attempts=3, **kwargs):
        super().__init__(**kwargs)
        self.max_attempts = max_attempts

    def process(self, context: ExecutionContext, execute_func):
        for attempt in range(1, self.max_attempts + 1):
            try:
                return super().process(context, execute_func)
            except Exception as e:
                if attempt == self.max_attempts:
                    raise
                time.sleep(attempt * 0.1)
```

### Rate Limiting

```python
class RateLimitMiddleware(Middleware):
    def __init__(self, max_per_second=10, **kwargs):
        super().__init__(**kwargs)
        self.max_per_second = max_per_second
        self.last_times = []

    def before_execute(self, context: ExecutionContext, next_func):
        now = time.time()
        self.last_times = [t for t in self.last_times if now - t < 1.0]

        if len(self.last_times) >= self.max_per_second:
            raise RuntimeError("Rate limit exceeded")

        self.last_times.append(now)
        super().before_execute(context, next_func)
```

### Result Caching

```python
class CacheMiddleware(Middleware):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cache = {}

    def before_execute(self, context: ExecutionContext, next_func):
        key = context.task.id
        if key in self.cache:
            context.result = self.cache[key]
            context.metadata["cached"] = True
        else:
            super().before_execute(context, next_func)

    def after_execute(self, context: ExecutionContext):
        if context.error is None and context.result is not None:
            self.cache[context.task.id] = context.result
        super().after_execute(context)
```

## Troubleshooting

### Middleware Not Executing
- Check pipeline order
- Ensure `super().before_execute()` and `super().after_execute()` are called

### Errors Not Being Captured
- Ensure `ErrorCaptureMiddleware` is added last
- Check `reraise` parameter

### Timing Inaccurate
- Use `TimingMiddleware` for precise timing
- Avoid slow operations in `before_execute` hooks

### Memory Issues
- Disable `enable_histogram` if not needed
- Clear `metadata` periodically
- Disable `capture_traceback` for large errors

## API Reference

See `python_task_queue/middleware.py` for complete API documentation including:
- All class constructors
- Method signatures
- Type hints
- Docstrings

Run `python demo_middleware.py` for interactive examples.