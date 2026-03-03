#!/usr/bin/env python3
"""
Simple verification script for integration test components.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("Verifying Integration Test Components")
print("=" * 70)
print()

# Test 1: Import all modules
print("Test 1: Importing core modules...")
try:
    from python_task_queue.models import Task, TaskStatus, TaskResult
    print("  ✓ Models imported")
except Exception as e:
    print(f"  ✗ Models import failed: {e}")
    sys.exit(1)

try:
    from python_task_queue.backends import InMemoryBackend, SQLiteBackend
    print("  ✓ Backends imported")
except Exception as e:
    print(f"  ✗ Backends import failed: {e}")
    sys.exit(1)

try:
    from python_task_queue.worker import Worker, WorkerStats
    print("  ✓ Worker imported")
except Exception as e:
    print(f"  ✗ Worker import failed: {e}")
    sys.exit(1)

try:
    from python_task_queue.registry import TaskRegistry
    print("  ✓ Registry imported")
except Exception as e:
    print(f"  ✗ Registry import failed: {e}")
    sys.exit(1)

try:
    from python_task_queue.retry import simple_retry_policy
    print("  ✓ Retry imported")
except Exception as e:
    print(f"  ✗ Retry import failed: {e}")
    sys.exit(1)

try:
    from python_task_queue.dlq import DeadLetterQueue, DeadLetterTask
    print("  ✓ DLQ imported")
except Exception as e:
    print(f"  ✗ DLQ import failed: {e}")
    sys.exit(1)

try:
    from python_task_queue.scheduler import CronScheduler, ScheduledJob
    print("  ✓ Scheduler imported")
except Exception as e:
    print(f"  ✗ Scheduler import failed: {e}")
    sys.exit(1)

try:
    from python_task_queue.monitoring import Monitoring, WorkerMetric
    print("  ✓ Monitoring imported")
except Exception as e:
    print(f"  ✗ Monitoring import failed: {e}")
    sys.exit(1)

print()
print("Test 2: Creating backend instances...")
try:
    mem_backend = InMemoryBackend()
    print("  ✓ InMemoryBackend created")
except Exception as e:
    print(f"  ✗ InMemoryBackend creation failed: {e}")
    sys.exit(1)

try:
    sqlite_backend = SQLiteBackend(":memory:")
    print("  ✓ SQLiteBackend created")
except Exception as e:
    print(f"  ✗ SQLiteBackend creation failed: {e}")
    sys.exit(1)

print()
print("Test 3: Creating DLQ instance...")
try:
    dlq = DeadLetterQueue()
    print("  ✓ DeadLetterQueue created")
except Exception as e:
    print(f"  ✗ DeadLetterQueue creation failed: {e}")
    sys.exit(1)

print()
print("Test 4: Creating Scheduler instance...")
try:
    scheduler = CronScheduler()
    print("  ✓ CronScheduler created")
except Exception as e:
    print(f"  ✗ CronScheduler creation failed: {e}")
    sys.exit(1)

print()
print("Test 5: Monitoring instance...")
try:
    monitoring = Monitoring()
    print("  ✓ Monitoring created")
except Exception as e:
    print(f"  ✗ Monitoring creation failed: {e}")
    sys.exit(1)

print()
print("Test 6: Creating Worker instance...")
try:
    registry = TaskRegistry()
    worker = Worker(backend=mem_backend, registry=registry)
    print("  ✓ Worker created")
except Exception as e:
    print(f"  ✗ Worker creation failed: {e}")
    sys.exit(1)

print()
print("Test 7: Verifying test modules can be imported...")
try:
    from tests import test_integration
    print("  ✓ test_integration module imported")
except Exception as e:
    print(f"  ✗ test_integration import failed: {e}")
    sys.exit(1)

try:
    from tests import test_sqlite_backend_integration
    print("  ✓ test_sqlite_backend_integration module imported")
except Exception as e:
    print(f"  ✗ test_sqlite_backend_integration import failed: {e}")
    sys.exit(1)

try:
    from tests import test_dlq_integration
    print("  ✓ test_dlq_integration module imported")
except Exception as e:
    print(f"  ✗ test_dlq_integration import failed: {e}")
    sys.exit(1)

try:
    from tests import test_scheduler_integration
    print("  ✓ test_scheduler_integration module imported")
except Exception as e:
    print(f"  ✗ test_scheduler_integration import failed: {e}")
    sys.exit(1)

print()
print("=" * 70)
print("✓ All verification tests passed!")
print("=" * 70)
print()
print("Integration test components are ready:")
print("  - test_integration.py")
print("  - test_sqlite_backend_integration.py")
print("  - test_dlq_integration.py")
print("  - test_scheduler_integration.py")
print("  - run_integration_tests.py")
print()
print("To run all integration tests:")
print("  python tests/run_integration_tests.py")
print()
print("To run a specific test class:")
print("  python tests/run_integration_tests.py --class TaskLifecycle")
print()