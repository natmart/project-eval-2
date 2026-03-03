"""
Configuration system for the Python Task Queue Library.

Provides YAML-based configuration loading with environment variable override support.
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any, Dict, List
from threading import Lock
import re

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


logger = logging.getLogger(__name__)


@dataclass
class Config:
    """
    Configuration dataclass for the Python Task Queue Library.

    All settings have sensible defaults and can be overridden via:
    - YAML configuration files
    - Environment variables (prefixed with TASK_QUEUE_)
    - Direct parameter values

    Attributes:
        queue_backend: Backend implementation to use ('memory', 'redis', 'sqldb')
        poll_interval: Interval in seconds between polling for tasks
        max_retries: Maximum number of retry attempts for failed tasks
        backoff_base: Base multiplier for exponential backoff
        backoff_max: Maximum backoff time in seconds
        timeout: Timeout in seconds for task execution
        max_concurrent_tasks: Maximum number of tasks to process concurrently
        worker_enabled: Enable worker loop
        worker_threads: Number of worker threads
        heartbeat_interval: Interval in seconds for worker heartbeats
        task_result_ttl: Time in seconds to keep task results
        task_timeout_default: Default timeout for tasks if not specified
        queue_size_limit: Maximum number of tasks in queue (0 = unlimited)
        enable_metrics: Enable metrics collection
        enable_tracing: Enable distributed tracing
        log_level: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        log_format: Log format string
        config_path: Path to configuration file (for reference)
        redis_host: Redis server host (if using redis backend)
        redis_port: Redis server port
        redis_db: Redis database number
        redis_password: Redis password
        redis_socket_timeout: Redis socket timeout
        sqlite_path: Path to SQLite database (if using sqldb backend)
    """

    # Queue configuration
    queue_backend: str = "memory"
    poll_interval: float = 1.0
    max_retries: int = 3
    backoff_base: float = 2.0
    backoff_max: float = 300.0
    timeout: float = 300.0
    max_concurrent_tasks: int = 10

    # Worker configuration
    worker_enabled: bool = True
    worker_threads: int = 1
    heartbeat_interval: float = 30.0

    # Task configuration
    task_result_ttl: int = 3600
    task_timeout_default: float = 300.0
    queue_size_limit: int = 0

    # Monitoring configuration
    enable_metrics: bool = False
    enable_tracing: bool = False

    # Logging configuration
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Backend-specific configurations
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_socket_timeout: int = 5

    sqlite_path: str = "taskqueue.db"

    # Metadata
    config_path: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        self.log_level = self.log_level.upper()
        assert self.queue_backend in ["memory", "redis", "sqldb"], \
            f"Invalid queue_backend: {self.queue_backend}"
        assert self.poll_interval > 0, "poll_interval must be positive"
        assert self.max_retries >= 0, "max_retries must be non-negative"
        assert self.backoff_base > 0, "backoff_base must be positive"
        assert self.backoff_max >= self.backoff_base, "backoff_max must be >= backoff_base"
        assert self.timeout > 0, "timeout must be positive"
        assert self.max_concurrent_tasks > 0, "max_concurrent_tasks must be positive"
        assert self.heartbeat_interval > 0, "heartbeat_interval must be positive"
        assert self.task_result_ttl >= 0, "task_result_ttl must be non-negative"
        assert self.task_timeout_default > 0, "task_timeout_default must be positive"
        assert self.worker_threads > 0, "worker_threads must be positive"


# Global config instance
_global_config: Optional[Config] = None
_config_lock = Lock()


def load_config(
    config_path: Optional[str] = None,
    env_prefix: str = "TASK_QUEUE_",
    skip_env: bool = False,
    force_reload: bool = False,
) -> Config:
    """
    Load configuration from file and environment variables.

    Priority order (highest to lowest):
    1. Environment variables
    2. Configuration file (YAML)
    3. Default values

    Args:
        config_path: Path to YAML configuration file. If None, searches default locations.
        env_prefix: Prefix for environment variables (default: "TASK_QUEUE_")
        skip_env: If True, skip environment variable loading
        force_reload: If True, force reload even if config already loaded

    Returns:
        Config instance

    Examples:
        >>> config = load_config()
        >>> config = load_config(config_path="/path/to/config.yaml")
        >>> config = load_config(env_prefix="MYQUEUE_")

    Environment variable naming:
        All config fields are uppercased and prefixed.
        For example: TASK_QUEUE_POLL_INTERVAL, TASK_QUEUE_MAX_RETRIES
    """
    global _global_config

    with _config_lock:
        if _global_config is not None and not force_reload:
            return _global_config

        # Start with defaults
        config_dict: Dict[str, Any] = {}

        # 1. Load from YAML file
        if config_path is not None:
            file_config = _load_yaml_config(config_path)
            if file_config:
                config_dict.update(file_config)
                config_dict["config_path"] = config_path
        else:
            # Try default locations
            for default_path in _get_default_config_paths():
                if os.path.exists(default_path):
                    file_config = _load_yaml_config(default_path)
                    if file_config:
                        config_dict.update(file_config)
                        config_dict["config_path"] = default_path
                        logger.info(f"Loaded configuration from {default_path}")
                        break

        # 2. Load from environment variables
        if not skip_env:
            env_config = _load_env_config(env_prefix)
            config_dict.update(env_config)

        # 3. Create Config instance with merged values
        _global_config = Config(**config_dict)
        logger.info("Configuration loaded successfully")

        return _global_config


def get_config() -> Config:
    """
    Get the global configuration instance.

    Loads default configuration if not already loaded.

    Returns:
        Global Config instance

    Examples:
        >>> config = get_config()
        >>> print(config.poll_interval)
    """
    global _global_config

    with _config_lock:
        if _global_config is None:
            _global_config = load_config()

        return _global_config


def reset_config() -> None:
    """Reset the global configuration to None, forcing reload on next access."""
    global _global_config

    with _config_lock:
        _global_config = None


def _get_default_config_paths() -> List[str]:
    """
    Get list of default configuration file locations to search.

    Returns:
        List of paths in priority order
    """
    paths = [
        # Current directory
        "taskqueue.yaml",
        "taskqueue.yml",
        ".taskqueue.yaml",
        ".taskqueue.yml",

        # User home directory
        os.path.expanduser("~/.taskqueue.yaml"),
        os.path.expanduser("~/.taskqueue.yml"),

        # XDG config directory
        os.path.expanduser("~/.config/taskqueue/config.yaml"),
        os.path.expanduser("~/.config/taskqueue/config.yml"),

        # System-wide config (Unix)
        "/etc/taskqueue/config.yaml",
        "/etc/taskqueue/config.yml",
    ]
    return paths


def _load_yaml_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from a YAML file.

    Args:
        config_path: Path to YAML configuration file

    Returns:
        Dictionary of configuration values

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If YAML parsing fails
    """
    if not YAML_AVAILABLE:
        logger.warning("PyYAML not available, skipping YAML config loading")
        return {}

    path = Path(config_path)
    if not path.exists():
        logger.warning(f"Config file not found: {config_path}")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Convert snake_case to match Config dataclass fields
        config_dict = {}
        for key, value in data.items():
            # Support both snake_case and camelCase in YAML
            python_key = key
            if "_" not in key and any(c.isupper() for c in key):
                # Convert camelCase to snake_case
                s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', key)
                python_key = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

            # Handle nested config for backends
            if python_key == "backends":
                # Extract backend-specific config
                for backend_name, backend_config in value.items():
                    if isinstance(backend_config, dict):
                        for bk, bv in backend_config.items():
                            config_dict[f"{backend_name}_{bk}"] = bv
            elif python_key in _get_config_field_names():
                config_dict[python_key] = value
            else:
                logger.warning(f"Unknown config field: {key}")

        logger.debug(f"Loaded {len(config_dict)} values from {config_path}")
        return config_dict

    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML config: {e}") from e
    except Exception as e:
        raise ValueError(f"Failed to load config file: {e}") from e


