"""
Middleware system for the Python Task Queue Library.

Provides around/before/after hooks for task execution, enabling cross-cutting
concerns like logging, metrics, error handling, etc.
"""

from __future__ import annotations

import logging
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from python_task_queue.models import Task, TaskResult


logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """
    Context object passed through middleware chain.
    
    Attributes:
        task: The task being executed
        handler: The handler function being called
        result: The result of execution (may be None before execution)
        error: Any error that occurred during execution
        metadata: Additional metadata for the execution
    """
    task: Task
    handler: Callable[..., Any]
    result: Optional[Any] = None
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Middleware(ABC):
    """
    Abstract base class for middleware.
    
    Middleware can intercept task execution before and after the handler is called,
    enabling cross-cutting concerns like logging, metrics, error handling, etc.
    """
    
    @abstractmethod
    def before_execution(self, context: ExecutionContext) -> None:
        """
        Called before the task handler is executed.
        
        Args:
            context: The execution context
        """
        pass
    
    @abstractmethod
    def after_execution(self, context: ExecutionContext) -> None:
        """
        Called after the task handler is executed (regardless of success/failure).
        
        Args:
            context: The execution context
        """
        pass


class MiddlewarePipeline:
    """
    Pipeline for executing middleware around task handlers.
    """
    
    def __init__(self, middleware: Optional[List[Middleware]] = None):
        """
        Initialize the middleware pipeline.
        
        Args:
            middleware: List of middleware to execute (in order)
        """
        self.middleware = middleware or []
    
    def execute(self, task: Task, handler: Callable[..., Any]) -> Any:
        """
        Execute a task handler with middleware chain.
        
        Args:
            task: The task to execute
            handler: The handler function
            
        Returns:
            The result of the handler execution
        """
        context = ExecutionContext(task=task, handler=handler)
        
        # Execute before hooks
        for middleware in self.middleware:
            try:
                middleware.before_execution(context)
            except Exception as e:
                logger.exception(f"Middleware before_execution failed: {e}")
        
        # Execute the handler
        try:
            context.result = handler(task.payload)
        except Exception as e:
            context.error = e
            logger.exception(f"Task handler execution failed: {e}")
            raise
        finally:
            # Execute after hooks (even if handler failed)
            for middleware in reversed(self.middleware):
                try:
                    middleware.after_execution(context)
                except Exception as e:
                    logger.exception(f"Middleware after_execution failed: {e}")
        
        return context.result


class LoggingMiddleware(Middleware):
    """
    Middleware that logs task lifecycle events.
    """
    
    def __init__(self, level: int = logging.INFO):
        """
        Initialize the logging middleware.
        
        Args:
            level: Logging level to use
        """
        self.level = level
    
    def before_execution(self, context: ExecutionContext) -> None:
        """Log task start."""
        logger.log(
            self.level,
            f"Starting task execution: {context.task.name} (id={context.task.id})"
        )
    
    def after_execution(self, context: ExecutionContext) -> None:
        """Log task completion."""
        if context.error:
            logger.log(
                self.level,
                f"Task failed: {context.task.name} (id={context.task.id}) - "
                f"{type(context.error).__name__}: {context.error}"
            )
        else:
            logger.log(
                self.level,
                f"Task completed: {context.task.name} (id={context.task.id})"
            )