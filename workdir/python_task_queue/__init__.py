"""
Python Task Queue Library

A flexible, production-ready task queue library for Python with pluggable backends.
"""

__version__ = "0.1.0"

# Core configuration
from python_task_queue.config import Config, get_config, load_config

# Core data models
from python_task_queue.models import Task, TaskResult, TaskStatus

# Queue backends
from python_task_queue.backends import QueueBackend, InMemoryBackend, SQLiteBackend

# Retry system
from python_task_queue.retry import (
    RetryPolicy,
    RetryStrategy,
    RetryDecision,
    RetryDecisionReason,
    RetryPolicyConfig,
    simple_retry_policy,
    aggressive_retry_policy,
    conservative_retry_policy,
    network_retry_policy,
    no_retry_policy,
)

# Middleware system
from python_task_queue.middleware import (
    Middleware,
    MiddlewarePipeline,
    LoggingMiddleware,
    ExecutionContext,
)

# Worker system
from python_task_queue.worker import Worker, WorkerStats, create_worker

# Dead Letter Queue
from python_task_queue.dlq import DeadLetterQueue, DeadLetterTask

# Scheduler
from python_task_queue.scheduler import CronScheduler, ScheduledJob

# Monitoring
from python_task_queue.monitoring import Monitoring, WorkerMetric, QueueMetric

# CLI (optional import, may fail if click is not available)
try:
    from python_task_queue.cli import cli
    _cli_available = True
except ImportError:
    _cli_available = False


__all__ = [
    "__version__",
    # Config
    "Config",
    "get_config",
    "load_config",
    # Models
    "Task",
    "TaskResult",
    "TaskStatus",
    # Backends
    "QueueBackend",
    "InMemoryBackend",
    "SQLiteBackend",
    # Retry
    "RetryPolicy",
    "RetryStrategy",
    "RetryDecision",
    "RetryDecisionReason",
    "RetryPolicyConfig",
    "simple_retry_policy",
    "aggressive_retry_policy",
    "conservative_retry_policy",
    "network_retry_policy",
    "no_retry_policy",
    # Middleware
    "Middleware",
    "MiddlewarePipeline",
    "LoggingMiddleware",
    "ExecutionContext",
    # Worker
    "Worker",
    "WorkerStats",
    "create_worker",
    # DLQ
    "DeadLetterQueue",
    "DeadLetterTask",
    # Scheduler
    "CronScheduler",
    "ScheduledJob",
    # Monitoring
    "Monitoring",
    "WorkerMetric",
    "QueueMetric",
    # CLI
    "cli",
]