"""
Comprehensive test suite for the configuration system.
"""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from python_task_queue.config import (
    Config,
    load_config,
    get_config,
    reset_config,
    _load_yaml_config,
    _load_env_config,
    _parse_env_value,
    _get_config_field_names,
    save_config,
    _get_default_config_paths,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def reset_global_config():
    """Reset global config before and after each test."""
    reset_config()
    yield
    reset_config()


class TestConfigDataclass:
    """Test the Config dataclass."""

    def test_default_values(self):
        """Test that Config has correct default values."""
        config = Config()
        assert config.queue_backend == "memory"
        assert config.poll_interval == 1.0
        assert config.max_retries == 3
        assert config.backoff_base == 2.0
        assert config.backoff_max == 300.0
        assert config.timeout == 300.0
        assert config.max_concurrent_tasks == 10
        assert config.worker_enabled is True
        assert config.worker_threads == 1
        assert config.heartbeat_interval == 30.0
        assert config.task_result_ttl == 3600
        assert config.task_timeout_default == 300.0
        assert config.queue_size_limit == 0
        assert config.enable_metrics is False
        assert config.enable_tracing is False
        assert config.log_level == "INFO"
        assert config.log_format == "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        assert config.redis_host == "localhost"
        assert config.redis_port == 6379
        assert config.redis_db == 0
        assert config.redis_password is None
        assert config.redis_socket_timeout == 5
        assert config.sqlite_path == "taskqueue.db"

    def test_custom_values(self):
        """Test creating Config with custom values."""
        config = Config(
            queue_backend="redis",
            poll_interval=2.5,
            max_retries=5,
            backoff_base=3.0,
        )
        assert config.queue_backend == "redis"
        assert config.poll_interval == 2.5
        assert config.max_retries == 5
        assert config.backoff_base == 3.0

    def test_validation_queue_backend(self):
        """Test validation of queue_backend field."""
        with pytest.raises(AssertionError, match="Invalid queue_backend"):
            Config(queue_backend="invalid")

    def test_validation_poll_interval(self):
        """Test validation of poll_interval field."""
        with pytest.raises(AssertionError, match="poll_interval must be positive"):
            Config(poll_interval=0)
        with pytest.raises(AssertionError, match="poll_interval must be positive"):
            Config(poll_interval=-1)

    def test_validation_max_retries(self):
        """Test validation of max_retries field."""
        with pytest.raises(AssertionError, match="max_retries must be non-negative"):
            Config(max_retries=-1)

    def test_validation_backoff_base(self):
        """Test validation of backoff_base field."""
        with pytest.raises(AssertionError, match="backoff_base must be positive"):
            Config(backoff_base=0)

    def test_validation_max_concurrent_tasks(self):
        """Test validation of max_concurrent_tasks field."""
        with pytest.raises(AssertionError, match="max_concurrent_tasks must be positive"):
            Config(max_concurrent_tasks=0)

    def test_validation_log_level_uppercase(self):
        """Test that log_level is normalized to uppercase."""
        config = Config(log_level="debug")
        assert config.log_level == "DEBUG"

    def test_all_fields_configurable(self):
        """Test that all fields can be configured."""
        config = Config(
            queue_backend="sqldb",
            poll_interval=5.0,
            max_retries=10,
            backoff_base=1.5,
            backoff_max=600.0,
            timeout=600.0,
            max_concurrent_tasks=20,
            worker_enabled=False,
            worker_threads=4,
            heartbeat_interval=60.0,
            task_result_ttl=7200,
            task_timeout_default=600.0,
            queue_size_limit=1000,
            enable_metrics=True,
            enable_tracing=True,
            log_level="DEBUG",
            log_format="%(message)s",
            redis_host="localhost",
            redis_port=6380,
            redis_db=1,
            redis_password="secret",
            redis_socket_timeout=10,
            sqlite_path="/tmp/queue.db",
        )
        assert config.queue_backend == "sqldb"
        assert config.worker_enabled is False
        assert config.worker_threads == 4
        assert config.enable_metrics is True
        assert config.enable_tracing is True


class TestYamlConfigLoading:
    """Test YAML configuration file loading."""

    def test_load_simple_yaml(self, temp_dir):
        """Test loading a simple YAML configuration."""
        config_path = os.path.join(temp_dir, "config.yaml")
        yaml_content = """
queue_backend: redis
poll_interval: 2.5
max_retries: 5
"""
        Path(config_path).write_text(yaml_content)

        config_dict = _load_yaml_config(config_path)
        assert config_dict["queue_backend"] == "redis"
        assert config_dict["poll_interval"] == 2.5
        assert config_dict["max_retries"] == 5

    def test_load_yaml_with_backend_configs(self, temp_dir):
        """Test loading YAML with backend-specific configs."""
        config_path = os.path.join(temp_dir, "config.yaml")
        yaml_content = """
queue_backend: redis
backends:
  redis:
    host: localhost
    port: 6380
    db: 1
    password: secret
"""
        Path(config_path).write_text(yaml_content)

        config_dict = _load_yaml_config(config_path)
        assert config_dict["queue_backend"] == "redis"
        assert config_dict["redis_host"] == "localhost"
        assert config_dict["redis_port"] == 6380
        assert config_dict["redis_db"] == 1
        assert config_dict["redis_password"] == "secret"

    def test_load_yaml_with_sqlite_backend(self, temp_dir):
        """Test loading YAML with SQLite backend config."""
        config_path = os.path.join(temp_dir, "config.yaml")
        yaml_content = """
queue_backend: sqldb
backends:
  sqlite:
    path: /tmp/queue.db
"""
        Path(config_path).write_text(yaml_content)

        config_dict = _load_yaml_config(config_path)
        assert config_dict["queue_backend"] == "sqldb"
        assert config_dict["sqlite_path"] == "/tmp/queue.db"

    def test_load_yaml_camelcase_to_snake_case(self, temp_dir):
        """Test that camelCase keys in YAML are converted to snake_case."""
        config_path = os.path.join(temp_dir, "config.yaml")
        yaml_content = """
queueBackend: redis
pollInterval: 2.5
maxRetries: 5
"""
        Path(config_path).write_text(yaml_content)

        config_dict = _load_yaml_config(config_path)
        assert config_dict["queue_backend"] == "redis"
        assert config_dict["poll_interval"] == 2.5
        assert config_dict["max_retries"] == 5

    def test_load_empty_yaml(self, temp_dir):
        """Test loading an empty YAML file."""
        config_path = os.path.join(temp_dir, "config.yaml")
        Path(config_path).write_text("")

        config_dict = _load_yaml_config(config_path)
        assert config_dict == {}

    def test_load_yaml_with_comments(self, temp_dir):
        """Test loading YAML with comments."""
        config_path = os.path.join(temp_dir, "config.yaml")
        yaml_content = """
# Configuration for task queue
queue_backend: redis  # Backend type
poll_interval: 2.5   # Seconds between polls
"""
        Path(config_path).write_text(yaml_content)

        config_dict = _load_yaml_config(config_path)
        assert config_dict["queue_backend"] == "redis"
        assert config_dict["poll_interval"] == 2.5

    def test_load_invalid_yaml(self, temp_dir):
        """Test that invalid YAML raises an error."""
        config_path = os.path.join(temp_dir, "config.yaml")
        Path(config_path).write_text("invalid: yaml: content: [unclosed")

        with pytest.raises(ValueError, match="Failed to parse YAML config"):
            _load_yaml_config(config_path)

    def test_load_nonexistent_yaml(self, temp_dir):
        """Test loading a non-existent file returns empty dict."""
        config_path = os.path.join(temp_dir, "nonexistent.yaml")
        config_dict = _load_yaml_config(config_path)
        assert config_dict == {}

    def test_load_yaml_with_unknown_fields(self, temp_dir, caplog):
        """Test that unknown fields are logged as warnings."""
        config_path = os.path.join(temp_dir, "config.yaml")
        yaml_content = """
queue_backend: redis
unknown_field: value
another_unknown: test
"""
        Path(config_path).write_text(yaml_content)

        config_dict = _load_yaml_config(config_path)
        assert config_dict["queue_backend"] == "redis"
        assert "unknown_field" not in config_dict
        assert "another_unknown" not in config_dict


class TestEnvironmentVariableLoading:
    """Test environment variable configuration loading."""

    def test_parse_env_boolean(self):
        """Test parsing boolean environment values."""
        assert _parse_env_value("true") is True
        assert _parse_env_value("True") is True
        assert _parse_env_value("TRUE") is True
        assert _parse_env_value("yes") is True
        assert _parse_env_value("YES") is True
        assert _parse_env_value("1") is True
        assert _parse_env_value("on") is True
        assert _parse_env_value("ON") is True

        assert _parse_env_value("false") is False
        assert _parse_env_value("False") is False
        assert _parse_env_value("FALSE") is False
        assert _parse_env_value("no") is False
        assert _parse_env_value("NO") is False
        assert _parse_env_value("0") is False
        assert _parse_env_value("off") is False
        assert _parse_env_value("OFF") is False

    def test_parse_env_int(self):
        """Test parsing integer environment values."""
        assert _parse_env_value("42") == 42
        assert _parse_env_value("0") == 0
        assert _parse_env_value("-10") == -10

    def test_parse_env_float(self):
        """Test parsing float environment values."""
        assert _parse_env_value("3.14") == 3.14
        assert _parse_env_value("0.5") == 0.5
        assert _parse_env_value("-1.5") == -1.5

    def test_parse_env_none(self):
        """Test parsing None/null values."""
        assert _parse_env_value("None") is None
        assert _parse_env_value("none") is None
        assert _parse_env_value("NONE") is None
        assert _parse_env_value("null") is None
        assert _parse_env_value("NULL") is None
        assert _parse_env_value("") is None

    def test_parse_env_string(self):
        """Test parsing string environment values."""
        assert _parse_env_value("hello") == "hello"
        assert _parse_env_value("some_value") == "some_value"

    @patch.dict(os.environ, {
        "TASK_QUEUE_QUEUE_BACKEND": "redis",
        "TASK_QUEUE_POLL_INTERVAL": "2.5",
        "TASK_QUEUE_MAX_RETRIES": "5",
        "OTHER_VAR": "should_be_ignored",
    })
    def test_load_env_config(self):
        """Test loading configuration from environment variables."""
        config_dict = _load_env_config("TASK_QUEUE_")
        assert config_dict["queue_backend"] == "redis"
        assert config_dict["poll_interval"] == 2.5
        assert config_dict["max_retries"] == 5
        assert "other_var" not in config_dict

    @patch.dict(os.environ, {
        "TASK_QUEUE_WORKER_ENABLED": "true",
        "TASK_QUEUE_ENABLE_METRICS": "yes",
        "TASK_QUEUE_ENABLE_TRACING": "1",
    })
    def test_load_env_booleans(self):
        """Test loading boolean values from environment."""
        config_dict = _load_env_config("TASK_QUEUE_")
        assert config_dict["worker_enabled"] is True
        assert config_dict["enable_metrics"] is True
        assert config_dict["enable_tracing"] is True

    @patch.dict(os.environ, {
        "TASK_QUEUE_REDIS_HOST": "localhost",
        "TASK_QUEUE_REDIS_PORT": "6380",
        "TASK_QUEUE_REDIS_PASSWORD": "secret",
    })
    def test_load_env_redis_config(self):
        """Test loading Redis config from environment."""
        config_dict = _load_env_config("TASK_QUEUE_")
        assert config_dict["redis_host"] == "localhost"
        assert config_dict["redis_port"] == 6380
        assert config_dict["redis_password"] == "secret"

    @patch.dict(os.environ, {
        "MYAPP_QUEUE_BACKEND": "redis",
        "MYAPP_POLL_INTERVAL": "2.5",
    })
    def test_custom_env_prefix(self):
        """Test loading with custom environment prefix."""
        config_dict = _load_env_config("MYAPP_")
        assert config_dict["queue_backend"] == "redis"
        assert config_dict["poll_interval"] == 2.5

    def test_skip_env_loading(self, temp_dir):
        """Test skipping environment variable loading."""
        # Set some environment vars
        with patch.dict(os.environ, {"TASK_QUEUE_POLL_INTERVAL": "10.0"}):
            config = load_config(skip_env=True)
            assert config.poll_interval == 1.0  # Default value


class TestConfigMerging:
    """Test merging configuration from multiple sources."""

    def test_env_overrides_yaml(self, temp_dir):
        """Test that environment variables override YAML config."""
        config_path = os.path.join(temp_dir, "config.yaml")
        yaml_content = """
queue_backend: redis
poll_interval: 2.5
max_retries: 5
"""
        Path(config_path).write_text(yaml_content)

        with patch.dict(os.environ, {
            "TASK_QUEUE_POLL_INTERVAL": "5.0",
            "TASK_QUEUE_MAX_RETRIES": "10",
        }):
            config = load_config(config_path=config_path)
            assert config.queue_backend == "redis"  # From YAML
            assert config.poll_interval == 5.0  # From env (overrides YAML)
            assert config.max_retries == 10  # From env (overrides YAML)

    def test_yaml_overrides_defaults(self, temp_dir):
        """Test that YAML config overrides defaults."""
        config_path = os.path.join(temp_dir, "config.yaml")
        yaml_content = """
queue_backend: redis
poll_interval: 2.5
max_retries: 5
"""
        Path(config_path).write_text(yaml_content)

        config = load_config(config_path=config_path)
        assert config.queue_backend == "redis"
        assert config.poll_interval == 2.5
        assert config.max_retries == 5
        assert config.timeout == 300.0  # Default value

    def test_full_merge_priority(self, temp_dir):
        """Test the full priority order: env > yaml > defaults."""
        config_path = os.path.join(temp_dir, "config.yaml")
        yaml_content = """
queue_backend: redis
poll_interval: 2.5
max_retries: 5
timeout: 600.0
"""
        Path(config_path).write_text(yaml_content)

        with patch.dict(os.environ, {
            "TASK_QUEUE_POLL_INTERVAL": "5.0",
        }):
            config = load_config(config_path=config_path)
            assert config.queue_backend == "redis"  # From YAML
            assert config.poll_interval == 5.0  # From env (highest priority)
            assert config.max_retries == 5  # From YAML
            assert config.timeout == 600.0  # From YAML
            assert config.max_concurrent_tasks == 10  # Default (lowest priority)


class TestGlobalConfig:
    """Test global configuration management."""

    def test_load_config_sets_global(self):
        """Test that load_config sets the global instance."""
        config = load_config()
        assert get_config() is config

    def test_get_config_loads_defaults(self):
        """Test that get_config loads default config if not loaded."""
        config = get_config()
        assert config.queue_backend == "memory"
        assert isinstance(config, Config)

    def test_force_reload(self, temp_dir):
        """Test that force_reload reloads configuration."""
        config1 = load_config()
        assert config1.queue_backend == "memory"

        # Create a config file
        config_path = os.path.join(temp_dir, "config.yaml")
        Path(config_path).write_text("queue_backend: redis")

        # Normal load shouldn't reload
        config2 = load_config()
        assert config2 is config1
        assert config2.queue_backend == "memory"

        # Force reload
        config3 = load_config(config_path=config_path, force_reload=True)
        assert config3.queue_backend == "redis"
        assert config3 is not config1

    def test_reset_config(self):
        """Test that reset_config clears the global instance."""
        config1 = get_config()
        reset_config()

        config2 = get_config()
        assert config2 is not config1


class TestConfigPaths:
    """Test config file path resolution."""

    def test_default_config_paths(self):
        """Test default config file search paths."""
        paths = _get_default_config_paths()

        # Check that important paths are included
        assert "taskqueue.yaml" in paths
        assert "taskqueue.yml" in paths
        assert ".taskqueue.yaml" in paths
        assert "~/.taskqueue.yaml" in paths
        assert "~/.config/taskqueue/config.yaml" in paths

    def test_load_config_auto_discovery(self, temp_dir):
        """Test that load_config finds config in current directory."""
        # Create a config file in temp dir
        config_path = os.path.join(temp_dir, "taskqueue.yaml")
        Path(config_path).write_text("queue_backend: redis\npoll_interval: 3.0")

        # Change to temp dir and load config
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            config = load_config()
            assert config.queue_backend == "redis"
            assert config.poll_interval == 3.0
        finally:
            os.chdir(original_cwd)

    def test_load_custom_path(self, temp_dir):
        """Test loading from a custom path."""
        config_path = os.path.join(temp_dir, "custom_config.yaml")
        Path(config_path).write_text("queue_backend: sqldb\nmax_retries: 10")

        config = load_config(config_path=config_path)
        assert config.queue_backend == "sqldb"
        assert config.max_retries == 10


class TestSaveConfig:
    """Test saving configuration to YAML files."""

    def test_save_simple_config(self, temp_dir):
        """Test saving a simple configuration."""
        config = Config(
            queue_backend="redis",
            poll_interval=2.5,
            max_retries=5,
        )

        config_path = os.path.join(temp_dir, "saved_config.yaml")
        save_config(config, config_path)

        # Verify it was saved and can be loaded
        assert os.path.exists(config_path)
        loaded_config = Config(**_load_yaml_config(config_path))
        assert loaded_config.queue_backend == "redis"
        assert loaded_config.poll_interval == 2.5
        assert loaded_config.max_retries == 5

    def test_save_config_with_backends(self, temp_dir):
        """Test saving configuration with backend-specific settings."""
        config = Config(
            queue_backend="redis",
            redis_host="localhost",
            redis_port=6380,
            redis_password="secret",
            sqlite_path="/tmp/queue.db",
        )

        config_path = os.path.join(temp_dir, "saved_config.yaml")
        save_config(config, config_path)

        # Load the saved file
        yaml_content = Path(config_path).read_text()
        assert "redis:" in yaml_content
        assert "host: localhost" in yaml_content
        assert "port: 6380" in yaml_content
        assert "password: secret" in yaml_content
        assert "sqlite:" in yaml_content
        assert "path: /tmp/queue.db" in yaml_content

    def test_save_and_load_roundtrip(self, temp_dir):
        """Test that saved config can be loaded accurately."""
        original_config = Config(
            queue_backend="sqldb",
            poll_interval=5.0,
            max_retries=10,
            backoff_base=3.0,
            worker_enabled=False,
            worker_threads=4,
            enable_metrics=True,
            log_level="DEBUG",
        )

        config_path = os.path.join(temp_dir, "roundtrip_config.yaml")
        save_config(original_config, config_path)

        loaded_dict = _load_yaml_config(config_path)
        loaded_config = Config(**loaded_dict)

        assert loaded_config.queue_backend == original_config.queue_backend
        assert loaded_config.poll_interval == original_config.poll_interval
        assert loaded_config.max_retries == original_config.max_retries
        assert loaded_config.backoff_base == original_config.backoff_base
        assert loaded_config.worker_enabled == original_config.worker_enabled
        assert loaded_config.worker_threads == original_config.worker_threads
        assert loaded_config.enable_metrics == original_config.enable_metrics
        assert loaded_config.log_level == original_config.log_level


class TestConfigFieldNames:
    """Test getting config field names."""

    def test_get_config_field_names(self):
        """Test that all config field names are returned."""
        fields = _get_config_field_names()
        assert isinstance(fields, list)
        assert len(fields) > 0
        assert "queue_backend" in fields
        assert "poll_interval" in fields
        assert "max_retries" in fields
        assert "worker_enabled" in fields
        assert "enable_metrics" in fields


class TestIntegration:
    """Integration tests for the configuration system."""

    def test_end_to_end_config_loading(self, temp_dir):
        """Test a complete configuration loading workflow."""
        # 1. Create a config file
        config_path = os.path.join(temp_dir, "config.yaml")
        yaml_content = """
queue_backend: redis
poll_interval: 2.5
backends:
  redis:
    host: localhost
    port: 6380
"""
        Path(config_path).write_text(yaml_content)

        # 2. Set some environment variables
        with patch.dict(os.environ, {
            "TASK_QUEUE_POLL_INTERVAL": "5.0",
            "TASK_QUEUE_MAX_RETRIES": "10",
        }):
            # 3. Load config
            config = load_config(config_path=config_path)

            # 4. Verify merged values
            assert config.queue_backend == "redis"  # From YAML
            assert config.redis_host == "localhost"  # From YAML backend
            assert config.redis_port == 6380  # From YAML backend
            assert config.poll_interval == 5.0  # From env (overrides YAML)
            assert config.max_retries == 10  # From env
            assert config.timeout == 300.0  # Default

    def test_multiple_backends_in_yaml(self, temp_dir):
        """Test YAML with multiple backend configurations."""
        config_path = os.path.join(temp_dir, "config.yaml")
        yaml_content = """
queue_backend: redis
backends:
  redis:
    host: localhost
    port: 6380
    password: secret
  sqlite:
    path: /tmp/queue.db
"""
        Path(config_path).write_text(yaml_content)

        config = load_config(config_path=config_path)

        # Both backends' config should be loaded
        assert config.redis_host == "localhost"
        assert config.redis_port == 6380
        assert config.redis_password == "secret"
        assert config.sqlite_path == "/tmp/queue.db"

    def test_config_for_all_backends(self, temp_dir):
        """Test configuration for all supported backends."""
        # Create config with all backend settings
        config_path = os.path.join(temp_dir, "config.yaml")
        yaml_content = """
backends:
  redis:
    host: localhost
    port: 6380
    db: 1
    password: pass123
    socket_timeout: 10
  sqlite:
    path: /tmp/tasks.db
"""
        Path(config_path).write_text(yaml_content)

        config = load_config(config_path=config_path)

        # Verify Redis settings
        assert config.redis_host == "localhost"
        assert config.redis_port == 6380
        assert config.redis_db == 1
        assert config.redis_password == "pass123"
        assert config.redis_socket_timeout == 10

        # Verify SQLite settings
        assert config.sqlite_path == "/tmp/tasks.db"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_env_value(self):
        """Test that empty environment values are parsed as None."""
        with patch.dict(os.environ, {"TASK_QUEUE_REDIS_PASSWORD": ""}):
            config_dict = _load_env_config("TASK_QUEUE_")
            assert config_dict["redis_password"] is None

    def test_whitespace_in_field_names(self):
        """Test that whitespace in env var field names is handled."""
        with patch.dict(os.environ, {"TASK_QUEUE_  POLL_INTERVAL": "5.0"}):
            config_dict = _load_env_config("TASK_QUEUE_")
            assert config_dict.get("poll_interval") == 5.0

    def test_corrupted_yaml(self, temp_dir):
        """Test handling of corrupted YAML files."""
        config_path = os.path.join(temp_dir, "corrupted.yaml")
        Path(config_path).write_text("queue_backend: [unclosed")

        with pytest.raises(ValueError):
            _load_yaml_config(config_path)

    def test_config_without_yaml_installed(self):
        """Test behavior when PyYAML is not installed."""
        with patch("python_task_queue.config.YAML_AVAILABLE", False):
            config_dict = _load_yaml_config("config.yaml")
            assert config_dict == {}

    def test_save_without_yaml(self):
        """Test that save raises error without PyYAML."""
        config = Config()

        with patch("python_task_queue.config.YAML_AVAILABLE", False):
            with pytest.raises(ValueError, match="PyYAML not available"):
                save_config(config, "config.yaml")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])