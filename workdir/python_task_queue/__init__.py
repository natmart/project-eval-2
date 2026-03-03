"""
Python Task Queue Library

A flexible, production-ready task queue library for Python with pluggable backends.
"""

__version__ = "0.1.0"

# Core configuration
from python_task_queue.config import Config, get_config, load_config

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

# Core data models
from python_task_queue.models import Task, TaskResult, TaskStatus

# Dead Letter Queue
from python_task_queue.dlq import (
    DeadLetterQueue,
    DeadLetterTask,
    DLQBackend,
    MemoryDLQBackend,
    create_dlq,
)

__all__ = [
    "__version__",
    # Config
    "Config",
    "get_config",
    "load_config",
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
    # Models
    "Task",
    "TaskResult",
    "TaskStatus",
    # DLQ
    "DeadLetterQueue",
    "DeadLetterTask",
    "DLQBackend",
    "MemoryDLQBackend",
    "create_dlq",
]