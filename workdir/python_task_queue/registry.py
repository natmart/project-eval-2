"""
Task registration system for the Python Task Queue Library.

Provides decorator-based task registration, name-to-handler mapping,
task discovery from modules, and handler signature validation.
"""

from __future__ import annotations

import inspect
import logging
import importlib.util
import sys
import threading
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar, Union
from typing_extensions import Protocol, runtime_checkable
from functools import wraps


logger = logging.getLogger(__name__)


# Type variables for better type hints
T = TypeVar('T')
Handler = Callable[..., Any]
TaskName = str
ModulePath = Union[str, Path]


class RegistrationError(Exception):
    """Base exception for registration errors."""
    pass


class DuplicateTaskError(RegistrationError):
    """Raised when attempting to register a task with an already registered name."""
    
    def __init__(self, task_name: str, existing_handler: Handler, new_handler: Handler):
        self.task_name = task_name
        self.existing_handler = existing_handler
        self.new_handler = new_handler
        super().__init__(
            f"Task '{task_name}' is already registered with handler "
            f"{existing_handler.__module__}.{existing_handler.__name__}"
        )


class InvalidHandlerError(RegistrationError):
    """Raised when a task handler fails signature validation."""
    
    def __init__(self, handler: Handler, reason: str):
        self.handler = handler
        self.reason = reason
        super().__init__(f"Invalid handler {handler.__name__}: {reason}")


class TaskNotFoundError(RegistrationError):
    """Raised when attempting to retrieve a non-existent task."""
    
    def __init__(self, task_name: str):
        self.task_name = task_name
        super().__init__(f"Task '{task_name}' is not registered")


@runtime_checkable
class TaskHandler(Protocol):
    """
    Protocol defining the expected interface for task handlers.
    
    A valid task handler should be a callable that accepts a payload
    and returns a result. The return type is Any to allow flexibility.
    """
    
    def __call__(self, payload: Any, **kwargs: Any) -> Any:
        """Execute the task with the given payload."""
        ...


@dataclass
class TaskInfo:
    """
    Information about a registered task.
    
    Attributes:
        name: The task name
        handler: The handler function
        module: The module where the handler is defined
        signature: The handler's signature
        metadata: Additional metadata about the task
        registered_at: Timestamp when the task was registered
    """
    
    name: TaskName
    handler: Handler
    module: str
    signature: inspect.Signature
    metadata: Dict[str, Any]
    registered_at: float
    
    def __repr__(self) -> str:
        return f"TaskInfo(name={self.name!r}, handler={self.handler.__name__}, module={self.module!r})"
    
    @property
    def full_name(self) -> str:
        """Get the fully qualified name (module.handler)."""
        return f"{self.module}.{self.handler.__name__}"


