# Configuration System Documentation

## Overview

The Python Task Queue Library provides a comprehensive configuration system that supports:

- **YAML-based configuration files** for maintainable settings
- **Environment variable overrides** for deployment flexibility
- **Sensible defaults** for quick setup
- **Type-safe configuration** using Python dataclasses
- **Thread-safe global configuration** for access anywhere

## Quick Start

```python
from python_task_queue import load_config, get_config, Config

# Load configuration (auto-discovers config files or uses defaults)
config = load_config()

# Get the global configuration instance
config = get_config()

# Create custom configuration
config = Config(
    queue_backend="redis",
    poll_interval=2.5,
    max_retries=5,
)
```

## Configuration Priority

Configuration values are loaded in the following order (highest priority first):

1. **Environment variables** (e.g., `TASK_QUEUE_POLL_INTERVAL`)
2. **YAML configuration file** (if found)
3. **Default values** (from Config dataclass)

### Example

```python
# YAML file contains: poll_interval: 2.5
# Environment variable: TASK_QUEUE_POLL_INTERVAL=5.0

# Result: poll_interval will be 5.0 (env takes priority)
```

## Configuration File Locations

The system searches for configuration files in the following order:

1. `taskqueue.yaml` (current directory)
2. `taskqueue.yml` (current directory)
3. `.taskqueue.yaml` (current directory)
4. `.taskqueue.yml` (current directory)
5. `~/.taskqueue.yaml` (user home)
6. `~/.taskqueue.yml` (user home)
7. `~/.config/taskqueue/config.yaml`
8. `~/.config/taskqueue/config.yml`
9. `/etc/taskqueue/config.yaml` (system)
10. `/etc/taskqueue/config.yml` (system)

## Configuration Reference

### Queue Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `queue_backend` | str | `"memory"` | Backend type: `memory`, `redis`, or `sqldb` |
| `poll_interval` | float | `1.0` | Seconds between polling for tasks |
| `max_retries` | int | `3` | Maximum retry attempts for failed tasks |
| `backoff_base` | float | `2.0` | Base multiplier for exponential backoff |
| `backoff_max` | float | `300.0` | Maximum backoff time in seconds |
| `timeout` | float | `300.0` | Default timeout for task execution |
| `max_concurrent_tasks` | int | `10` | Maximum concurrent tasks |
| `queue_size_limit` | int | `0` | Max queue size (0 = unlimited) |

### Worker Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `worker_enabled` | bool | `true` | Enable worker loop |
| `worker_threads` | int | `1` | Number of worker threads |
| `heartbeat_interval` | float | `30.0` | Seconds between heartbeat updates |

### Task Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `task_result_ttl` | int | `3600` | Time in seconds to keep task results |
| `task_timeout_default` | float | `300.0` | Default timeout per task |

### Monitoring Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enable_metrics` | bool | `false` | Enable metrics collection |
| `enable_tracing` | bool | `false` | Enable distributed tracing |

### Logging Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `log_level` | str | `"INFO"` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `log_format` | str | `"%(asctime)s - ..."` | Log format string |

### Redis Backend Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `redis_host` | str | `"localhost"` | Redis server hostname |
| `redis_port` | int | `6379` | Redis server port |
| `redis_db` | int | `0` | Redis database number |
| `redis_password` | str | `None` | Redis password (optional) |
| `redis_socket_timeout` | int | `5` | Redis socket timeout |

### SQLite Backend Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `sqlite_path` | str | `"taskqueue.db"` | Path to SQLite database file |

## YAML Configuration Format

### Basic Configuration

```yaml
# taskqueue.yaml
queue_backend: redis
poll_interval: 2.5
max_retries: 5
worker_threads: 4
log_level: DEBUG
```

### Backend-Specific Configuration

```yaml
queue_backend: redis

backends:
  redis:
    host: localhost
    port: 6380
    password: secret123
    db: 1
    socket_timeout: 10

  sqlite:
    path: /data/backup_tasks.db
```

### Using camelCase

The system supports both `snake_case` and `camelCase` in YAML files:

