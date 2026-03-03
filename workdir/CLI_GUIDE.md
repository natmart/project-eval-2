# Python Task Queue CLI Guide

## Overview

The Python Task Queue Library provides a comprehensive command-line interface (CLI) for managing task queues, workers, tasks, and monitoring through the `tq` command.

## Installation

After installing the `python-task-queue` package, the `tq` command will be available:

```bash
pip install python-task-queue
```

## Global Options

- `--config, -c`: Path to a YAML configuration file
- `--log-level, -l`: Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--backend, -b`: Queue backend to use (memory, redis, sqlite)
- `--version`: Show version and exit
- `--help`: Show help message

## Commands

### Worker Commands (`tq worker`)

#### Start a Worker

```bash
tq worker start [OPTIONS]
```

**Options:**
- `--daemon / --no-daemon`: Run worker as a daemon (default: no)
- `--poll-interval, -p`: Polling interval in seconds
- `--max-retries, -r`: Maximum number of retries
- `--tasks-module, -m`: Python module to load task handlers from

**Examples:**
```bash
# Start a worker with default settings
tq worker start

# Start worker with custom poll interval and retries
tq worker start -p 0.5 -r 5

# Start worker loading tasks from a module
tq worker start -m mytasks.py

# Start as a daemon
tq worker start --daemon
```

### Task Commands (`tq task`)

#### Enqueue a Task

```bash
tq task enqueue NAME PAYLOAD [OPTIONS]
```

**Arguments:**
- `NAME`: The name of the registered task handler
- `PAYLOAD`: JSON-formatted payload for the task

**Options:**
- `--priority, -p`: Task priority (lower is higher priority, default: 0)
- `--max-retries, -r`: Maximum number of retries for this task
- `--timeout, -t`: Task timeout in seconds

**Examples:**
```bash
# Enqueue a simple task
tq task enqueue greet '{"name": "Alice"}'

# Enqueue with priority and retries
tq task enqueue send_email '{"to": "bob@example.com", "subject": "Hello"}' -p 1 -r 5

# Enqueue with timeout
tq task enqueue process_data '{"data": 123}' -t 60
```

#### List Tasks

```bash
tq task list [OPTIONS]
```

**Options:**
- `--status, -s`: Filter by task status (pending, running, completed, failed, retrying)
- `--limit, -l`: Maximum number of tasks to show (default: 50)
- `--output, -o`: Output format (table, json, default: table)

**Examples:**
```bash
# List all pending tasks
tq task list -s pending

# List last 20 completed tasks
tq task list --status completed --limit 20

# Export task list as JSON
tq task list --output json > tasks.json
```

#### Inspect a Task

```bash
tq task inspect TASK_ID [OPTIONS]
```

**Arguments:**
- `TASK_ID`: UUID of the task to inspect

**Options:**
- `--output, -o`: Output format (table, json, default: table)

**Examples:**
```bash
# Inspect a task (table format)
tq task inspect 550e8400-e29b-41d4-a716-446655440000

# Get task details as JSON
tq task inspect 550e8400-e29b-41d4-a716-446655440000 --output json
```

### Dead Letter Queue Commands (`tq dlq`)

#### List DLQ Tasks

```bash
tq dlq list [OPTIONS]
```

**Options:**
- `--reason, -r`: Filter by failure reason
- `--limit, -l`: Maximum number of tasks to show (default: 50)
- `--output, -o`: Output format (table, json, default: table)

**Examples:**
```bash
# List all failed tasks
tq dlq list

# List tasks that failed due to network errors
tq dlq list --reason "network"

# Export as JSON
tq dlq list --output json
```

#### Replay a DLQ Task

```bash
tq dlq replay DLQ_ID [OPTIONS]
```

**Arguments:**
- `DLQ_ID`: UUID of the DLQ task to replay

**Options:**
- `--reset-retries / --no-reset-retries`: Reset retry count when replaying (default: yes)

**Examples:**
```bash
# Replay a task with retry reset
tq dlq replay 550e8400-e29b-41d4-a716-446655440000

# Replay without reset
tq dlq replay 550e8400-e29b-41d4-a716-446655440000 --no-reset-retries
```

#### Purge a DLQ Task

```bash
tq dlq purge DLQ_ID
```

**Arguments:**
- `DLQ_ID`: UUID of the DLQ task to remove

**Examples:**
```bash
# Remove a task from DLQ
tq dlq purge 550e8400-e29b-41d4-a716-446655440000
```

### Statistics Command

```bash
tq stats [OPTIONS]
```

**Options:**
- `--output, -o`: Output format (table, json, default: table)

**Examples:**
```bash
# Show statistics (table format)
tq stats

