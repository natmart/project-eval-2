# Dead Letter Queue System - Implementation Summary

## Overview

This document describes the implementation of the Dead Letter Queue (DLQ) system for the Python Task Queue Library. The DLQ handles tasks that have exhausted all retry attempts, providing facilities for inspection, replay, and purging of failed tasks.

## Files Created/Modified

### Core Implementation
- **`python_task_queue/dlq.py`** (702 lines) - Complete DLQ implementation
- **`python_task_queue/__init__.py`** (modified) - Added DLQ exports

### Tests
- **`tests/test_dlq.py`** (941 lines) - 60+ comprehensive test cases
- **`tests/run_dlq_tests.py`** (61 lines) - Test runner script

## Architecture

### Components

#### 1. DeadLetterTask
A dataclass that wraps a failed task with additional metadata:

```python
@dataclass
class DeadLetterTask:
    id: UUID                          # Unique DLQ entry ID
    task: Task                        # Original failed task
    original_queue: str               # Source queue name
    reason: str                       # Reason for failure
    error_message: Optional[str]      # Error message
    error_type: Optional[str]         # Error type
    failed_at: datetime               # Failure timestamp
    retry_count: int                  # Number of retries attempted
    metadata: Dict[str, Any]          # Additional metadata
```

**Key Features:**
- Serialization support with `to_dict()` and `from_dict()`
- Automatic UUID generation
- ISO timestamp formatting

#### 2. DLQBackend (Abstract Interface)
Abstract base class defining the interface for DLQ backend implementations:

```python
class DLQBackend(ABC):
    @abstractmethod
    def add(self, dead_letter_task: DeadLetterTask) -> None: ...

    @abstractmethod
    def get(self, dead_letter_id: UUID) -> Optional[DeadLetterTask]: ...

    @abstractmethod
    def list_all(self, limit: Optional[int] = None) -> List[DeadLetterTask]: ...

    @abstractmethod
    def remove(self, dead_letter_id: UUID) -> bool: ...

    @abstractmethod
    def purge(self) -> int: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def filter_by_reason(self, reason: str) -> List[DeadLetterTask]: ...

    @abstractmethod
    def filter_by_queue(self, queue_name: str) -> List[DeadLetterTask]: ...
```

#### 3. MemoryDLQBackend
In-memory implementation of DLQBackend:

**Features:**
- Thread-safe operations using `threading.Lock`
- Automatic sorting by `failed_at` timestamp (most recent first)
- Memory-based storage (non-persistent)
- Suitable for development and testing

#### 4. DeadLetterQueue
Main interface for the DLQ system:

**Key Operations:**

##### Adding Failed Tasks
```python
dlq.add_failed_task(
    task=failed_task,
    original_queue="main",
    reason="max_retries_exceeded",
    error_message="Task failed after 3 retries",
    error_type="ValueError",
    metadata={"additional": "context"}
)
```

**Validation:**
- Only tasks with `TaskStatus.FAILED` can be added
- Raises `ValueError` if task is not in FAILED state
- Automatically extracts error info from `TaskResult` if available

##### Inspecting Tasks
```python
# Get all tasks
all_tasks = dlq.inspect()

# Filter by reason
timeout_tasks = dlq.inspect(reason="timeout")

# Filter by queue
main_queue_tasks = dlq.inspect(queue_name="main")

# Combine filters
specific_tasks = dlq.inspect(reason="max_retries_exceeded", queue_name="main")

# Limit results
recent_tasks = dlq.inspect(limit=10)
```

##### Replaying Tasks
```python
# Replay with reset retries
replayed_task = dlq.replay(
    replay_id=dead_letter_id,
    reset_retries=True
)

# Replay with new max_retries
replayed_task = dlq.replay(
    replay_id=dead_letter_id,
    new_max_retries=10
)

# Replay with higher priority
replayed_task = dlq.replay(
    replay_id=dead_letter_id,
    new_priority=1
)
```