```yaml
# Both formats are accepted
queueBackend: redis
pollInterval: 2.5
maxRetries: 5
```

These are automatically converted to Python `snake_case` format.

## Environment Variable Configuration

### Naming Convention

All environment variables follow the pattern: `TASK_QUEUE_<FIELD_NAME>`

Examples:

| Environment Variable | Config Field |
|---------------------|--------------|
| `TASK_QUEUE_QUEUE_BACKEND` | `queue_backend` |
| `TASK_QUEUE_POLL_INTERVAL` | `poll_interval` |
| `TASK_QUEUE_MAX_RETRIES` | `max_retries` |
| `TASK_QUEUE_REDIS_HOST` | `redis_host` |

### Values

Environment values are automatically parsed to the correct type:

```bash
# Boolean
TASK_QUEUE_WORKER_ENABLED=true
TASK_QUEUE_ENABLE_METRICS=false

# Integer
TASK_QUEUE_MAX_RETRIES=5
TASK_QUEUE_WORKER_THREADS=4

# Float
TASK_QUEUE_POLL_INTERVAL=2.5
TASK_QUEUE_TIMEOUT=300.0

# String
TASK_QUEUE_QUEUE_BACKEND=redis
TASK_QUEUE_LOG_LEVEL=DEBUG
```

### Accepted Boolean Values

**True:** `true`, `True`, `TRUE`, `yes`, `Yes`, `YES`, `1`, `on`, `On`, `ON`
**False:** `false`, `False`, `FALSE`, `no`, `No`, `NO`, `0`, `off`, `Off`, `OFF`

### None Values

These values are parsed as `None`:

- `None`
- `none`
- `NONE`
- `null`
- `NULL`
- Empty string

### Custom Prefix

```python
# Load with custom prefix
from python_task_queue import load_config

config = load_config(env_prefix="MYAPP_")
# Now looks for MYAPP_QUEUE_BACKEND, MYAPP_POLL_INTERVAL, etc.
```

## API Reference

### `Config`

Configuration dataclass with all settings.

```python
from python_task_queue import Config

config = Config(
    queue_backend="redis",
    poll_interval=2.5,
    max_retries=5,
)
```

### `load_config()`

Load configuration from file and environment variables.

```python
from python_task_queue import load_config

# Auto-discover config file
config = load_config()

# Load from specific file
config = load_config(config_path="/path/to/config.yaml")

# Skip environment variables
config = load_config(skip_env=True)

# Force reload even if already loaded
config = load_config(force_reload=True)

# Use custom env prefix
config = load_config(env_prefix="MYAPP_")
```

**Parameters:**

- `config_path` (`str`, optional): Path to YAML configuration file
- `env_prefix` (`str`, default `"TASK_QUEUE_"`): Prefix for environment variables
- `skip_env` (`bool`, default `False`): If True, skip environment variable loading
- `force_reload` (`bool`, default `False`): Force reload even if already loaded

**Returns:** `Config` instance

### `get_config()`

Get the global configuration instance.

```python
from python_task_queue import get_config

config = get_config()
```

**Returns:** Global `Config` instance

### `reset_config()`

Reset the global configuration to `None`, forcing reload on next access.

```python
from python_task_queue import reset_config

reset_config()
```

### `save_config()`

Save configuration to a YAML file.

```python
from python_task_queue import save_config, Config

config = Config(queue_backend="redis")
save_config(config, "/path/to/config.yaml")
```

**Parameters:**

- `config` (`Config`): Config instance to save
- `config_path` (`str`): Path to save configuration

## Usage Examples

### Example 1: Development Setup

```python
from python_task_queue import load_config

# Use defaults for development
config = load_config()

print(f"Using {config.queue_backend} backend")
print(f"Polling every {config.poll_interval}s")
```

### Example 2: Production Deployment

```python
from python_task_queue import load_config

# Load from production config file
config = load_config(config_path="/etc/taskqueue/production.yaml")

print(f"Production config loaded: {config.queue_backend}")
```

### Example 3: Kubernetes/Docker Deployment

