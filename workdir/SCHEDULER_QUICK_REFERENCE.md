# Cron Scheduler Quick Reference

## Quick Start

```python
from python_task_queue import CronScheduler, task
from python_task_queue.backends.memory import InMemoryBackend

# 1. Register a task
@task(name="my_task")
def my_task_handler(payload):
    print(f"Executing: {payload}")
    return "done"

# 2. Create scheduler with backend
backend = InMemoryBackend()
scheduler = CronScheduler(backend=backend)

# 3. Add a scheduled job
job = scheduler.add_job(
    task_name="my_task",
    schedule="*/5 * * * *",  # Every 5 minutes
    payload={"message": "Hello"}
)

# 4. Start scheduler
scheduler.start()

# 5. Stop when done
scheduler.stop()
```

## Cron Expressions

Format: `minute hour day_of_month month day_of_week`

| Expression | Description |
|------------|-------------|
| `* * * * *` | Every minute |
| `*/5 * * * *` | Every 5 minutes |
| `*/15 * * * *` | Every 15 minutes |
| `0 * * * *` | Every hour (at 0 minutes) |
| `0 */2 * * *` | Every 2 hours |
| `0 0 * * *` | Every day at midnight |
| `0 12 * * *` | Every day at noon |
| `0 9 * * 1-5` | Every weekday at 9 AM |
| `0 9 * * Mon,Wed,Fri` | Mon/Wed/Fri at 9 AM |
| `0 0 1 * *` | First day of every month |
| `0 0 1 1 *` | January 1st every year |
| `0 */6 * * *` | Every 6 hours |
| `5,10,15 * * * *` | At minutes 5, 10, and 15 |
| `0-10 * * * *` | Every minute from 0-10 |
| `0-10/2 * * * *` | Every 2 minutes from 0-10 |

### Special Characters

- `*` - Wildcard (matches all)
- `*/n` - Every n units
- `n-m` - Range from n to m
- `n1,n2,n3` - List of specific values
- `n-m/x` - Range with step

### Day Names

- `Sun` or `0` - Sunday
- `Mon` or `1` - Monday
- `Tue` or `2` - Tuesday
- `Wed` or `3` - Wednesday
- `Thu` or `4` - Thursday
- `Fri` or `5` - Friday
- `Sat` or `6` - Saturday

### Month Names

- `Jan` - January
- `Feb` - February
- `Mar` - March
- `Apr` - April
- `May` - May
- `Jun` - June
- `Jul` - July
- `Aug` - August
- `Sep` - September
- `Oct` - October
- `Nov` - November
- `Dec` - December

## API Reference

### CronScheduler

```python
CronScheduler(
    registry: Optional[TaskRegistry] = None,
    backend: Optional[QueueBackend] = None,
    check_interval: float = 1.0
)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `add_job(task_name, schedule, payload, job_id, enabled, metadata)` | Add a scheduled job |
| `remove_job(job_id)` | Remove a job |
| `get_job(job_id)` | Get a job by ID |
| `list_jobs(enabled_only=False)` | List all jobs |
| `enable_job(job_id)` | Enable a job |
| `disable_job(job_id)` | Disable a job |
| `start()` | Start the scheduler |
| `stop(timeout=None)` | Stop the scheduler |
| `is_running()` | Check if running |

### ScheduledJob

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | str | Unique job identifier |
| `task_name` | str | Name of the task |
| `schedule` | str | Cron expression |
| `payload` | Any | Task payload |
| `last_run` | datetime | Last execution time |
| `next_run` | datetime | Next scheduled time |
| `enabled` | bool | Whether job is enabled |
| `metadata` | dict | Custom metadata |

### CronSchedule

```python
CronSchedule(expression: str)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `should_run(dt: datetime) -> bool` | Check if should run at given time |
| `next_run_time(from_time: datetime) -> datetime` | Calculate next run time |

## Common Patterns

### Daily Backup at 2 AM

```python
job = scheduler.add_job(
    task_name="backup_database",
    schedule="0 2 * * *",
    payload={"type": "full"}
)
```

### Hourly Report

```python
job = scheduler.add_job(
    task_name="generate_report",
    schedule="0 * * * *",
    payload={"granularity": "hourly"}
)
```

### Weekly Cleanup on Sunday at 3 AM

```python
job = scheduler.add_job(
    task_name="cleanup_old_files",
    schedule="0 3 * * Sun",
    payload={"max_age_days": 30}
)
```

### Monthly Invoice Generation on 1st at 9 AM

```python
job = scheduler.add_job(
    task_name="generate_invoices",
    schedule="0 9 1 * *",
    metadata={"process": "billing"}
)
```

### Every 15 Minutes During Business Hours

```python
# Monday to Friday, 9 AM to 5 PM, every 15 minutes
# Note: This requires multiple jobs
for hour in range(9, 17):
    job = scheduler.add_job(
        task_name="check_status",
        schedule=f"*/15 {hour} * * 1-5"
    )
```

### Multiple Time Zones