def _load_env_config(env_prefix: str) -> Dict[str, Any]:
    """
    Load configuration from environment variables.

    Args:
        env_prefix: Prefix for environment variables

    Returns:
        Dictionary of configuration values
    """
    config_dict = {}
    valid_fields = _get_config_field_names()

    for env_key, env_value in os.environ.items():
        # Check if variable has the correct prefix
        if not env_key.startswith(env_prefix):
            continue

        # Extract config field name (remove prefix and lowercase)
        config_key = env_key[len(env_prefix):].lower()
        config_key = config_key.strip()  # Remove any whitespace

        if config_key not in valid_fields:
            logger.debug(f"Ignoring unknown env variable: {env_key}")
            continue

        # Parse value based on expected type
        parsed_value = _parse_env_value(env_value)
        config_dict[config_key] = parsed_value
        logger.debug(f"Loaded config from env: {env_key} = {parsed_value}")

    return config_dict


def _parse_env_value(value: str) -> Any:
    """
    Parse environment variable value to appropriate type.

    Args:
        value: String value from environment

    Returns:
        Parsed value (bool, int, float, or str)
    """
    # Handle booleans
    if value.lower() in ("true", "1", "yes", "on"):
        return True
    if value.lower() in ("false", "0", "no", "off"):
        return False

    # Handle integers
    try:
        return int(value)
    except ValueError:
        pass

    # Handle floats
    try:
        return float(value)
    except ValueError:
        pass

    # Handle "None" strings
    if value.lower() in ("none", "null", ""):
        return None

    # Return as string
    return value


def _get_config_field_names() -> List[str]:
    """
    Get list of valid Config dataclass field names.

    Returns:
        List of field names
    """
    return [f.name for f in Config.__dataclass_fields__.values()]


def save_config(config: Config, config_path: str) -> None:
    """
    Save configuration to a YAML file.

    Args:
        config: Config instance to save
        config_path: Path to save configuration

    Raises:
        ValueError: If YAML not available
    """
    if not YAML_AVAILABLE:
        raise ValueError("PyYAML not available, cannot save config")

    # Convert Config to dictionary
    config_dict = {}
    for field_name in _get_config_field_names():
        value = getattr(config, field_name)
        if value is not None and field_name != "config_path":
            config_dict[field_name] = value

    # Organize backend-specific config
    backend_configs = {}
    for key in list(config_dict.keys()):
        if key.startswith("redis_"):
            backend_configs.setdefault("redis", {})[key[6:]] = config_dict.pop(key)
        elif key.startswith("sqlite_"):
            backend_configs.setdefault("sqlite", {})[key[7:]] = config_dict.pop(key)

    if backend_configs:
        config_dict["backends"] = backend_configs

    # Write to file
    path = Path(config_path)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Configuration saved to {config_path}")