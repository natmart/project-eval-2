#!/usr/bin/env python3
"""
Demo script showing how to use the Python Task Queue configuration system.
"""

import os
import tempfile
import shutil
from pathlib import Path

# Set up the package path for demo purposes
import sys
sys.path.insert(0, '.')

from python_task_queue.config import Config, load_config, get_config, reset_config, save_config


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_default_config():
    """Demonstrate loading default configuration."""
    print_section("1. Default Configuration")

    reset_config()
    config = get_config()

    print(f"Queue Backend: {config.queue_backend}")
    print(f"Poll Interval: {config.poll_interval}s")
    print(f"Max Retries: {config.max_retries}")
    print(f"Worker Threads: {config.worker_threads}")
    print(f"Log Level: {config.log_level}")


def demo_custom_config():
    """Demonstrate creating custom configuration."""
    print_section("2. Custom Configuration")

    config = Config(
        queue_backend="redis",
        poll_interval=2.5,
        max_retries=5,
        worker_threads=4,
        enable_metrics=True,
    )

    print(f"Queue Backend: {config.queue_backend}")
    print(f"Poll Interval: {config.poll_interval}s")
    print(f"Max Retries: {config.max_retries}")
    print(f"Worker Threads: {config.worker_threads}")
    print(f"Metrics Enabled: {config.enable_metrics}")


def demo_yaml_config():
    """Demonstrate loading configuration from YAML file."""
    print_section("3. YAML Configuration File Loading")

    tmpdir = tempfile.mkdtemp()
    try:
        config_path = os.path.join(tmpdir, "custom_config.yaml")

        yaml_content = """
queue_backend: redis
poll_interval: 3.0
max_retries: 5
worker_threads: 4
enable_metrics: true
log_level: DEBUG

backends:
  redis:
    host: localhost
    port: 6380
    password: secret123
    db: 1
"""

        with open(config_path, "w") as f:
            f.write(yaml_content)

        print(f"Created config file: {config_path}")

        reset_config()
        config = load_config(config_path=config_path)

        print(f"\nLoaded configuration from YAML:")
        print(f"  Queue Backend: {config.queue_backend}")
        print(f"  Poll Interval: {config.poll_interval}s")
        print(f"  Max Retries: {config.max_retries}")
        print(f"  Worker Threads: {config.worker_threads}")
        print(f"  Metrics Enabled: {config.enable_metrics}")
        print(f"  Log Level: {config.log_level}")
        print(f"\n  Redis Host: {config.redis_host}")
        print(f"  Redis Port: {config.redis_port}")
        print(f"  Redis DB: {config.redis_db}")
        print(f"  Redis Password: {config.redis_password}")

    finally:
        shutil.rmtree(tmpdir)


def demo_env_override():
    """Demonstrate environment variable override."""
    print_section("4. Environment Variable Override")

    tmpdir = tempfile.mkdtemp()
    try:
        # Create a YAML config
        config_path = os.path.join(tmpdir, "config.yaml")
        with open(config_path, "w") as f:
            f.write("queue_backend: redis\npoll_interval: 2.0\nmax_retries: 3\n")

        # Set environment variables (these will override YAML values)
        os.environ["TASK_QUEUE_POLL_INTERVAL"] = "5.0"
        os.environ["TASK_QUEUE_MAX_RETRIES"] = "10"
        os.environ["TASK_QUEUE_WORKER_THREADS"] = "8"

        print("Set environment variables:")
        print("  TASK_QUEUE_POLL_INTERVAL=5.0 (overrides YAML)")
        print("  TASK_QUEUE_MAX_RETRIES=10 (overrides YAML)")
        print("  TASK_QUEUE_WORKER_THREADS=8 (adds to config)")

        reset_config()
        config = load_config(config_path=config_path)

        print(f"\nFinal configuration after merging:")
        print(f"  Queue Backend: {config.queue_backend} (from YAML)")
        print(f"  Poll Interval: {config.poll_interval}s (from env)")
        print(f"  Max Retries: {config.max_retries} (from env)")
        print(f"  Worker Threads: {config.worker_threads} (from env)")
        print(f"  Default timeout: {config.timeout}s (default value)")

        # Clean up env vars
        del os.environ["TASK_QUEUE_POLL_INTERVAL"]
        del os.environ["TASK_QUEUE_MAX_RETRIES"]
        del os.environ["TASK_QUEUE_WORKER_THREADS"]

    finally:
        shutil.rmtree(tmpdir)


