"""
Tests for the task registry system.

Tests cover:
- Task registration and retrieval
- Decorator-based registration
- Task discovery
- Signature validation
- Error handling
"""

import unittest
import inspect
import tempfile
import sys
from pathlib import Path

from python_task_queue.registry import (
    TaskRegistry,
    RegistrationError,
    DuplicateTaskError,
    InvalidHandlerError,
    TaskNotFoundError,
    TaskInfo,
    get_registry,
    task,
)


class TestRegistryBasic(unittest.TestCase):
    """Basic registry functionality tests."""

    def setUp(self):
        """Create a fresh registry for each test."""
        self.registry = TaskRegistry()

    def test_register_simple_task(self) -> None:
        """Test registering a simple task handler."""

        def my_task(payload):
            return payload * 2

        self.registry.register("my_task", my_task)
        result = self.registry.get("my_task")

        self.assertEqual(result.handler, my_task)
        self.assertEqual(result.name, "my_task")

    def test_register_and_execute(self) -> None:
        """Test registering and executing a task handler."""

        def add_numbers(payload):
            return payload["a"] + payload["b"]

        self.registry.register("add", add_numbers)

        handler = self.registry.get_handler("add")
        result = handler({"a": 5, "b": 3})

        self.assertEqual(result, 8)

    def test_get_nonexistent_task(self) -> None:
        """Test retrieving a non-existent task raises error."""
        with self.assertRaises(TaskNotFoundError):
            self.registry.get("nonexistent")

    def test_get_handler_nonexistent(self) -> None:
        """Test retrieving handler for non-existent task."""
        with self.assertRaises(TaskNotFoundError):
            self.registry.get_handler("nonexistent")

    def test_has_task(self) -> None:
        """Test checking if a task is registered."""

        def my_task(payload):
            return payload

        self.assertFalse(self.registry.has("my_task"))

        self.registry.register("my_task", my_task)

        self.assertTrue(self.registry.has("my_task"))

    def test_list_tasks(self) -> None:
        """Test listing all registered tasks."""

        def task1(payload):
            return 1

        def task2(payload):
            return 2

        self.registry.register("task1", task1)
        self.registry.register("task2", task2)

        tasks = self.registry.list()

        self.assertEqual(len(tasks), 2)
        task_names = {t.name for t in tasks}
        self.assertEqual(task_names, {"task1", "task2"})


class TestDecoratorRegistration(unittest.TestCase):
    """Tests for the @task decorator."""

    def test_task_decorator(self) -> None:
        """Test using the @task decorator."""
        registry = TaskRegistry()

        @task(name="decorated_task", registry=registry)
        def my_handler(payload):
            return payload

        self.assertTrue(registry.has("decorated_task"))
        handler = registry.get_handler("decorated_task")
        self.assertEqual(handler({"test": "data"}), {"test": "data"})

    def test_task_decorator_default_name(self) -> None:
        """Test @task decorator with default name from function."""
        registry = TaskRegistry()

        @task(registry=registry)
        def my_function(payload):
            return payload

        self.assertTrue(registry.has("my_function"))

    def test_task_decorator_with_metadata(self) -> None:
        """Test @task decorator with metadata."""
        registry = TaskRegistry()

        @task(name="meta_task", registry=registry, version="1.0", author="test")
        def handler(payload):
            return payload

        task_info = registry.get("meta_task")
        self.assertEqual(task_info.metadata.get("version"), "1.0")
        self.assertEqual(task_info.metadata.get("author"), "test")


class TestDuplicateRegistration(unittest.TestCase):
    """Tests for duplicate task registration."""

    def test_duplicate_task_raises_error(self) -> None:
        """Test registering duplicate task raises DuplicateTaskError."""
        registry = TaskRegistry()

        def handler1(payload):
            return 1

        def handler2(payload):
            return 2

        registry.register("task", handler1)

        with self.assertRaises(DuplicateTaskError):
            registry.register("task", handler2)

    def test_duplicate_with_allow_replace(self) -> None:
        """Test registering duplicate with allow_replace=True works."""
        registry = TaskRegistry()

        def handler1(payload):
            return 1

        def handler2(payload):
            return 2

        registry.register("task", handler1)
        registry.register("task", handler2, allow_replace=True)

        result = registry.get_handler("task")({})
        self.assertEqual(result, 2)

    def test_duplicate_error_details(self) -> None:
        """Test DuplicateTaskError contains proper details."""
        registry = TaskRegistry()

        def original(payload):
            return "original"

        def duplicate(payload):
            return "duplicate"

        registry.register("task", original)

        with self.assertRaises(DuplicateTaskError) as ctx:
            registry.register("task", duplicate)

        error = ctx.exception
        self.assertEqual(error.task_name, "thread")
        self.assertEqual(error.existing_handler, original)
        self.assertEqual(error.new_handler, duplicate)


