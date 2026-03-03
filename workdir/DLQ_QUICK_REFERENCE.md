# Dead Letter Queue - Quick Reference

## Installation

No additional installation needed - DLQ is part of python_task_queue.

## Basic Setup

```python
from python_task_queue import (
    DeadLetterQueue,
    Task,
)

# Initialize DLQ (uses memory backend by default)
dlq = DeadLetterQueue()

# Or create with specific backend type
dlq = create_dlq(backend_type="memory")
```

## Common Operations

### Add Failed Task to DLQ

```python
# Create and fail a task
task = Task(name="my_task", payload={"data": "value"})
task.fail(error="Task failed", error_type="ValueError")

# Add to DLQ
dead_letter = dlq.add_failed_task(
    task=task,
    original_queue="main",          # Optional: source queue
    reason="max_retries_exceeded",  # Required: failure reason
    error_message="Service down",   # Optional: error details
    error_type="ConnectionError",   # Optional: error type
    metadata={"custom": "data"}     # Optional: additional context
)
```

### Inspect Failed Tasks

```python
# Get all tasks (most recent first)
all_failed = dlq.inspect()

# Get specific number of tasks
recent = dlq.inspect(limit=10)

# Filter by reason
timeout_tasks = dlq.inspect(reason="timeout")

# Filter by queue
main_queue_tasks = dlq.inspect(queue_name="main")

# Combine filters
specific = dlq.inspect(reason="timeout", queue_name="main")

# Get specific task by ID
task = dlq.get_task(dead_letter_id)
```

### Replay Failed Tasks

```python
# Replay with reset retry count
replayed_task = dlq.replay(
    replay_id=dead_letter_id,
    reset_retries=True
)

# Replay with new max retries (auto-increases if not specified)
replayed_task = dlq.replay(
    replay_id=dead_letter_id,
    new_max_retries=10
)

# Replay with higher priority
replayed_task = dlq.replay(
    replay_id=dead_letter_id,
    new_priority=1  # Lower number = higher priority
)

# Combine options
replayed_task = dlq.replay(
    replay_id=dead_letter_id,
    reset_retries=True,
    new_max_retries=5,
    new_priority=1
)

# Replay all tasks
all_replayed = dlq.replay_all(reset_retries=True)

# Replay filtered tasks
timeout_replayed = dlq.replay_filtered(
    reason="timeout",
    reset_retries=True,
    new_max_retries=5
)
```

### Remove/Purge Tasks

```python
# Remove specific task
dlq.purge(dead_letter_id)

# Purge all tasks
count = dlq.purge_all()

# Purge filtered tasks
purged = dlq.purge_filtered(reason="timeout")
purged = dlq.purge_filtered(queue_name="main")
purged = dlq.purge_filtered(reason="timeout", queue_name="main")
```

### Counting & Statistics

```python
# Total count
total = dlq.count()

# Count by reason
timeout_count = dlq.count_by_reason("timeout")

# Count by queue
main_count = dlq.count_by_queue("main")

# Full statistics
stats = dlq.get_statistics()
# Returns dict with:
# {
#     "total_count": int,
#     "queues": {"queue_name": count},
#     "reasons": {"reason": count},
#     "errors": {"error_type": count}
# }
```

## Classes

### DeadLetterQueue

Main DLQ interface.

**Methods:**
- `add_failed_task()` - Add a failed task to DLQ
- `inspect()` - List failed tasks (with optional filters)
- `get_task()` - Get specific task by ID
- `replay()` - Replay a single failed task
- `replay_all()` - Replay all tasks
- `replay_filtered()` - Replay filtered tasks
- `purge()` - Remove specific task
- `purge_all()` - Remove all tasks
- `purge_filtered()` - Remove filtered tasks
- `count()` - Get total count
- `count_by_reason()` - Count by reason
- `count_by_queue()` - Count by queue
- `get_statistics()` - Get full statistics

### DeadLetterTask

Dataclass representing a task in the DLQ.

**Attributes:**
- `id: UUID` - Unique DLQ entry ID
- `task: Task` - Original failed task
- `original_queue: str` - Source queue name
- `reason: str` - Failure reason
- `error_message: str` - Error message
- `error_type: str` - Error type
- `failed_at: datetime` - Failure timestamp
- `retry_count: int` - Attempts before failure
- `metadata: Dict[str, Any]` - Additional context

**Methods:**
- `to_dict()` - Serialize to dictionary
- `from_dict()` - Deserialize from dictionary

### DLQBackend

Abstract interface for DLQ implementations.

### MemoryDLQBackend