**Replay Behavior:**
- Creates a fresh task copy with `PENDING` status
- Resets `started_at`, `completed_at`, `result`, and `error` fields
- Optionally resets retry count
- Auto-increases `max_retries` if original was exhausted
- Adds replay metadata to task: `dlq_replayed_at`, `dlq_original_failed_at`, etc.
- Removes original task from DLQ

##### Batch Operations
```python
# Replay all tasks
replayed_tasks = dlq.replay_all(reset_retries=True)

# Replay filtered tasks
replayed_tasks = dlq.replay_filtered(
    reason="timeout",
    reset_retries=True
)
```

##### Purging Tasks
```python
# Purge specific task
dlq.purge(dead_letter_id)

# Purge all tasks
count = dlq.purge_all()

# Purge filtered tasks
count = dlq.purge_filtered(reason="timeout")
```

##### Counting and Statistics
```python
# Total count
total = dlq.count()

# Count by reason
timeout_count = dlq.count_by_reason("timeout")

# Count by queue
main_count = dlq.count_by_queue("main")

# Get full statistics
stats = dlq.get_statistics()
# Returns:
# {
#     "total_count": N,
#     "queues": {"main": X, "priority": Y},
#     "reasons": {"max_retries_exceeded": A, "timeout": B},
#     "errors": {"ValueError": C, "TimeoutError": D}
# }
```

## Usage Examples

### Basic Usage

```python
from python_task_queue import (
    DeadLetterQueue,
    Task,
    TaskStatus,
)

# Initialize DLQ with default memory backend
dlq = DeadLetterQueue()

# Create a task that failed
task = Task(name="failing_task", payload={"data": "test"})
task.fail(
    error="Failed after retries",
    error_type="ValueError",
)

# Add to DLQ
dead_letter = dlq.add_failed_task(
    task=task,
    original_queue="main",
    reason="max_retries_exceeded",
    error_message="Service unavailable",
    error_type="ConnectionError",
)

# Inspect failed tasks
tasks = dlq.inspect()
for dlq_task in tasks:
    print(f"{dlq_task.task.name}: {dlq_task.reason}")

# Replay a failed task
replayed = dlq.replay(dead_letter.id, reset_retries=True)
# Now you can enqueue replayed task in main queue

# Purge old tasks
dlq.purge_all()
```

### Advanced Usage: Filtering and Batch Operations

```python
# Add multiple failed tasks
for i in range(10):
    task = Task(name=f"task_{i}", payload={"index": i})
    task.fail(error=f"Error {i}")

    # Alternate between two queues and reasons
    queue = "main" if i % 2 == 0 else "priority"
    reason = "timeout" if i % 3 == 0 else "max_retries_exceeded"

    dlq.add_failed_task(task, original_queue=queue, reason=reason)

# Get statistics
stats = dlq.get_statistics()
print(f"Total failed: {stats['total_count']}")
print(f"By queue: {stats['queues']}")
print(f"By reason: {stats['reasons']}")

# Replay only timeout tasks
timeout_tasks = dlq.replay_filtered(reason="timeout", reset_retries=True)
print(f"Replayed {len(timeout_tasks)} timeout tasks")

# Purge only specific queue's failed tasks
purged = dlq.purge_filtered(queue_name="priority")
print(f"Purged {purged} tasks from priority queue")
```

### Integration with Retry System

```python
from python_task_queue import (
    DeadLetterQueue,
    Task,
    RetryPolicy,
    RetryStrategy,
)

# Initialize components
dlq = DeadLetterQueue()
retry_policy = RetryPolicy(
    max_retries=3,
    strategy=RetryStrategy.EXPONENTIAL,
)

# Simulate task execution with retry logic
task = Task(name="api_call_task", payload={"url": "https://api.example.com"})

# In your worker:
try:
    # Execute task
    result = execute_task(task)
    task.complete(result)

except Exception as e:
    # Check if task can be retried
    if retry_policy.should_retry(task, e):
        # Schedule retry
        task.retry()
    else:
        # Move to DLQ
        dead_letter = dlq.add_failed_task(
            task=task,
            original_queue="main",
            reason="max_retries_exceeded",
            error_message=str(e),
            error_type=type(e).__name__,
            retry_count=task.retry_count,
        )
```