class TestSignatureValidation(unittest.TestCase):
    """Tests for handler signature validation."""

    def test_valid_signature(self) -> None:
        """Test handler with valid signature passes validation."""
        registry = TaskRegistry()

        def valid_handler(payload, **kwargs):
            return payload

        # Should not raise
        registry.register("valid", valid_handler)

    def test_invalid_signature_no_args(self) -> None:
        """Test handler without required arguments raises error."""
        registry = TaskRegistry()

        def invalid_handler():
            return "ok"

        with self.assertRaises(InvalidHandlerError):
            registry.register("invalid", invalid_handler)

    def test_invalid_signature_too_many_required(self) -> None:
        """Test handler with too many required arguments."""
        registry = TaskRegistry()

        def invalid_handler(payload, required_arg, another_arg):
            return "ok"

        with self.assertRaises(InvalidHandlerError):
            registry.register("invalid", invalid_handler)

    def test_skip_validation(self) -> None:
        """Test skipping signature validation allows any signature."""
        registry = TaskRegistry()

        def any_signature():
            return "ok"

        # Should not raise when validation is skipped
        registry.register("any", any_signature, validate_signature=False)

        self.assertTrue(registry.has("any"))


class TestTaskDiscovery(unittest.TestCase):
    """Tests for task discovery from modules."""

    def test_discover_from_module_dict(self) -> None:
        """Test discovering tasks from a module's globals."""
        registry = TaskRegistry()

        # Create a fake module namespace
        module_dict = {
            "task1": lambda payload: 1,
            "task2": lambda payload: 2,
            "_private": lambda payload: 3,
            "not_a_task": "string",
        }

        registry.discover_from_dict(module_dict)

        # Should discover task1 and task2 (callables, not private)
        self.assertTrue(registry.has("task1"))
        self.assertTrue(registry.has("task2"))
        self.assertFalse(registry.has("_private"))
        self.assertFalse(registry.has("not_a_task"))

    def test_discover_from_file(self) -> None:
        """Test discovering tasks from a Python file."""
        registry = TaskRegistry()

        # Create a temporary module file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("def discovered_task(payload):\n")
            f.write("    return payload\n")
            f.write("\n")
            f.write("# Not callable\n")
            f.write("CONSTANT = 42\n")
            module_path = f.name

        try:
            registry.discover_from_file(module_path)

            self.assertTrue(registry.has("discovered_task"))
            self.assertFalse(registry.has("CONSTANT"))
        finally:
            Path(module_path).unlink()

    def test_discover_with_prefix(self) -> None:
        """Test discovering tasks with a name prefix."""
        registry = TaskRegistry()

        module_dict = {
            "task_one": lambda payload: 1,
            "task_two": lambda payload: 2,
        }

        registry.discover_from_dict(module_dict, prefix="myapp.")

        self.assertTrue(registry.has("myapp.task_one"))
        self.assertTrue(registry.has("myapp.task_two"))


class TestTaskInfo(unittest.TestCase):
    """Tests for TaskInfo data class."""

    def test_task_info_creation(self) -> None:
        """Test creating TaskInfo object."""
        import time

        def sample_handler(payload):
            return payload

        signature = inspect.signature(sample_handler)
        registered_at = time.time()

        task_info = TaskInfo(
            name="sample",
            handler=sample_handler,
            module="__main__",
            signature=signature,
            metadata={"version": "1.0"},
            registered_at=registered_at,
        )

        self.assertEqual(task_info.name, "sample")
        self.assertEqual(task_info.handler, sample_handler)
        self.assertEqual(task_info.module, "__main__")
        self.assertEqual(task_info.signature, signature)
        self.assertEqual(task_info.metadata["version"], "1.0")
        self.assertEqual(task_info.registered_at, registered_at)


class TestGetRegistry(unittest.TestCase):
    """Tests for the get_registry singleton."""

    def tearDown(self) -> None:
        """Clean up registry singleton after tests."""
        # Reset registry singleton (implementation dependent)
        try:
            from python_task_queue.registry import _default_registry
            _default_registry.clear()
        except AttributeError:
            pass

    def test_get_registry_singleton(self) -> None:
        """Test get_registry returns same instance."""
        registry1 = get_registry()
        registry2 = get_registry()

        self.assertIs(registry1, registry2)

    def test_get_registry_is_task_registry(self) -> None:
        """Test get_registry returns TaskRegistry instance."""
        registry = get_registry()
        self.assertIsInstance(registry, TaskRegistry)

    def test_get_registry_persists_across_calls(self) -> None:
        """Test tasks persist across get_registry calls."""
        registry1 = get_registry()

        def sample(payload):
            return payload

        registry1.register("sample", sample)

        registry2 = get_registry()
        self.assertTrue(registry2.has("sample"))


class TestRegistryThreadSafety(unittest.TestCase):
    """Tests for thread safety in registry operations."""

    def test_concurrent_registration(self) -> None:
        """Test concurrent registrations don't cause issues."""
        import threading

        registry = TaskRegistry()
        errors = []
        num_threads = 10

        def register_task(i):
            try:
                def handler(payload):
                    return i

                registry.register(f"task_{i}", handler)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_task, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(registry.list()), num_threads)


if __name__ == "__main__":
    unittest.main()