# Export statistics as JSON
tq stats --output json > stats.json
```

**Output includes:**
- Total tasks
- Pending tasks
- Running tasks
- Completed tasks
- Failed tasks
- Retrying tasks
- Success rate
- DLQ task count (if available)

## Configuration Files

You can use a YAML configuration file to set default values:

```yaml
# taskqueue.yaml
queue_backend: memory
poll_interval: 1.0
max_retries: 3
log_level: INFO
```

Use the configuration file:

```bash
tq -c taskqueue.yaml worker start
```

## Task Handler Registration

Task handlers must be registered before they can be enqueued. You can register them in your code:

```python
# mytasks.py
from python_task_queue import get_registry

def process_data(payload):
    data = payload.get("data", 0)
    return data * 2

# Register the task
registry = get_registry()
registry.register("process_data")(process_data)
```

Then load the module when starting the worker:

```bash
tq worker start -m mytasks
```

## Environment Variables

You can also configure the CLI using environment variables with the `TASK_QUEUE_` prefix:

```bash
# Set log level to debug
export TASK_QUEUE_LOG_LEVEL=DEBUG

# Set backend
export TASK_QUEUE_QUEUE_BACKEND=redis

# Set max retries
export TASK_QUEUE_MAX_RETRIES=5
```

## Example Workflows

### 1. Basic Task Processing

```bash
# Terminal 1: Start worker
tq worker start -m example_tasks

# Terminal 2: Enqueue tasks
tq task enqueue greet '{"name": "World"}'
tq task enqueue process_data '{"data": 42}'
```

### 2. Monitor Task Progress

```bash
# List all tasks
tq task list

# Inspect a specific task
tq task inspect <task-id>

# Check statistics
tq stats
```

### 3. Handle Failed Tasks

```bash
# List failed tasks in DLQ
tq dlq list

# Replay a failed task
tq dlq replay <dlq-id>

# Or remove it entirely
tq dlq purge <dlq-id>
```

### 4. Production Deployment

```bash
# Create a configuration file
cat > config.yaml << EOF
queue_backend: redis
poll_interval: 0.5
max_retries: 5
log_level: WARNING
EOF

# Start multiple workers
tq -c config.yaml worker start --daemon -p 0.5 &
tq -c config.yaml worker start --daemon -p 0.5 &
tq -c config.yaml worker start --daemon -p 0.5 &
```

## Best Practices

1. **Always use daemon mode for production**: Use `--daemon` or run workers as system services
2. **Set appropriate log levels**: Use WARNING or ERROR in production, DEBUG in development
3. **Monitor statistics**: Regularly check `tq stats` to monitor queue health
4. **Handle DLQ**: Monitor `tq dlq list` for failed tasks and replay or purge as needed
5. **Use configuration files**: Centralize configuration in YAML files for consistency
6. **Set timeouts**: Always specify timeouts for tasks to prevent hangs

## Troubleshooting

### Task Not Registered

If you get "Task is not registered:
- Ensure the task handler is registered
- Use `-m` option to load the module containing task handlers
- Check that the module can be imported correctly

### Worker Won't Start

If the worker fails to start:
- Check log messages for errors
- Verify the queue backend is accessible
- Ensure no other worker is using the same resources

### Task Stuck in Pending

If tasks remain in pending status:
- Ensure at least one worker is running
- Check worker logs for errors
- Verify the task handler is registered

### DLQ Issues

If DLQ is not available:
- Ensure the DLQ module is installed
- Check that the DLQ backend is configured correctly

## Exit Codes

- `0`: Success
- `1`: Error occurred
- `2`: Invalid command or arguments

## Integration with CI/CD

```yaml
# Example GitHub Actions workflow
name: Run Tasks
on: [push]

jobs:
  process:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install dependencies
        run: pip install python-task-queue
      - name: Register and enqueue tasks
        run: |
          python -c "from mytasks import *"
          tq task enqueue process_data '{"data": 123}'
      - name: Process tasks
        run: tq worker start -m mytasks
```

## See Also

- [Python Task Queue Library Documentation](https://github.com/natmart/project-eval-2)
- [Queue Backend Documentation](docs/backends.md)
- [Retry Policy Documentation](docs/retry.md)
- [Middleware Documentation](docs/middleware.md)