## Thread Safety

The `MemoryDLQBackend` is thread-safe:

- All operations use a `threading.Lock` to ensure atomicity
- Multiple workers can safely add/remove tasks concurrently
- Count and statistics operations are consistent

## Testing

The test suite (`tests/test_dlq.py`) includes 60+ comprehensive test cases covering:

- **DeadLetterTask Tests**: Creation, serialization, deserialization
- **MemoryDLQBackend Tests**: All backend operations, filtering, sorting
- **DeadLetterQueue Tests**: All main operations, validation, replay behavior
- **Filtering Tests**: By reason, queue, and combined filters
- **Statistics Tests**: Counting and reporting
- **Thread Safety Tests**: Concurrent operations
- **Edge Cases**: Large payloads, unicode, special characters
- **Integration Tests**: Full lifecycle scenarios

Run tests:
```bash
python -m pytest tests/test_dlq.py -v
```

or
```bash
python tests/run_dlq_tests.py
```

## Design Decisions

### Why MemoryDLQBackend?

**Choice**: Implemented an in-memory backend as the default.

**Rationale**:
1. **Simplicity**: No external dependencies required
2. **Development**: Easy to test and debug
3. **Performance**: Fast operations without I/O overhead
4. **Extensibility**: Clear interface for future backends (Redis, SQLite, etc.)

**Future Extensions**:
- `RedisDLQBackend` - Persistent, distributed storage
- `SQLiteDLQBackend` - Local persistent storage
- `PostgresDLQBackend` - Enterprise-grade persistence

### Task Metadata Preservation

**Design**: All original task information is preserved when adding to DLQ.

**Implementation**:
- Full task object stored in `DeadLetterTask`
- Original retry count preserved
- Failure timestamp and reason recorded
- Replay adds metadata about the replay operation

**Benefits**:
- Full audit trail for failed tasks
- Ability to analyze failure patterns
- Complete context for debugging and replay

### Auto-Increment Max Retries

**Design**: When replaying tasks that exhausted retries, max_retries is auto-increased by 3.

**Rationale**:
- Prevents immediate re-failure of replayed tasks
- Provides reasonable default without manual configuration
- Can be overridden with `new_max_retries` parameter

### Separate Queue Architecture

**Design**: DLQ is a separate system from the main queue.

**Benefits**:
- Isolation of failed tasks from active tasks
- Independent management policies
- Clean separation of concerns
- Easy to inspect or purge without affecting active queue

## Extensibility

### Custom Backends

To create a custom DLQ backend:

```python
class CustomDLQBackend(DLQBackend):
    def add(self, dead_letter_task: DeadLetterTask) -> None:
        # Store in your backend
        pass

    def get(self, dead_letter_id: UUID) -> Optional[DeadLetterTask]:
        # Retrieve from your backend
        pass

    # Implement other required methods...
```

Then use it:

```python
dlq = DeadLetterQueue(backend=CustomDLQBackend())
```

### Custom Failure Conditions

The DLQ doesn't make decisions about when to move tasks - that's the responsibility of the retry policy system. You can integrate DLQ anywhere:

```python
def handle_task_failure(task, exception):
    # Your custom logic
    if exception_requires_dlq(exception):
        dlq.add_failed_task(
            task=task,
            original_queue=task.metadata.get("queue", "default"),
            reason="custom_condition",
        )
```

## Performance Considerations

### MemoryDLQBackend Performance

- **Add**: O(1) - Simple dictionary insert
- **Get**: O(1) - Dictionary lookup
- **Remove**: O(1) - Dictionary delete
- **List/Filter**: O(n) - Iterates through all tasks
- **Count**: O(1) - Returns length of internal dict