In-memory DLQ backend (thread-safe).

## Integration Patterns

### With Task Worker

```python
class Worker:
    def __init__(self):
        self.dlq = DeadLetterQueue()
        self.retry_policy = RetryPolicy(max_retries=3)

    def process(self, task):
        try:
            result = self.execute(task)
            task.complete(result)
        except Exception as e:
            if self.retry_policy.should_retry(task, e):
                task.retry()
                # Reschedule...
            else:
                # Move to DLQ
                self.dlq.add_failed_task(
                    task=task,
                    original_queue="main",
                    error_message=str(e),
                    error_type=type(e).__name__,
                    retry_count=task.retry_count,
                )
```

### Scheduled Replay

```python
# Replay all timeout tasks every hour
import schedule
import time

def replay_timeout_tasks():
    replayed = dlq.replay_filtered(
        reason="timeout",
        reset_retries=True,
        new_max_retries=5
    )
    print(f"Replayed {len(replayed)} timeout tasks")

schedule.every().hour.do(replay_timeout_tasks)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### Monitoring & Alerting

```python
def check_dlq_health():
    stats = dlq.get_statistics()

    # Alert on high total count
    if stats["total_count"] > 100:
        send_alert(f"DLQ has {stats['total_count']} failed tasks")

    # Alert on specific reason
    if stats["reasons"].get("timeout", 0) > 50:
        send_alert("High number of timeout failures")

    # Report statistics
    logger.info(f"DLQ stats: {stats}")
```

## Common Failure Reasons

Use these standard reason codes:

- `max_retries_exceeded` - All retries used
- `timeout` - Task timed out
- `invalid_payload` - Invalid task payload
- `permission_denied` - Insufficient permissions
- `service_not_available` - External service unavailable
- `rate_limit_exceeded` - API rate limit hit
- `validation_failed` - Task validation error

## Task Metadata When Replayed

When a task is replayed, the following metadata is added:

```python
{
    "dlq_replayed_at": "2024-03-03T12:00:00",
    "dlq_original_failed_at": "2024-03-03T10:00:00",
    "dlq_reason": "max_retries_exceeded",
    "dlq_original_retry_count": 3,
    "dlq_original_max_retries": 3,
}
```

## Thread Safety

- `MemoryDLQBackend` is thread-safe
- All operations are atomic
- Multiple workers can safely add/remove tasks concurrently

## Performance Notes

- `MemoryDLQBackend` operations: O(1) for add/get/remove, O(n) for list/filter
- For large DLQs, filter by reason/queue to avoid loading all tasks
- Consider regular purging to manage memory usage
- For production persistence, consider future Redis/SQLite backends

## See Also

- **Complete Documentation**: `DLQ_IMPLEMENTATION_SUMMARY.md`
- **API Reference**: Docstrings in `python_task_queue/dlq.py`
- **Tests**: `tests/test_dlq.py`
- **Examples**: Integration patterns above

## Tips

1. **Set specific reason codes** for better filtering and statistics
2. **Include relevant metadata** when adding to DLQ
3. **Use batch operations** for efficiency (replay_filtered, purge_filtered)
4. **Schedule regular purges** for old DLQ entries
5. **Monitor statistics** for operational insights
6. **Consider underlying issues** before bulk-replaying tasks
7. **Use `new_max_retries`** on replay to avoid immediate re-failure
8. **Leverage replay metadata** to track task history

## Example: Complete Workflow

```python
from python_task_queue import (
    DeadLetterQueue,
    Task,
    TaskStatus,
    create_dlq,
)

# 1. Initialize
dlq = create_dlq(backend_type="memory")

# 2. Simulate task failure
task = Task(name="api_task", payload={"endpoint": "/data"})
task.fail(error="Connection timeout", error_type="TimeoutError")

# 3. Add to DLQ
dead_letter = dlq.add_failed_task(
    task=task,
    original_queue="api_queue",
    reason="timeout",
    error_message="Service unavailable after 30s",
    error_type="TimeoutError",
    retry_count=3,
)

# 4. Inspect
print(f"DLQ count: {dlq.count()}")
stats = dlq.get_statistics()
print(f"Statistics: {stats}")

# 5. Replay with higher priority and more retries
replayed = dlq.replay(
    replay_id=dead_letter.id,
    reset_retries=True,
    new_max_retries=5,
    new_priority=1,  # Higher priority
)

# 6. Use replayed task
print(f"Replayed task: {replayed}")
print(f"Status: {replayed.status}")
print(f"Replay metadata: {replayed.metadata.get('dlq_reason')}")
```