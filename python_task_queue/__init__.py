"""
Python Task Queue Library

A flexible, production-ready task queue library for Python with pluggable backends.
"""

__version__ = "0.1.0"

# Core configuration
from python_task_queue.config import Config, get_config, load_config

__all__ = [
    "__version__",
    "Config",
    "get_config",
    "load_config",
]