```python
import os
from python_task_queue import load_config

# Environment variables are set via Docker/Kubernetes
# TASK_QUEUE_QUEUE_BACKEND=redis
# TASK_QUEUE_REDIS_HOST=redis-service
# TASK_QUEUE_REDIS_PORT=6379

config = load_config()

# Config automatically merges env vars with defaults
print(f"Redis at {config.redis_host}:{config.redis_port}")
```

### Example 4: Testing

```python
from python_task_queue import Config, reset_config
import unittest

class MyTest(unittest.TestCase):
    def setUp(self):
        reset_config()
        self.config = Config(
            queue_backend="memory",
            poll_interval=0.1,  # Fast for testing
            max_retries=1,
        )

    def tearDown(self):
        reset_config()
```

### Example 5: Dynamic Configuration

```python
from python_task_queue import load_config, Config, reset_config

# Load initial config
config = load_config()

# Recreate with different settings
new_config = Config(
    queue_backend="redis",
    poll_interval=config.poll_interval * 2,  # Double the poll interval
    max_retries=config.max_retries + 2,
)
```

## Best Practices

### 1. Use YAML for Structured Settings

```yaml
# Good: Use YAML for complex configuration
queue_backend: redis
backends:
  redis:
    host: ${REDIS_HOST}  # Can use env substitution in YAML
    port: 6379
```

### 2. Use Environment Variables for Deployment

```bash
# Docker Compose
environment:
  - TASK_QUEUE_QUEUE_BACKEND=redis
  - TASK_QUEUE_REDIS_HOST=redis
  - TASK_QUEUE_REDIS_PORT=6379
```

### 3. Keep Secrets in Environment Variables

```bash
# Never commit secrets to YAML files
export TASK_QUEUE_REDIS_PASSWORD=$(vault kv get -field=password queue/redis)
```

### 4. Validate Configuration in Production

```python
from python_task_queue import load_config

config = load_config()
assert config.queue_backend in ["memory", "redis", "sqldb"]
assert config.redis_password is not None if config.queue_backend == "redis" else True
```

### 5. Document Your Configuration

Keep a `taskqueue.yaml.example` file in your repository:

```yaml
# Example configuration - copy to taskqueue.yaml and customize
queue_backend: redis
poll_interval: 1.0
max_retries: 3
```

## Troubleshooting

### Configuration Not Loading

```python
from python_task_queue import reset_config, load_config

# Force reload for debugging
reset_config()
config = load_config(force_reload=True)
print(f"Config loaded from: {config.config_path}")
```

### Check What's Loaded

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from python_task_queue import load_config
config = load_config()
# Logs will show config loading details
```

### Wrong Type Values

The configuration system validates types. If you get an error, check:

```python
from python_task_queue import Config

try:
    config = Config(poll_interval="invalid")  # This will raise
except AssertionError as e:
    print(f"Validation error: {e}")
```

### Environment Variables Not Working

```python
import os
print(f"TASK_QUEUE_POLL_INTERVAL = {os.environ.get('TASK_QUEUE_POLL_INTERVAL')}")

from python_task_queue import load_config, reset_config
reset_config()
config = load_config()
print(f"Loaded value: {config.poll_interval}")
```

## Migration Guide

### From Manual Configuration

**Before:**
```python
class MyConfig:
    def __init__(self):
        self.queue_backend = os.environ.get("BACKEND", "memory")
        self.poll_interval = float(os.environ.get("POLL_INTERVAL", "1.0"))
```

**After:**
```python
from python_task_queue import load_config

config = load_config()
# Settings automatically loaded from YAML and environment
```

### From Other Config Libraries

Most configuration libraries work similarly:

**python-decouple:**
```python
from decouple import config
value = config('MY_VAR')
```

**python-task-queue:**
```python
from python_task_queue import load_config
config = load_config()
value = config.my_var  # if mapped to Config field
```

## Contributing

When adding new configuration options:

1. Add field to `Config` dataclass with type annotation
2. Add default value
3. Add validation in `__post_init__` if needed
4. Update this documentation
5. Add tests in `tests/test_config.py`

## License

MIT - See LICENSE file for details.