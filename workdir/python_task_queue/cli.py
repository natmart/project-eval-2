"""
Click-based CLI for the Python Task Queue Library.

This module provides a command-line interface for:
- Starting workers
- Enqueuing and managing tasks
- Inspecting the dead letter queue
- Viewing statistics
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import click

from python_task_queue.models import Task, TaskStatus
from python_task_queue.backends import InMemoryBackend
from python_task_queue.registry import get_registry
from python_task_queue.worker import Worker, create_worker
from python_task_queue.config import get_config, load_config

# Try to import optional modules gracefully
try:
    from python_task_queue.dlq import DeadLetterQueue
    DLQ_AVAILABLE = True
except ImportError:
    DLQ_AVAILABLE = False

try:
    from python_task_queue.monitoring import Monitoring
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False

try:
    from python_task_queue.scheduler import CronScheduler
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False


# Configure CLI logging
def setup_logging(log_level: str = "INFO", log_format: Optional[str] = None) -> None:
    """Set up logging for the CLI."""
    if log_format is None:
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        stream=sys.stdout
    )


logger = logging.getLogger(__name__)


# Main CLI group
@click.group()
@click.version_option(version="0.1.0")
@click.option(
    "--config", "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file (YAML)"
)
@click.option(
    "--log-level", "-l",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False),
    default="INFO",
    help="Set the logging level"
)
@click.option(
    "--backend", "-b",
    type=click.Choice(["memory", "redis", "sqlite"], case_sensitive=False),
    help="Queue backend to use"
)
@click.pass_context
def cli(ctx: click.Context, config: Optional[Path], log_level: str, backend: Optional[str]) -> None:
    """Python Task Queue CLI
    
    A flexible command-line interface for managing task queues, workers, and tasks.
    """
    # Set up context
    ctx.ensure_object(dict)
    
    # Set up logging
    setup_logging(log_level)
    
    # Load configuration if provided
    if config:
        try:
            config_obj = load_config(str(config))
            ctx.obj["config"] = config_obj
            logger.info(f"Loaded configuration from {config}")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            ctx.exit(1)
    else:
        ctx.obj["config"] = get_config()
    
    # Override backend if specified
    if backend:
        ctx.obj["backend_type"] = backend.lower()
    else:
        ctx.obj["backend_type"] = ctx.obj["config"].queue_backend
    
    logger.debug(f"CLI initialized with backend: {ctx.obj['backend_type']}")


def get_backend(ctx: click.Context):
    """Get the appropriate backend based on configuration."""
    backend_type = ctx.obj.get("backend_type", "memory")
    
    if backend_type == "memory":
        return InMemoryBackend()
    elif backend_type == "redis":
        try:
            from python_task_queue.backends import RedisBackend
            config = ctx.obj.get("config")
            return RedisBackend(
                host=config.redis_host,
                port=config.redis_port,
                db=config.redis_db,
                password=config.redis_password
            )
        except ImportError:
            logger.error("Redis backend not available. Install redis-py to use this backend.")
            ctx.exit(1)
    elif backend_type == "sqlite":
        try:
            from python_task_queue.backends import SQLiteBackend
            config = ctx.obj.get("config")
            return SQLiteBackend(config.sqlite_path)
        except ImportError:
            logger.error("SQLite backend not available.")
            ctx.exit(1)
    else:
        logger.error(f"Unknown backend type: {backend_type}")
        ctx.exit(1)


def get_dlq(ctx: click.Context):
    """Get the DLQ if available."""
    if not DLQ_AVAILABLE:
        logger.error("Dead Letter Queue is not available.")
        ctx.exit(1)
    return DeadLetterQueue()


# Worker commands
@cli.group()
def worker() -> None:
    """Worker management commands."""
    pass


@worker.command()
@click.option(
    "--daemon/--no-daemon",
    default=False,
    help="Run worker as a daemon"
)
@click.option(
    "--poll-interval", "-p",
    type=float,
    help="Polling interval in seconds"
)
@click.option(
    "--max-retries", "-r",
    type=int,
    help="Maximum number of retries"
)
@click.option(
    "--tasks-module", "-m",
    type=str,
    help="Python module to load task handlers from"
)
@click.pass_context
def start(ctx: click.Context, daemon: bool, poll_interval: Optional[float], 
          max_retries: Optional[int], tasks_module: Optional[str]) -> None:
    """Start a task queue worker."""
    # Load tasks from module if specified
    if tasks_module:
        logger.info(f"Loading task handlers from module: {tasks_module}")
        try:
            import importlib
            importlib.import_module(tasks_module)
            logger.info("Task handlers loaded successfully")
        except ImportError as e:
            logger.error(f"Failed to load tasks module: {e}")
            ctx.exit(1)
    
    # Get configuration
    config = ctx.obj.get("config", get_config())
    
    # Override config with CLI options
    if poll_interval is None:
        poll_interval = config.poll_interval
    if max_retries is None:
        max_retries = config.max_retries
    
    # Create backend and worker
    backend = get_backend(ctx)
    
    worker = Worker(
        backend=backend,
        poll_interval=poll_interval,
        max_retries=max_retries
    )
    
    # Set up graceful shutdown
    shutdown_event = worker.shutdown_event
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        worker.stop(timeout=30.0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start worker
    logger.info(f"Starting worker (daemon={daemon}, poll_interval={poll_interval}s, max_retries={max_retries})")
    worker.start(daemon=daemon)
    
    if daemon:
        # Daemon mode - run until shutdown signal
        try:
            while worker.is_running():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, stopping worker...")
            worker.stop()
            worker.join(timeout=30.0)
    else:
        # Non-daemon - run in foreground
        try:
            while worker.is_running():
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, stopping worker...")
            worker.stop()
            worker.join(timeout=30.0)
    
    # Print statistics
    stats = worker.get_stats()
    logger.info(f"Worker stopped. Statistics: {stats}")
    logger.info(f"  Tasks processed: {stats.tasks_processed}")
    logger.info(f"  Tasks succeeded: {stats.tasks_succeeded}")
    logger.info(f"  Tasks failed: {stats.tasks_failed}")
    logger.info(f"  Tasks retried: {stats.tasks_retried}")
    logger.info(f"  Total execution time: {stats.total_execution_time:.3f}s")


# Task commands
@cli.group()
def task() -> None:
    """Task management commands."""
    pass


@task.command("enqueue")
@click.argument("name")
@click.argument("payload")
@click.option(
    "--priority", "-p",
    type=int,
    default=0,
    help="Task priority (lower is higher priority)"
)
@click.option(
    "--max-retries", "-r",
    type=int,
    help="Maximum number of retries for this task"
)
@click.option(
    "--timeout", "-t",
    type=float,
    help="Task timeout in seconds"
)
@click.pass_context
def enqueue_task(ctx: click.Context, name: str, payload: str, priority: int,
                 max_retries: Optional[int], timeout: Optional[float]) -> None:
    """Enqueue a new task.
    
    NAME: The name of the task handler
    PAYLOAD: JSON-formatted payload for the task
    """
    # Validate task name is registered
    registry = get_registry()
    try:
        handler = registry.get(name)
        logger.info(f"Task '{name}' is registered with handler: {handler.__name__}")
    except Exception as e:
        logger.error(f"Task '{name}' is not registered: {e}")
        logger.info(f"Registered tasks: {list(registry.list_all().keys())}")
        ctx.exit(1)
    
    # Parse payload
    try:
        payload_data = json.loads(payload)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON payload: {e}")
        ctx.exit(1)
    
    # Create task
    task = Task(
        name=name,
        payload=payload_data,
        priority=priority,
        max_retries=max_retries,
        timeout=timeout
    )
    
    # Enqueue task
    backend = get_backend(ctx)
    try:
        backend.enqueue(task)
        logger.info(f"Task enqueued successfully")
        logger.info(f"  ID: {task.id}")
        logger.info(f"  Name: {task.name}")
        logger.info(f"  Status: {task.status}")
        logger.info(f"  Priority: {task.priority}")
    except Exception as e:
        logger.error(f"Failed to enqueue task: {e}")
        ctx.exit(1)


@task.command("list")
@click.option(
    "--status", "-s",
    type=click.Choice(["pending", "running", "completed", "failed", "retrying"], case_sensitive=False),
    help="Filter by task status"
)
@click.option(
    "--limit", "-l",
    type=int,
    default=50,
    help="Maximum number of tasks to show"
)
@click.option(
    "--output", "-o",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format"
)
@click.pass_context
def list_tasks(ctx: click.Context, status: Optional[str], limit: int, output: str) -> None:
    """List tasks in the queue."""
    backend = get_backend(ctx)
    
    # Filter by status if specified
    status_filter = TaskStatus.from_string(status) if status else None
    tasks = backend.list_tasks(status=status_filter)
    
    # Limit results
    tasks = tasks[:limit]
    
    if output == "json":
        # JSON output
        task_list = [
            {
                "id": str(task.id),
                "name": task.name,
                "status": str(task.status),
                "priority": task.priority,
                "retry_count": task.retry_count,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
            for task in tasks
        ]
        click.echo(json.dumps(task_list, indent=2))
    else:
        # Table output
        if not tasks:
            click.echo("No tasks found.")
            return
        
        click.echo(f"\nFound {len(tasks)} task(s):\n")
        click.echo(f"{'ID':<36} {'Name':<20} {'Status':<10} {'Priority':<8} {'Retries':<8}")
        click.echo("-" * 90)
        
        for task in tasks:
            click.echo(
                f"{str(task.id)[:36]:<36} "
                f"{task.name[:20]:<20} "
                f"{str(task.status)[:10]:<10} "
                f"{task.priority:<8} "
                f"{task.retry_count:<8}"
            )
        
        click()


@task.command("inspect")
@click.argument("task_id")
@click.option(
    "--output", "-o",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format"
)
@click.pass_context
def inspect_task(ctx: click.Context, task_id: str, output: str) -> None:
    """Inspect a specific task by ID."""
    import uuid
    
    backend = get_backend(ctx)
    
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        logger.error(f"Invalid task ID: {task_id}")
        ctx.exit(1)
    
    task = backend.get_task(task_uuid)
    
    if task is None:
        logger.error(f"Task not found: {task_id}")
        ctx.exit(1)
    
    if output == "json":
        # JSON output
        task_dict = {
            "id": str(task.id),
            "name": task.name,
            "status": str(task.status),
            "priority": task.priority,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "timeout": task.timeout,
            "payload": task.payload,
            "result": task.result.value if task.result else None,
            "error": task.error,
            "error_type": task.error_type,
            "traceback": task.result.traceback if task.result else None,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }
        click.echo(json.dumps(task_dict, indent=2))
    else:
        # Table output
        click.echo(f"\nTask Details:\n")
        click.echo(f"  ID:           {task.id}")
        click.echo(f"  Name:         {task.name}")
        click.echo(f"  Status:       {task.status}")
        click.echo(f"  Priority:     {task.priority}")
        click.echo(f"  Retries:      {task.retry_count}/{task.max_retries}")
        click.echo(f"  Timeout:      {task.timeout}s")
        
        click.echo(f"\n  Payload:")
        click.echo(f"    {json.dumps(task.payload, indent=6)}")
        
        if task.result and task.result.value is not None:
            click.echo(f"\n  Result:")
            click.echo(f"    {json.dumps(task.result.value, indent=6)}")
        
        if task.error:
            click.echo(f"\n  Error:")
            click.echo(f"    Type: {task.error_type}")
            click.echo(f"    Message: {task.error}")
            if task.result and task.result.traceback:
                click.echo(f"    Traceback:\n{task.result.traceback}")
        
        click.echo(f"\n  Timestamps:")
        click.echo(f"    Created:   {task.created_at.isoformat() if task.created_at else 'N/A'}")
        click.echo(f"    Started:   {task.started_at.isoformat() if task.started_at else 'N/A'}")
        click.echo(f"    Completed: {task.completed_at.isoformat() if task.completed_at else 'N/A'}")
        click()


# DLQ commands
@cli.group()
def dlq() -> None:
    """Dead Letter Queue management commands."""
    pass


@dlq.command("list")
@click.option(
    "--reason", "-r",
    type=str,
    help="Filter by failure reason"
)
@click.option(
    "--limit", "-l",
    type=int,
    default=50,
    help="Maximum number of tasks to show"
)
@click.option(
    "--output", "-o",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format"
)
@click.pass_context
def list_dlq(ctx: click.Context, reason: Optional[str], limit: int, output: str) -> None:
    """List tasks in the dead letter queue."""
    if not DLQ_AVAILABLE:
        logger.error("Dead Letter Queue is not available")
        ctx.exit(1)
    
    dlq = get_dlq(ctx)
    
    # Get tasks from DLQ
    if reason:
        tasks = dlq.inspect(reason=reason)
    else:
        tasks = dlq.inspect()
    
    # Limit results
    tasks = list(tasks)[:limit]
    
    if output == "json":
        # JSON output
        task_list = []
        for task in tasks:
            task_dict = {
                "dlq_id": str(task.id),
                "task_id": str(task.task_id),
                "task_name": task.task_name,
                "queue": task.queue,
                "reason": task.reason,
                "error": task.error,
                "failed_at": task.failed_at.isoformat() if task.failed_at else None,
                "original_retry_count": task.original_retry_count,
            }
            task_list.append(task_dict)
        click.echo(json.dumps(task_list, indent=2))
    else:
        # Table output
        if not tasks:
            click.echo("No tasks in dead letter queue.")
            return
        
        click.echo(f"\nFound {len(tasks)} task(s) in dead letter queue:\n")
        click.echo(f"{'DLQ ID':<36} {'Task Name':<20} {'Reason':<20} {'Queue':<10}")
        click.echo("-" * 96)
        
        for task in tasks:
            click.echo(
                f"{str(task.id)[:36]:<36} "
                f"{task.task_name[:20]:<20} "
                f"{task.reason[:20]:<20} "
                f"{task.queue[:10]:<10}"
            )
        click()


@dlq.command("replay")
@click.argument("dlq_id")
@click.option(
    "--reset-retries/--no-reset-retries",
    default=True,
    help="Reset retry count when replaying"
)
@click.pass_context
def replay_dlq(ctx: click.Context, dlq_id: str, reset_retries: bool) -> None:
    """Replay a task from the dead letter queue."""
    import uuid
    
    if not DLQ_AVAILABLE:
        logger.error("Dead Letter Queue is not available")
        ctx.exit(1)
    
    dlq = get_dlq(ctx)
    backend = get_backend(ctx)
    
    try:
        dlq_uuid = uuid.UUID(dlq_id)
    except ValueError:
        logger.error(f"Invalid DLQ task ID: {dlq_id}")
        ctx.exit(1)
    
    # Replay the task
    try:
        task = dlq.replay(dlq_uuid, reset_retries=reset_retries)
        
        # Enqueue the replayed task
        backend.enqueue(task)
        
        logger.info(f"Task replayed successfully")
        logger.info(f"  Original task ID: {task.id}")
        logger.info(f"  Task name: {task.name}")
        logger.info(f"  Retries reset: {reset_retries}")
    except Exception as e:
        logger.error(f"Failed to replay task: {e}")
        ctx.exit(1)


@dlq.command("purge")
@click.argument("dlq_id")
@click.pass_context
def purge_dlq(ctx: click.Context, dlq_id: str) -> None:
    """Remove a task from the dead letter queue."""
    import uuid
    
    if not DLQ_AVAILABLE:
        logger.error("Dead Letter Queue is not available")
        ctx.exit(1)
    
    dlq = get_dlq(ctx)
    
    try:
        dlq_uuid = uuid.UUID(dlq_id)
    except ValueError:
        logger.error(f"Invalid DLQ task ID: {dlq_id}")
        ctx.exit(1)
    
    try:
        dlq.purge(dlq_uuid)
        logger.info(f"Task removed from dead letter queue: {dlq_id}")
    except Exception as e:
        logger.error(f"Failed to purge task: {e}")
        ctx.exit(1)


# Statistics command
@cli.command("stats")
@click.option(
    "--output", "-o",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format"
)
@click.pass_context
def statistics(ctx: click.Context, output: str) -> None:
    """Show task queue statistics."""
    backend = get_backend(ctx)
    
    # Get task counts by status
    all_tasks = backend.list_tasks()
    total_tasks = len(all_tasks)
    
    pending_tasks = backend.list_tasks(status=TaskStatus.PENDING)
    running_tasks = backend.list_tasks(status=TaskStatus.RUNNING)
    completed_tasks = backend.list_tasks(status=TaskStatus.COMPLETED)
    failed_tasks = backend.list_tasks(status=TaskStatus.FAILED)
    retrying_tasks = backend.list_tasks(status=TaskStatus.RETRYING)
    
    stats = {
        "total": total_tasks,
        "pending": len(pending_tasks),
        "running": len(running_tasks),
        "completed": len(completed_tasks),
        "failed": len(failed_tasks),
        "retrying": len(retrying_tasks),
    }
    
    if output == "json":
        click.echo(json.dumps(stats, indent=2))
    else:
        click.echo(f"\nTask Queue Statistics:\n")
        click.echo(f"  Total Tasks:    {stats['total']}")
        click.echo(f"  Pending:        {stats['pending']}")
        click.echo(f"  Running:        {stats['running']}")
        click.echo(f"  Completed:      {stats['completed']}")
        click.echo(f"  Failed:         {stats['failed']}")
        click.echo(f"  Retrying:       {stats['retrying']}")
        
        # Calculate success rate
        if stats['total'] > 0:
            success_rate = (stats['completed'] / stats['total']) * 100
            click.echo(f"  Success Rate:   {success_rate:.1f}%")
        
        click()
        
        # Show DLQ info if available
        if DLQ_AVAILABLE:
            dlq = get_dlq(ctx)
            dlq_tasks = list(dlq.inspect())
            click.echo(f"  DLQ Tasks:      {len(dlq_tasks)}")


if __name__ == "__main__":
    cli()