class TaskRegistry:
    """
    Thread-safe registry for task handlers.
    
    The registry maintains a mapping from task names to their handlers,
    ensures thread-safe operations, prevents duplicate registrations,
    and validates handler signatures.
    
    The registry is a singleton-like class with a global instance.
    
    Attributes:
        _tasks: Dictionary mapping task names to TaskInfo objects
        _lock: Thread lock for thread-safe operations
        _strict_mode: Whether to enforce strict validation
        _allow_overwrite: Whether to allow overwriting existing tasks
    """
    
    _instance: Optional[TaskRegistry] = None
    _instance_lock = threading.Lock()
    
    def __new__(cls) -> TaskRegistry:
        """Ensure singleton pattern with thread-safe initialization."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        """Initialize the task registry."""
        if self._initialized:
            return
        
        self._tasks: Dict[TaskName, TaskInfo] = {}
        self._lock = threading.RLock()
        self._strict_mode = False
        self._allow_overwrite = False
        self._initialized = True
        self._on_registration_hooks: List[Callable[[TaskInfo], None]] = []
        self._on_duplicate_hooks: List[Callable[[TaskName, Handler, Handler], Optional[Handler]]] = []
        
        logger.debug("TaskRegistry initialized")
    
    def register(
        self,
        task_name: Optional[TaskName] = None,
        *,
        overwrite: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None,
        validate_signature: bool = True,
        strict_mode: Optional[bool] = None,
    ) -> Callable[[Handler], Handler]:
        """
        Decorator for registering task handlers.
        
        Args:
            task_name: Optional custom task name. If None, uses the function name.
            overwrite: Whether to allow overwriting existing tasks. If None, uses registry default.
            metadata: Optional metadata to attach to the task.
            validate_signature: Whether to validate the handler signature.
            strict_mode: Whether to use strict validation mode. If None, uses registry default.
            
        Returns:
            Decorator function that registers the handler and returns it unchanged.
            
        Raises:
            DuplicateTaskError: If task name already exists and overwrite is False
            InvalidHandlerError: If handler fails signature validation
            
        Example:
            @registry.register("send_email")
            def send_email_handler(payload: dict) -> bool:
                # Send email logic
                return True
        """
        
        def decorator(handler: Handler) -> Handler:
            # Determine task name
            name = task_name or handler.__name__
            
            # Validate handler if requested
            if validate_signature:
                self._validate_handler(handler, strict_mode=strict_mode)
            
            # Prepare task info
            task_info = TaskInfo(
                name=name,
                handler=handler,
                module=handler.__module__,
                signature=inspect.signature(handler),
                metadata=metadata or {},
                registered_at=logger.handlers[0].emit if logger.handlers else 0,
            )
            
            # Get effective overwrite setting
            effective_overwrite = overwrite if overwrite is not None else self._allow_overwrite
            
            # Register with thread safety
            with self._lock:
                if name in self._tasks:
                    existing_info = self._tasks[name]
                    
                    # Check duplicate hooks
                    resolved_handler = None
                    for hook in self._on_duplicate_hooks:
                        result = hook(name, existing_info.handler, handler)
                        if result is not None:
                            resolved_handler = result
                            break
                    
                    if resolved_handler is not None:
                        # Use the resolved handler from hook
                        task_info.handler = resolved_handler
                        task_info.signature = inspect.signature(resolved_handler)
                        self._tasks[name] = task_info
                        logger.info(f"Task '{name}' overwritten via duplicate hook")
                    elif not effective_overwrite:
                        raise DuplicateTaskError(name, existing_info.handler, handler)
                    else:
                        warnings.warn(
                            f"Overwriting existing task '{name}' ({existing_info.handler}) "
                            f"with new handler ({handler})",
                            UserWarning,
                            stacklevel=2
                        )
                        self._tasks[name] = task_info
                        logger.info(f"Task '{name}' overwritten")
                else:
                    self._tasks[name] = task_info
                    logger.info(f"Task '{name}' registered with handler {handler.__qualifiedname__}")
            
            # Call registration hooks
            for hook in self._on_registration_hooks:
                try:
                    hook(task_info)
                except Exception as e:
                    logger.warning(f"Registration hook failed for task '{name}': {e}")
            
            return handler
        
        return decorator
    
    def unregister(self, task_name: TaskName) -> None:
        """
        Unregister a task from the registry.
        
        Args:
            task_name: Name of the task to unregister
            
        Raises:
            TaskNotFoundError: If the task is not registered
        """
        with self._lock:
            if task_name not in self._tasks:
                raise TaskNotFoundError(task_name)
            
            del self._tasks[task_name]
            logger.info(f"Task '{task_name}' unregistered")
    
    def get(self, task_name: TaskName) -> Handler:
        """
        Retrieve a task handler by name.
        
        Args:
            task_name: Name of the task to retrieve
            
        Returns:
            The task handler callable
            
        Raises:
            TaskNotFoundError: If the task is not registered
        """
        with self._lock:
            if task_name not in self._tasks:
                raise TaskNotFoundError(task_name)
            
            return self._tasks[task_name].handler
    
    def get_info(self, task_name: TaskName) -> TaskInfo:
        """
        Retrieve full task information by name.
        
        Args:
            task_name: Name of the task to retrieve info for
            
        Returns:
            TaskInfo object with full information
            
        Raises:
            TaskNotFoundError: If the task is not registered
        """
        with self._lock:
            if task_name not in self._tasks:
                raise TaskNotFoundError(task_name)
            
            return self._tasks[task_name]
    
    def list_tasks(self) -> List[TaskName]:
        """
        Get a list of all registered task names.
        
        Returns:
            List of task names
        """
        with self._lock:
            return list(self._tasks.keys())
    
    def get_all(self) -> Dict[TaskName, Handler]:
        """
        Get all registered tasks as a dictionary.
        
        Returns:
            Dictionary mapping task names to handlers (copy for thread safety)
        """
        with self._lock:
            return {name: info.handler for name, info in self._tasks.items()}
    
    def get_all_info(self) -> Dict[TaskName, TaskInfo]:
        """
        Get all task information.
        
        Returns:
            Dictionary mapping task names to TaskInfo objects (copy for thread safety)
        """
        with self._lock:
            return dict(self._tasks)
    
    def contains(self, task_name: TaskName) -> bool:
        """
        Check if a task is registered.
        
        Args:
            task_name: Name of the task to check
            
        Returns:
            True if the task is registered, False otherwise
        """
        with self._lock:
            return task_name in self._tasks
    
    def count(self) -> int:
        """
        Get the number of registered tasks.
        
        Returns:
            Number of registered tasks
        """
        with self._lock:
            return len(self._tasks)
    
    def clear(self) -> None:
        """Clear all registered tasks."""
        with self._lock:
            self._tasks.clear()
            logger.info("All tasks cleared from registry")
    
    def discover(
        self,
        module_path: ModulePath,
        *,
        recursive: bool = True,
        pattern: str = "*_tasks.py",
        validate: bool = True,
        on_error: str = "raise"
    ) -> List[TaskName]:
        """
        Discover and register tasks from modules.
        
        This method searches for Python modules and imports them, allowing
        any @task decorated functions to auto-register.
        
        Args:
            module_path: Path to a Python file or directory to search
            recursive: If True and module_path is a directory, search recursively
            pattern: Glob pattern for files to import (ignored if module_path is a file)
            validate: Whether to validate handlers after import
            on_error: How to handle errors ('raise', 'warn', or 'ignore')
            
        Returns:
            List of newly registered task names
            
        Raises:
            ImportError: If module import fails and on_error is 'raise'
            ValueError: If on_error is not one of 'raise', 'warn', 'ignore'
        """
        if on_error not in ("raise", "warn", "ignore"):
            raise ValueError(f"Invalid on_error value: {on_error}")
        
        module_path = Path(module_path)
        newly_registered: List[TaskName] = []
        
        # Get list of modules to import
        if module_path.is_file():
            modules_to_import = [module_path]
        else:
            if recursive:
                modules_to_import = list(module_path.rglob(pattern))
            else:
                modules_to_import = list(module_path.glob(pattern))
        
        baseline_count = self.count()
        
        for module_file in modules_to_import:
            if not module_file.suffix == ".py":
                continue
            
            try:
                # Import the module
                self._import_module(module_file)
                
                # Optionally validate handlers
                if validate:
                    for name, info in self.get_all_info().items():
                        if info.registered_at > baseline_count:
                            try:
                                self._validate_handler(info.handler)
                            except InvalidHandlerError as e:
                                if on_error == "raise":
                                    raise
                                elif on_error == "warn":
                                    warnings.warn(str(e), UserWarning, stacklevel=2)
                                # ignore mode: do nothing
            
            except Exception as e:
                if on_error == "raise":
                    raise ImportError(f"Failed to import module {module_file}: {e}") from e
                elif on_error == "warn":
                    warnings.warn(f"Failed to import module {module_file}: {e}", UserWarning, stacklevel=2)
                # ignore mode: continue
        
        # Determine newly registered tasks
        current_count = self.count()
        all_tasks = self.list_tasks()
        newly_registered = all_tasks[baseline_count:current_count]
        
        logger.info(f"Discovered and registered {len(newly_registered)} tasks")
        return newly_registered
    
    def _import_module(self, module_path: Path) -> None:
        """
        Import a Python module from a file path.
        
        Args:
            module_path: Path to the Python module file
        """
        module_name = module_path.stem
        
        # Remove parent directory names to create a unique module name
        # This helps with imports from different directories
        rel_path = module_path
        if module_path.is_absolute():
            # Try to find relative to current directory
            try:
                rel_path = module_path.relative_to(Path.cwd())
            except ValueError:
                pass
        
        module_name_parts = list(rel_path.parent.parts) + [module_name]
        module_name = ".".join(module_name_parts).replace(".py", "")
        
        # Avoid duplicate imports
        if module_name in sys.modules:
            return
        
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module spec for {module_path}")
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        logger.debug(f"Imported module: {module_name}")
    
    def _validate_handler(
        self,
        handler: Handler,
        strict_mode: Optional[bool] = None
    ) -> None:
        """
        Validate a task handler's signature.
        
        Args:
            handler: The handler to validate
            strict_mode: Whether to use strict validation. If None, uses registry default.
            
        Raises:
            InvalidHandlerError: If the handler fails validation
        """
        effective_strict = strict_mode if strict_mode is not None else self._strict_mode
        
        # Check if callable
        if not callable(handler):
            raise InvalidHandlerError(handler, "Handler must be callable")
        
        # Get signature
        try:
            sig = inspect.signature(handler)
        except ValueError as e:
            raise InvalidHandlerError(handler, f"Cannot inspect signature: {e}")
        
        # In strict mode, enforce that handler accepts keyword arguments
        if effective_strict:
            params = list(sig.parameters.values())
            if not params:
                raise InvalidHandlerError(handler, "Handler must accept at least one parameter")
            
            # Check if accepts **kwargs or has a reasonable parameter structure
            has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
            
            if not has_var_keyword and len(params) < 1:
                raise InvalidHandlerError(handler, "Handler must accept parameters")
            
            # Warn if no type hints in strict mode
            if not any(p.annotation != inspect.Parameter.empty for p in params):
                warnings.warn(
                    f"Handler '{handler.__name__}' lacks type hints (strict mode)",
                    UserWarning,
                    stacklevel=2
                )
        
        # Check for async handlers (not supported currently)
        if inspect.iscoroutinefunction(handler):
            raise InvalidHandlerError(handler, "Async handlers are not supported yet")
    
    def set_strict_mode(self, enabled: bool) -> None:
        """
        Enable or disable strict validation mode.
        
        Args:
            enabled: Whether to enable strict mode
        """
        with self._lock:
            self._strict_mode = enabled
            logger.debug(f"Strict mode {'enabled' if enabled else 'disabled'}")
    
    def set_allow_overwrite(self, allow: bool) -> None:
        """
        Set whether overwriting existing tasks is allowed.
        
        Args:
            allow: Whether to allow overwriting
        """
        with self._lock:
            self._allow_overwrite = allow
            logger.debug(f"Allow overwrite {'enabled' if allow else 'disabled'}")
    
    def on_registration(self, hook: Callable[[TaskInfo], None]) -> None:
        """
        Register a callback to be called when a task is registered.
        
        Args:
            hook: Callback function that receives TaskInfo
        """
        with self._lock:
            self._on_registration_hooks.append(hook)
    
    def on_duplicate(
        self,
        hook: Callable[[TaskName, Handler, Handler], Optional[Handler]]
    ) -> None:
        """
        Register a callback to handle duplicate task registrations.
        
        The hook can return a handler to use instead, or None to proceed
        with default behavior.
        
        Args:
            hook: Callback function that receives task name, existing handler, and new handler
        """
        with self._lock:
            self._on_duplicate_hooks.append(hook)
    
    def __len__(self) -> int:
        """Return the number of registered tasks."""
        return self.count()
    
    def __contains__(self, task_name: TaskName) -> bool:
        """Check if a task is registered."""
        return self.contains(task_name)
    
    def __iter__(self):
        """Iterate over task names (snapshot for thread safety)."""
        return iter(self.list_tasks())
    
    def __repr__(self) -> str:
        return f"TaskRegistry(tasks={self.count()})"


# Global registry instance
registry = TaskRegistry()


# Convenience decorator using the global registry
def task(
    task_name: Optional[TaskName] = None,
    *,
    overwrite: Optional[bool] = None,
    metadata: Optional[Dict[str, Any]] = None,
    validate_signature: bool = True,
    strict_mode: Optional[bool] = None,
) -> Callable[[Handler], Handler]:
    """
    Convenience decorator for registering tasks using the global registry.
    
    This is a shortcut for @registry.register() that uses the singleton registry.
    
    Args:
        task_name: Optional custom task name
        overwrite: Whether to allow overwriting existing tasks
        metadata: Optional metadata to attach to the task
        validate_signature: Whether to validate the handler signature
        strict_mode: Whether to use strict validation mode
        
    Returns:
        Decorator function
        
    Example:
        @task(name="send_email")
        def send_email_handler(payload: dict) -> bool:
            return True
    """
    return registry.register(
        task_name=task_name,
        overwrite=overwrite,
        metadata=metadata,
        validate_signature=validate_signature,
        strict_mode=strict_mode,
    )


def get_registry() -> TaskRegistry:
    """
    Get the global task registry instance.
    
    Returns:
        The global TaskRegistry singleton
    """
    return registry