"""
Python Task Queue Library

A flexible, production-ready task queue library for Python with pluggable backends.
"""

__version__ = "0.1.0"

# Core configuration
from python_task_queue.config import Config, get_config, load_config

# Core data models
from python_task_queue.models import Task, TaskResult, TaskStatus

# Middleware system
from python_task_queue.middleware import (
    ConditionalMiddleware,
    ErrorCaptureMiddleware,
    ExecutionContext,
    LoggingMiddleware,
    MetricsMiddleware,
    Middleware,
    MiddlewarePipeline,
    MiddlewarePipelineBuilder,
    TimingMiddleware,
    ValidationMiddleware,
)

__all__ = [
    "__version__",
    # Configuration
    "Config",
    "get_config",
    "load_config",
    # Core models
    "Task",
    "TaskResult",
    "TaskStatus",
    # Middleware
    "Middleware",
    "ExecutionContext",
    "MiddlewarePipeline",
    "MiddlewarePipelineBuilder",
    "LoggingMiddleware",
    "TimingMiddleware",
    "ErrorCaptureMiddleware",
    "ValidationMiddleware",
    "MetricsMiddleware",
    "ConditionalMiddleware",
]