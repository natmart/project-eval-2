# Python Task Queue Library

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Development Status](https://img.shields.io/badge/status-alpha-orange.svg)](https://github.com/natmart/project-eval-2)

A flexible, production-ready task queue library for Python with pluggable backends, supporting retry logic, middleware, task registration, and comprehensive monitoring.

## Features

- **Pluggable Backend Architecture** - Support for in-memory, SQLite, Redis, and custom backends
- **Smart Retry System** - Configurable retry policies with exponential backoff
- **Task Registry** - Easy task registration and discovery
- **Middleware Pipeline** - Request/response processing hooks for logging, timing, authentication
- **Dead Letter Queue** - Automatic handling of permanently failed tasks with replay support
- **Cron Scheduler** - Scheduled task execution using cron syntax
- **CLI Tools** - Complete command-line interface for managing queues and workers
- **Worker Pooling** - Efficient task processing with graceful shutdown
- **Comprehensive Monitoring** - Built-in statistics and metrics
- **Configuration Management** - YAML-based configuration with environment variable support

## Installation

Install the package via pip:

```bash
pip install python-task-queue
```

For development:

```bash
git clone https://github.com/natmart/project-eval-2.git
cd project-eval-2
pip install -e ".[dev]"
```

### Optional Dependencies

For specific backends, install additional packages:

```bash
# Redis backend support
pip install redis

# SQLite backend (included with Python)
# No additional installation needed
```

## Quickstart

Get started in under 5 minutes with this simple example:

```python
# example.py
from python_task_queue import Task, InMemoryBackend, Worker, TaskRegistry
import time

# Create a queue backend
backend = InMemoryBackend()

# Create a task registry and register tasks
registry = TaskRegistry()

@registry.register("greet")
def greet(name):
    """Simple greeting task."""
    return f"Hello, {name}!"

@registry.register("process_data")
def process_data(data):
    """Process data task."""
    return {"result": data * 2}

# Create and enqueue tasks
task1 = Task(name="greet", payload={"name": "Alice"})
task2 = Task(name="process_data", payload={"data": 21})

backend.enqueue(task1)
backend.enqueue(task2)

# Create and start worker
worker = Worker(
    backend=backend,
    registry=registry,
    poll_interval=1.0
)

# Worker processes 2 tasks then stops
worker.process_tasks(num_tasks=2, stop_on_empty=True)
```

Run the example:

```bash
python example.py
```

You should see output like:

```
2024-01-15 10:30:00 - INFO - Processing task: greet
2024-01-15 10:30:00 - INFO - Task completed: greet - Hello, Alice!
2024-01-15 10:30:00 - INFO - Processing task: process_data
2024-01-15 10:30:00 - INFO - Task completed: process_data - {'result': 42}
```

## Usage Examples

### Basic Task Enqueue and Process

```python
from python_task_queue import Task, InMemoryBackend, Worker, TaskRegistry

backend = InMemoryBackend()
registry = TaskRegistry()

@registry.register("send_email")
def send_email(to, subject, body):
    """Send email task."""
    print(f"Sending email to {to}: {subject}")
    return {"status": "sent", "to": to}

# Enqueue task
task = Task(
    name="send_email",
    payload={
        "to": "user@example.com",
        "subject": "Welcome!",
        "body": "Thanks for signing up."
    }
)
backend.enqueue(task)

# Create worker and process
worker = Worker(backend=backend, registry=registry)
worker.process_tasks(num_tasks=1)
```

### Using Retry Policies

```python
from python_task_queue import (
    Task, InMemoryBackend, Worker, TaskRegistry,
    simple_retry_policy, aggressive_retry_policy
)

backend = InMemoryBackend()
registry = TaskRegistry()

# Apply retry policy to a task
@registry.register("fetch_data", retry_policy=aggressive_retry_policy)
def fetch_data(url):
    """Fetch data from URL with automatic retries."""
    import requests
    response = requests.get(url, timeout=5)
    return response.json()

task = Task(name="fetch_data", payload={"url": "https://api.example.com/data"})
backend.enqueue(task)

worker = Worker(backend=backend, registry=registry)
worker.process_tasks(num_tasks=1)
```

### Using Middleware

```python
from python_task_queue import (
    Task, InMemoryBackend, Worker, TaskRegistry,
    LoggingMiddleware, MiddlewarePipeline
)
import time

# Custom timing middleware
class TimingMiddleware:
    def before_execution(self, context):
        context.metadata["start_time"] = time.time()
    
    def after_execution(self, context):
        elapsed = time.time() - context.metadata["start_time"]
        print(f"Task {context.task.name} took {elapsed:.3f}s")

# Create middleware pipeline
pipeline = MiddlewarePipeline([
    LoggingMiddleware(),
    TimingMiddleware()
])

backend = InMemoryBackend()
registry = TaskRegistry()

@registry.register("calculate")
def compute_expensive_calculation(n):
    """Task with middleware hooks."""
    return sum(range(n))

worker = Worker(
    backend=backend,
    registry=registry,
    middleware_pipeline=pipeline
)

task = Task(name="calculate", payload={"n": 1000000})
backend.enqueue(task)
worker.process_tasks(num_tasks=1)
# Output: Task calculate took 0.123s
```

### Dead Letter Queue

```python
from python_task_queue import (
    Task, InMemoryBackend, Worker, TaskRegistry,
    DeadLetterQueue, MemoryDLQBackend
)

backend = InMemoryBackend()
dlq_backend = MemoryDLQBackend()
dlq = DeadLetterQueue(backend=dlq_backend)
registry = TaskRegistry()

@registry.register("failing_task")
def failing_task():
    """Task that always fails."""
    raise ValueError("This task always fails!")

# Enqueue task
task = Task(name="failing_task", payload={})
backend.enqueue(task)

# Create worker with DLQ
worker = Worker(
    backend=backend,
    registry=registry,
    dlq=dlq,
    max_retries=3
)
worker.process_tasks(num_tasks=1)

# Inspect failed tasks
failed = dlq.list_all()
print(f"Failed tasks: {len(failed)}")
for item in failed:
    print(f"Task: {item.task.name}, Error: {item.error}")

# Replay failed task
dlq.replay(item.task.id)
```

### Scheduled Tasks with Cron

```python
from python_task_queue import (
    Task, InMemoryBackend, Worker, TaskRegistry,
    CronScheduler, CronSchedule
)
import time

backend = InMemoryBackend()
registry = TaskRegistry()
scheduler = CronScheduler()

@registry.register("cleanup")
def cleanup_old_files():
    """Scheduled cleanup task."""
    print("Running cleanup...")
    return {"status": "cleaned"}

# Add scheduled job (runs every minute)
scheduler.add_job(
    task_name="cleanup",
    schedule=CronSchedule.from_crontab("* * * * *"),
    payload={}
)

# Start scheduler and worker
scheduler.start()
worker = Worker(backend=backend, registry=registry)

try:
    # Worker processes tasks, scheduler enqueues them
    time.sleep(60)
finally:
    scheduler.stop()
```

### Using Configuration Files

Create a `taskqueue.yaml` file:

```yaml
backend:
  type: memory

worker:
  poll_interval: 1.0
  max_retries: 3
  num_threads: 4

retry:
  # Global retry policy
  max_attempts: 5
  backoff_factor: 2.0
  initial_delay: 1.0
  
logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

Load configuration:

```python
from python_task_queue import load_config, create_worker, TaskRegistry

config = load_config("taskqueue.yaml")
registry = TaskRegistry()

@registry.register("my_task")
def my_task(data):
    return process(data)

worker = create_worker(config=config, registry=registry)
worker.process_tasks(num_tasks=10)
```

## Command-Line Interface

The library includes a comprehensive CLI for managing task queues:

### Installation

After installation, the `tq` command becomes available:

```bash
tq --help
```

### Worker Commands

```bash
# Start a worker
tq worker start

# Start with custom settings
tq worker start --poll-interval 0.5 --max-retries 5 --tasks-module mytasks.py

# Start as daemon
tq worker start --daemon
```

### Task Commands

```bash
# Enqueue a task
tq task enqueue greet --name Alice

# List pending tasks
tq task list

# Inspect a specific task
tq task inspect <task-id>
```

### Dead Letter Queue Commands

```bash
# List failed tasks
tq dlq list

# Replay failed tasks
tq dlq replay --all

# Purge all failed tasks
tq dlq purge --all
```

### Statistics

```bash
# View queue statistics
tq stats

# Get stats in JSON format
tq stats --output json
```

For detailed CLI documentation, see [CLI_GUIDE.md](CLI_GUIDE.md).

## Configuration Guide

### Backend Configuration

#### In-Memory Backend

```python
from python_task_queue import InMemoryBackend

backend = InMemoryBackend()
```

#### SQLite Backend

```python
from python_task_queue.backends import SQLiteBackend

backend = SQLiteBackend(database_path="tasks.db")
```

#### Redis Backend

```python
from python_task_queue.backends import RedisBackend

backend = RedisBackend(
    host="localhost",
    port=6379,
    db=0,
    key_prefix="tasks"
)
```

### Retry Policy Configuration

```python
from python_task_queue import (
    RetryPolicy,
    simple_retry_policy,
    aggressive_retry_policy,
    conservative_retry_policy,
    network_retry_policy
)

# Use built-in policies
@registry.register("my_task", retry_policy=aggressive_retry_policy)
def my_task(data):
    # Retries up to 10 times with exponential backoff
    return process(data)

# Create custom policy
custom_policy = RetryPolicy(
    max_attempts=7,
    initial_delay=2.0,
    backoff_factor=1.5,
    max_delay=60.0,
    retry_exceptions=(ConnectionError, TimeoutError)
)
```

### Worker Configuration

```python
from python_task_queue import Worker

worker = Worker(
    backend=backend,
    registry=registry,
    poll_interval=1.0,          # Check interval in seconds
    max_retries=3,              # Per-task retry limit
    timeout=300,                # Task timeout in seconds
    middleware_pipeline=pipeline,
    dlq=dead_letter_queue,
)
```

## API Reference

### Core Classes

#### `Task`
Represents a task to be executed.

```python
Task(
    name: str,
    payload: dict,
    metadata: dict = None,
    id: str = None
)
```

#### `TaskRegistry`
Manages task handler registration.

```python
registry = TaskRegistry()
registry.register("task_name", retry_policy=None, timeout=None)(handler_function)
```

#### `Worker`
Processes tasks from a queue.

```python
Worker(
    backend: QueueBackend,
    registry: TaskRegistry,
    poll_interval: float = 1.0,
    max_retries: int = 3,
    timeout: int = None,
    middleware_pipeline: MiddlewarePipeline = None,
    dlq: DeadLetterQueue = None
)
```

Methods:
- `process_tasks(num_tasks=None, stop_on_empty=False)` - Process tasks
- `start()` - Start worker in background
- `stop()` - Stop background worker
- `get_stats()` - Get worker statistics

#### `QueueBackend` (Abstract)
Base class for queue backends.

Methods:
- `enqueue(task: Task) -> str` - Add task to queue
- `dequeue() -> Task | None` - Get next task
- `ack(task_id: str)` - Mark task as complete
- `nack(task_id: str, error: str)` - Mark task as failed
- `get_task(task_id: str) -> Task | None` - Get task by ID
- `get_queue_length() -> int` - Get queue size

#### `RetryPolicy`
Configures retry behavior.

```python
RetryPolicy(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    retry_exceptions: tuple = None
)
```

#### `Middleware` (Abstract)
Base class for middleware components.

Methods:
- `before_execution(context: ExecutionContext)` - Before task execution
- `after_execution(context: ExecutionContext)` - After task execution
- `on_error(context: ExecutionContext, error: Exception)` - On task error

#### `DeadLetterQueue`
Manages failed tasks.

Methods:
- `add(task: Task, error: str, reason: str)` - Add failed task
- `list_all()` - List all failed tasks
- `list_by_reason(reason)` - List tasks by failure reason
- `replay(task_id)` - Re-enqueue a failed task
- `purge(task_id)` - Remove a failed task

#### `CronScheduler`
Manages scheduled tasks.

```python
CronScheduler(check_interval: float = 1.0)
```

Methods:
- `add_job(task_name, schedule, payload)` - Add scheduled job
- `remove_job(job_id)` - Remove scheduled job
- `start()` - Start scheduler
- `stop()` - Stop scheduler

### Built-in Retry Policies

- `simple_retry_policy` - 3 attempts with 2x backoff
- `aggressive_retry_policy` - 10 attempts with aggressive backoff
- `conservative_retry_policy` - 2 attempts, cautious approach
- `network_retry_policy` - Optimized for network operations
- `no_retry_policy` - No retries, fail fast

## Common Use Cases

### 1. Email Sending with Retries

```python
from python_task_queue import Task, InMemoryBackend, Worker, TaskRegistry
from python_task_queue import network_retry_policy

backend = InMemoryBackend()
registry = TaskRegistry()

@registry.register("send_email", retry_policy=network_retry_policy)
def send_email(to, subject, body):
    import smtplib
    # Email sending logic with automatic retries on network errors
    return {"status": "sent", "to": to}

# Enqueue emails in bulk
emails = [
    {"to": "user1@example.com", "subject": "Hello", "body": "..."},
    {"to": "user2@example.com", "subject": "Hello", "body": "..."},
]

for email in emails:
    task = Task(name="send_email", payload=email)
    backend.enqueue(task)

# Process emails with automatic retries
worker = Worker(backend=backend, registry=registry)
worker.process_tasks(num_tasks=len(emails))
```

### 2. Batch Data Processing

```python
from python_task_queue import Task, InMemoryBackend, Worker, TaskRegistry
import concurrent.futures

backend = InMemoryBackend()
registry = TaskRegistry()

@registry.register("process_record")
def process_record(record_id):
    # Process individual record
    time.sleep(0.1)  # Simulate work
    return {"id": record_id, "status": "processed"}

# Enqueue 1000 records
for i in range(1000):
    task = Task(name="process_record", payload={"record_id": i})
    backend.enqueue(task)

# Process with 4 workers in parallel
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    futures = []
    for _ in range(4):
        worker = Worker(backend=backend, registry=registry)
        futures.append(executor.submit(worker.process_tasks, num_tasks=250))
    
    for future in concurrent.futures.as_completed(futures):
        future.result()
```

### 3. Scheduled Cleanup Jobs

```python
from python_task_queue import (
    InMemoryBackend, Worker, TaskRegistry,
    CronScheduler, CronSchedule
)
import time

backend = InMemoryBackend()
registry = TaskRegistry()
scheduler = CronScheduler()

@registry.register("cleanup_temp_files")
def cleanup_temp_files():
    """Clean up temporary files older than 24 hours."""
    import os
    import tempfile
    # Cleanup logic
    return {"cleaned": 10}

@registry.register("send_daily_report")
def send_daily_report():
    """Send daily summary report."""
    # Report generation and sending logic
    return {"status": "sent"}

# Schedule cleanup daily at 2 AM
scheduler.add_job(
    task_name="cleanup_temp_files",
    schedule=CronSchedule.from_crontab("0 2 * * *"),
    payload={}
)

# Schedule report daily at 8 AM
scheduler.add_job(
    task_name="send_daily_report",
    schedule=CronSchedule.from_crontab("0 8 * * *"),
    payload={}
)

scheduler.start()
worker = Worker(backend=backend, registry=registry)

# Keep running
try:
    while True:
        worker.process_tasks(num_tasks=10)
        time.sleep(5)
finally:
    scheduler.stop()
```

### 4. API Rate Limiting with Task Queue

```python
from python_task_queue import Task, InMemoryBackend, Worker, TaskRegistry
import time

backend = InMemoryBackend()
registry = TaskRegistry()

# Rate-limited API calls
api_calls_queued = 0

@registry.register("api_call")
def api_call(endpoint, params):
    """Make API call at controlled rate."""
    time.sleep(1)  # Ensure rate limit (1 call per second max)
    # Make actual API call
    return {"endpoint": endpoint, "status": "success"}

def queue_api_calls(endpoints):
    """Enqueue multiple API calls."""
    for endpoint in endpoints:
        task = Task(name="api_call", payload={"endpoint": endpoint, "params": {}})
        backend.enqueue(task)

# Enqueue 100 API calls
queue_api_calls([f"/api/data/{i}" for i in range(100)])

# Process with rate limiting
worker = Worker(backend=backend, registry=registry)
worker.process_tasks(num_tasks=100)
```

### 5. Image Processing Pipeline

```python
from python_task_queue import Task, InMemoryBackend, Worker, TaskRegistry
from python_task_queue import LoggingMiddleware, MiddlewarePipeline
import time

backend = InMemoryBackend()
registry = TaskRegistry()

# Pipeline stages
@registry.register("resize_image")
def resize_image(image_path, size):
    """Resize image to specified size."""
    time.sleep(0.5)  # Simulate processing
    return {"path": image_path, "size": size, "status": "resized"}

@registry.register("add_watermark")
def add_watermark(image_path, watermark):
    """Add watermark to image."""
    time.sleep(0.3)  # Simulate processing
    return {"path": image_path, "watermark": watermark, "status": "watermarked"}

@registry.register("compress_image")
def compress_image(image_path, quality):
    """Compress image to specified quality."""
    time.sleep(0.2)  # Simulate processing
    return {"path": image_path, "quality": quality, "status": "compressed"}

# Chain processing tasks
def process_image_pipeline(image_path):
    stages = [
        ("resize_image", {"size": (800, 600)}),
        ("add_watermark", {"watermark": "© 2024"}),
        ("compress_image", {"quality": 85})
    ]
    
    prev_result = image_path
    for task_name, payload in stages:
        task = Task(name=task_name, payload={"image_path": prev_result, **payload})
        backend.enqueue(task)
        prev_result = f"{image_path}_{task_name}"

# Process multiple images
for image in ["photo1.jpg", "photo2.jpg", "photo3.jpg"]:
    process_image_pipeline(image)

worker = Worker(backend=backend, registry=registry)
worker.process_tasks(num_tasks=9)  # 3 images * 3 stages
```

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=python_task_queue

# Run specific test file
pytest tests/test_worker.py

# Run with verbose output
pytest -v
```

## Development

### Setting Up Development Environment

```bash
git clone https://github.com/natmart/project-eval-2.git
cd project-eval-2
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### Code Style

This project uses Black and Ruff for code formatting and linting:

```bash
# Format code
black .

# Lint code
ruff check .

# Format and lint in one command
black . && ruff check .
```

### Type Checking

```bash
mypy python_task_queue
```

## Documentation

- [CLI Guide](CLI_GUIDE.md) - Complete command-line interface documentation
- [Configuration Guide](CONFIGURATION_DOCUMENTATION.md) - Detailed configuration options

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Project Structure

```
python_task_queue/
├── __init__.py           # Package exports
├── models.py             # Data models (Task, TaskResult, TaskStatus)
├── backends/             # Queue backends
│   ├── __init__.py
│   ├── base.py          # Abstract base class
│   └── memory.py        # In-memory implementation
├── config.py             # Configuration management
├── registry.py           # Task registration system
├── retry.py              # Retry logic and policies
├── middleware.py         # Middleware pipeline
├── worker.py             # Worker implementation
└── cli.py                # Command-line interface

tests/
├── test_*.py            # Unit and integration tests
└── run_*.py             # Test runner scripts

examples/
├── example_tasks.py     # Example task definitions
├── demo_worker.py       # Worker demonstration
├── demo_cli.py          # CLI demonstration
└── demo_config.py       # Configuration demonstration
```

## Roadmap

- [ ] Additional backend implementations (Redis, RabbitMQ, Kafka)
- [ ] Web dashboard for monitoring
- [ ] Task chaining and workflow orchestration
- [ ] Distributed worker coordination
- [ ] Task result persistence and querying
- [ ] Performance benchmarks and optimization
- [ ] Python async/await support

## Support

- **Issues**: [GitHub Issues](https://github.com/natmart/project-eval-2/issues)
- **Documentation**: [GitHub Wiki](https://github.com/natmart/project-eval-2/wiki)

## Acknowledgments

Built with inspiration from Celery, RQ, and other task queue libraries.