```python
# Run at 9 AM in different regions
scheduler.add_job("task_1", "0 9 * * *")      # Local time
scheduler.add_job("task_2", "0 9 * * *", payload={"tz": "UTC"})
scheduler.add_job("task_3", "0 17 * * *")     # 5 PM local
```

## Job Management

### Add Job with Custom ID

```python
job = scheduler.add_job(
    task_name="important_task",
    schedule="0 0 * * *",
    job_id="daily-important-task",
    metadata={"priority": "high"}
)
```

### Temporarily Disable Job

```python
scheduler.disable_job(job.id)
# ... later ...
scheduler.enable_job(job.id)
```

### Monitor Job Status

```python
job = scheduler.get_job(job_id)
print(f"Enabled: {job.enabled}")
print(f"Last run: {job.last_run}")
print(f"Next run: {job.next_run}")
```

### List Jobs

```python
# All jobs
all_jobs = scheduler.list_jobs()

# Only enabled jobs
enabled_jobs = scheduler.list_jobs(enabled_only=True)

# Jobs by task name
email_jobs = [j for j in scheduler.list_jobs() if j.task_name == "send_email"]
```

## Context Manager

```python
# Automatically stop when exiting
with CronScheduler(backend=backend) as scheduler:
    scheduler.add_job("task_name", "* * * * *")
    # Scheduler runs here
    time.sleep(60)
# Scheduler stopped automatically
```

## Integration with Backend

```python
from python_task_queue.backends.memory import InMemoryBackend

# Create backend
backend = InMemoryBackend()

# Create scheduler with backend
scheduler = CronScheduler(backend=backend)

# Add job
job = scheduler.add_job("task_name", "*/5 * * * *")

# Start scheduler
scheduler.start()

# Tasks are enqueued to the backend
scheduler.stop()

# Process enqueued tasks
while backend.size() > 0:
    task = backend.dequeue()
    # Process task...
```

## Error Handling

```python
from python_task_queue.scheduler import InvalidScheduleError, SchedulerError

try:
    job = scheduler.add_job("task", "invalid schedule")
except InvalidScheduleError as e:
    print(f"Invalid schedule: {e}")

try:
    scheduler.stop()
except SchedulerNotRunningError:
    print("Scheduler not running")
```

## Best Practices

1. **Use Descriptive Job IDs**
   ```python
   job = scheduler.add_job(
       "backup",
       "0 2 * * *",
       job_id="daily-db-backup"  # Descriptive ID
   )
   ```

2. **Add Metadata for Tracking**
   ```python
   job = scheduler.add_job(
       "report",
       "0 9 * * *",
       metadata={
           "category": "reporting",
           "critical": True,
           "contact": "admin@example.com"
       }
   )
   ```

3. **Validate Tasks Before Scheduling**
   ```python
   from python_task_queue.registry import get_registry

   registry = get_registry()
   if not registry.contains("my_task"):
       print("Task not registered!")
   ```

4. **Handle Exceptions in Task Handlers**
   ```python
   @task(name="safe_task")
   def safe_task_handler(payload):
       try:
           # Task logic
           return result
       except Exception as e:
           logger.error(f"Task failed: {e}")
           raise
   ```

5. **Use Appropriate Check Intervals**
   ```python
   # For high-frequency jobs: check frequently
   scheduler = CronScheduler(check_interval=0.5)  # 0.5 seconds

   # For low-frequency jobs: check less frequently
   scheduler = CronScheduler(check_interval=5.0)  # 5 seconds
   ```

## Tips and Tricks

### Check Next Run Time

```python
from python_task_queue.scheduler import CronSchedule

schedule = CronSchedule("0 9 * * *")
next_run = schedule.next_run_time()
print(f"Next run: {next_run}")
```

### Test if Schedule Should Run

```python
from datetime import datetime

schedule = CronSchedule("0 9 * * 1-5")  # Weekdays at 9 AM

test_time = datetime(2024, 1, 15, 9, 0)  # Monday at 9 AM
if schedule.should_run(test_time):
    print("Should run at this time")
```

### Bulk Job Operations

```python
# Disable all weekend jobs
weekend_jobs = [
    j for j in scheduler.list_jobs()
    if j.schedule.endswith("6") or j.schedule.endswith("Sun")
]

for job in weekend_jobs:
    scheduler.disable_job(job.id)
```

## Troubleshooting

### Jobs Not Executing

1. Check if scheduler is running: `scheduler.is_running()`
2. Verify task is registered in registry
3. Check job is enabled: `job.enabled`
4. Verify backend is configured
5. Check cron expression is valid

### Schedule Not Expected

1. Verify cron expression format
2. Check timezone (scheduler uses local time)
3. Verify check_interval is appropriate
4. Check system clock

### High CPU Usage

1. Increase `check_interval`
2. Reduce number of jobs
3. Use fewer wildcard patterns

## Examples See Also

- `demo_scheduler.py` - Full demonstration script
- `test_scheduler.py` - Comprehensive test examples
- `SCHEDULER_IMPLEMENTATION_SUMMARY.md` - Implementation details