def demo_save_config():
    """Demonstrate saving configuration."""
    print_section("5. Saving Configuration")

    tmpdir = tempfile.mkdtemp()
    try:
        # Create a custom config
        config = Config(
            queue_backend="sqldb",
            poll_interval=1.5,
            max_retries=5,
            worker_enabled=False,
            worker_threads=2,
            redis_host="redis.example.com",
            redis_port=6379,
            sqlite_path="/data/tasks.db",
        )

        # Save to file
        config_path = os.path.join(tmpdir, "saved_config.yaml")
        save_config(config, config_path)

        print(f"Saved configuration to: {config_path}")
        print("\nSaved file contents:")
        with open(config_path, "r") as f:
            print(f.read())

        # Verify we can load it back
        loaded = Config(**config.__dict__)
        print(f"Verification: Loaded poll_interval = {loaded.poll_interval}")

    finally:
        shutil.rmtree(tmpdir)


def demo_priority_order():
    """Demonstrate configuration priority order."""
    print_section("6. Priority Order Demonstration")

    print("Priority order (highest to lowest):")
    print("  1. Environment variables")
    print("  2. YAML configuration file")
    print("  3. Default values")
    print()

    tmpdir = tempfile.mkdtemp()
    try:
        config_path = os.path.join(tmpdir, "config.yaml")
        with open(config_path, "w") as f:
            f.write("""
poll_interval: 2.5
max_retries: 5
timeout: 600.0
""")

        # Set only env for poll_interval
        os.environ["TASK_QUEUE_POLL_INTERVAL"] = "10.0"

        reset_config()
        config = load_config(config_path=config_path)

        print("Example result:")
        print(f"  poll_interval: {config.poll_interval}s (from ENV - highest priority)")
        print(f"  max_retries: {config.max_retries} (from YAML)")
        print(f"  timeout: {config.timeout}s (from YAML)")
        print(f"  max_concurrent_tasks: {config.max_concurrent_tasks} (from DEFAULT - lowest priority)")

        del os.environ["TASK_QUEUE_POLL_INTERVAL"]

    finally:
        shutil.rmtree(tmpdir)


def demo_multiple_backends():
    """Demonstrate configuration for multiple backends."""
    print_section("7. Multiple Backend Configuration")

    tmpdir = tempfile.mkdtemp()
    try:
        config_path = os.path.join(tmpdir, "multi_backend.yaml")
        yaml_content = """
queue_backend: redis

backends:
  redis:
    host: redis.example.com
    port: 6379
    db: 1
    password: secret123
    socket_timeout: 10

  sqlite:
    path: /data/backup_tasks.db
"""
        with open(config_path, "w") as f:
            f.write(yaml_content)

        reset_config()
        config = load_config(config_path=config_path)

        print("Configuration loaded with multiple backend settings:")
        print(f"\nActive backend: {config.queue_backend}")
        print(f"\nRedis settings:")
        print(f"  Host: {config.redis_host}")
        print(f"  Port: {config.redis_port}")
        print(f"  DB: {config.redis_db}")
        print(f"  Password: {config.redis_password}")
        print(f"  Socket Timeout: {config.redis_socket_timeout}s")
        print(f"\nSQLite settings:")
        print(f"  Path: {config.sqlite_path}")

    finally:
        shutil.rmtree(tmpdir)


def demo_env_prefix():
    """Demonstrate custom environment variable prefix."""
    print_section("8. Custom Environment Variable Prefix")

    # Set custom env vars
    os.environ["MYAPP_QUEUE_BACKEND"] = "redis"
    os.environ["MYAPP_POLL_INTERVAL"] = "7.5"

    print("Set environment variables:")
    print("  MYAPP_QUEUE_BACKEND=redis")
    print("  MYAPP_POLL_INTERVAL=7.5")

    reset_config()
    config = load_config(env_prefix="MYAPP_")

    print(f"\nLoaded with custom prefix:")
    print(f"  Queue Backend: {config.queue_backend}")
    print(f"  Poll Interval: {config.poll_interval}s")

    # Clean up
    del os.environ["MYAPP_QUEUE_BACKEND"]
    del os.environ["MYAPP_POLL_INTERVAL"]


def main():
    """Run all configuration demos."""
    print("\n" + "=" * 70)
    print("  Python Task Queue Library - Configuration System Demo")
    print("=" * 70)

    try:
        demo_default_config()
        demo_custom_config()
        demo_yaml_config()
        demo_env_override()
        demo_priority_order()
        demo_save_config()
        demo_multiple_backends()
        demo_env_prefix()

        print_section("Demo Complete!")
        print("\nAll configuration features demonstrated successfully.")
        print("\nKey features:")
        print("  ✓ Default configuration values")
        print("  ✓ Custom configuration via code")
        print("  ✓ YAML file loading")
        print("  ✓ Environment variable override")
        print("  ✓ Priority-based merging")
        print("  ✓ Configuration persistence")
        print("  ✓ Multiple backend support")
        print("  ✓ Custom env variable prefixes")
        print()

    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()