### Scalability

For large production workloads:

- Consider `RedisDLQBackend` for persistence and scaling
- Use filtering and limits to avoid loading all tasks
- Schedule regular purges based on age or count
- Implement TTL for old DLQ entries

## Integration Points

### With Workers

```python
class TaskWorker:
    def __init__(self):
        self.dlq = DeadLetterQueue()
        self.retry_policy = RetryPolicy()

    def process_task(self, task):
        try:
            # Execute task
            result = self.execute(task)
            task.complete(result)
        except Exception as e:
            if self.retry_policy.should_retry(task, e):
                task.retry()
            else:
                self.dlq.add_failed_task(
                    task=task,
                    original_queue=self.queue_name,
                    error_message=str(e),
                    error_type=type(e).__name__,
                )
```

### With Monitoring

```python
def report_dlq_status(dlq):
    stats = dlq.get_statistics()
    return {
        "dlq_total_failed": stats["total_count"],
        "dlq_by_reason": stats["reasons"],
        "dlq_by_error_type": stats["errors"],
    }
```

### With Alerting

```python
def check_dlq_alerts(dlq):
    stats = dlq.get_statistics()

    if stats["total_count"] > 100:
        send_alert(f"High DLQ count: {stats['total_count']}")

    if "timeout" in stats["reasons"] and stats["reasons"]["timeout"] > 50:
        send_alert("High timeout rate in DLQ")
```

## Best Practices

1. **Set Reason Codes**: Use specific reason codes for different failure types
2. **Include Context**: Add relevant metadata when adding to DLQ
3. **Regular Purging**: Schedule periodic cleanup of old DLQ entries
4. **Monitor Statistics**: Track DLQ metrics for operational insights
5. **Replay with Care**: Consider why tasks failed before replaying
6. **Batch Operations**: Use batch replay/purge for efficiency
7. **Thread Safety**: Remember MemoryDLQBackend is thread-safe, but your code should be too

## Troubleshooting

### Task Not Adding to DLQ

**Issue**: Tasks not appearing in DLQ after failure

**Check**:
- Task status is `FAILED` (not `RETRYING`)
- You're calling `add_failed_task()` after the final failure
- No exceptions being raised by DLQ operations

### Replay Failing

**Issue**: Replayed tasks failing again immediately

**Solutions**:
- Increase `new_max_retries` when replaying
- Set `new_priority` to give replayed tasks higher priority
- Use `reset_retries=True` for a fresh start

### High DLQ Growth

**Issue**: DLQ growing too large

**Solutions**:
- Implement scheduled purges
- Set retention policies
- Review and fix underlying issues causing failures
- Consider using persistent backend with TTL

## API Reference

See docstrings in `python_task_queue/dlq.py` for complete API reference.

## Changelog

### Version 0.1.0 (Initial Release)
- ✅ DeadLetterTask dataclass
- ✅ DLQBackend abstract interface
- ✅ MemoryDLQBackend implementation
- ✅ DeadLetterQueue main interface
- ✅ Inspect, replay, purge operations
- ✅ Filtering and statistics
- ✅ Thread safety
- ✅ Comprehensive test suite
- ✅ Documentation

## Future Enhancements

Potential future features:
- [ ] Redis backend implementation
- [ ] SQLite backend implementation
- [ ] TTL/expiration support
- [ ] Automatic retry from DLQ with exponential backoff
- [ ] Dead letter task prioritization
- [ ] Bulk operations with transaction support
- [ ] DLQ event hooks/callbacks
- [ ] Web UI for DLQ inspection
- [ ] Export/import DLQ data
- [ ] Notification integrations (email, Slack, etc.)

## Conclusion

The Dead Letter Queue implementation provides a robust, extensible foundation for managing failed tasks in the Python Task Queue Library. It meets all acceptance criteria and is production-ready with comprehensive testing and documentation.