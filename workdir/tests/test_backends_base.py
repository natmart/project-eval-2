"""
Tests for the QueueBackend abstract base class.

This module verifies that:
1. QueueBackend is an abstract base class that cannot be instantiated
2. All required methods are properly marked as abstract
3. Method signatures match the expected interface
4. All methods have proper docstrings
"""

import inspect
import sys
import unittest
from abc import ABC
from uuid import UUID, uuid4

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from python_task_queue.backends.base import QueueBackend, QueueBackendError, TaskNotFoundError
from python_task_queue.models import Task, TaskStatus


class TestQueueBackendABC(unittest.TestCase):
    """Test that QueueBackend is a proper abstract base class."""

    def test_is_abstract_base_class(self):
        """Verify that QueueBackend inherits from ABC."""
        self.assertTrue(
            ABC in QueueBackend.__mro__,
            "QueueBackend should inherit from ABC"
        )

    def test_cannot_instantiate_directly(self):
        """Verify that QueueBackend cannot be instantiated directly."""
        with self.assertRaises(TypeError) as cm:
            QueueBackend()

        self.assertIn("abstract", str(cm.exception).lower())

    def test_has_abc_meta_metaclass(self):
        """Verify that QueueBackend uses ABCMeta metaclass."""
        from abc import ABCMeta
        self.assertIsInstance(
            QueueBackend,
            ABCMeta,
            "QueueBackend should have ABCMeta as its metaclass"
        )

    def test_all_required_methods_are_abstract(self):
        """Verify that all required methods are marked as abstract."""
        required_methods = {
            'enqueue',
            'dequeue',
            'peek',
            'size',
            'acknowledge',
            'fail',
            'get_task',
            'list_tasks',
        }

        abstract_methods = QueueBackend.__abstractmethods__

        for method_name in required_methods:
            self.assertIn(
                method_name,
                abstract_methods,
                f"{method_name} should be marked as abstract"
            )

        # Ensure we have at least these methods
        self.assertTrue(
            required_methods.issubset(abstract_methods),
            f"Missing abstract methods: {required_methods - abstract_methods}"
        )


class TestConcreteBackend(unittest.TestCase):
    """Test that a concrete backend can be created when all methods are implemented."""

    def test_concrete_implementation_can_be_instantiated(self):
        """Verify that a concrete implementation can be instantiated."""
        class MinimalBackend(QueueBackend):
            def __init__(self):
                self.tasks = []

            def enqueue(self, task: Task) -> None:
                self.tasks.append(task)

            def dequeue(self) -> Task | None:
                return self.tasks.pop(0) if self.tasks else None

            def peek(self) -> Task | None:
                return self.tasks[0] if self.tasks else None

            def size(self) -> int:
                return len(self.tasks)

            def acknowledge(self, task_id: UUID) -> None:
                pass

            def fail(self, task_id: UUID, error: str) -> None:
                pass

            def get_task(self, task_id: UUID) -> Task | None:
                for task in self.tasks:
                    if task.id == task_id:
                        return task
                return None

            def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
                if status is None:
                    return self.tasks.copy()
                return [t for t in self.tasks if t.status == status]

        # This should not raise TypeError
        backend = MinimalBackend()

        # Verify it's an instance of QueueBackend
        self.assertIsInstance(backend, QueueBackend)

    def test_partial_implementation_raises_error(self):
        """Verify that a partial implementation still raises TypeError."""
        class PartialBackend(QueueBackend):
            def enqueue(self, task: Task) -> None:
                pass

            # Missing other methods

        with self.assertRaises(TypeError) as cm:
            PartialBackend()

        self.assertIn("abstract", str(cm.exception).lower())


class TestMethodSignatures(unittest.TestCase):
    """Test that all abstract methods have correct signatures."""

    def test_enqueue_signature(self):
        """Verify enqueue method signature."""
        sig = inspect.signature(QueueBackend.enqueue)
        params = list(sig.parameters.keys())

        self.assertIn('self', params)
        self.assertIn('task', params)

        param = sig.parameters['task']
        self.assertEqual(param.annotation, Task)
        self.assertEqual(sig.return_annotation, None)

    def test_dequeue_signature(self):
        """Verify dequeue method signature."""
        sig = inspect.signature(QueueBackend.dequeue)
        params = list(sig.parameters.keys())

        self.assertEqual(params, ['self'])

        # Return type should be Optional[Task]
        self.assertIn('None', inspect.getsource(QueueBackend.dequeue))

    def test_peek_signature(self):
        """Verify peek method signature."""
        sig = inspect.signature(QueueBackend.peek)
        params = list(sig.parameters.keys())

        self.assertEqual(params, ['self'])

    def test_size_signature(self):
        """Verify size method signature."""
        sig = inspect.signature(QueueBackend.size)
        params = list(sig.parameters.keys())

        self.assertEqual(params, ['self'])

        param = sig.return_annotation
        self.assertIn('int', str(param))

    def test_acknowledge_signature(self):
        """Verify acknowledge method signature."""
        sig = inspect.signature(QueueBackend.acknowledge)
        params = list(sig.parameters.keys())

        self.assertIn('task_id', params)
        param = sig.parameters['task_id']
        self.assertIn('UUID', str(param.annotation))

    def test_fail_signature(self):
        """Verify fail method signature."""
        sig = inspect.signature(QueueBackend.fail)
        params = list(sig.parameters.keys())

        self.assertIn('task_id', params)
        self.assertIn('error', params)

        param = sig.parameters['task_id']
        self.assertIn('UUID', str(param.annotation))

        param = sig.parameters['error']
        self.assertIn('str', str(param.annotation))

    def test_get_task_signature(self):
        """Verify get_task method signature."""
        sig = inspect.signature(QueueBackend.get_task)
        params = list(sig.parameters.keys())

        self.assertIn('task_id', params)

        param = sig.parameters['task_id']
        self.assertIn('UUID', str(param.annotation))

    def test_list_tasks_signature(self):
        """Verify list_tasks method signature."""
        sig = inspect.signature(QueueBackend.list_tasks)
        params = list(sig.parameters.keys())

        self.assertIn('status', params)

        param = sig.parameters['status']
        self.assertIn('Optional', str(param.annotation))


class TestMethodDocstrings(unittest.TestCase):
    """Test that all abstract methods have proper docstrings."""

    def test_enqueue_has_docstring(self):
        """Verify that enqueue has a docstring."""
        self.assertIsNotNone(QueueBackend.enqueue.__doc__)
        self.assertGreater(len(QueueBackend.enqueue.__doc__), 50)

    def test_dequeue_has_docstring(self):
        """Verify that dequeue has a docstring."""
        self.assertIsNotNone(QueueBackend.dequeue.__doc__)
        self.assertGreater(len(QueueBackend.dequeue.__doc__), 50)

    def test_peek_has_docstring(self):
        """Verify that peek has a docstring."""
        self.assertIsNotNone(QueueBackend.peek.__doc__)
        self.assertGreater(len(QueueBackend.peek.__doc__), 50)

    def test_size_has_docstring(self):
        """Verify that size has a docstring."""
        self.assertIsNotNone(QueueBackend.size.__doc__)
        self.assertGreater(len(QueueBackend.size.__doc__), 50)

    def test_acknowledge_has_docstring(self):
        """Verify that acknowledge has a docstring."""
        self.assertIsNotNone(QueueBackend.acknowledge.__doc__)
        self.assertGreater(len(QueueBackend.acknowledge.__doc__), 50)

    def test_fail_has_docstring(self):
        """Verify that fail has a docstring."""
        self.assertIsNotNone(QueueBackend.fail.__doc__)
        self.assertGreater(len(QueueBackend.fail.__doc__), 50)

    def test_get_task_has_docstring(self):
        """Verify that get_task has a docstring."""
        self.assertIsNotNone(QueueBackend.get_task.__doc__)
        self.assertGreater(len(QueueBackend.get_task.__doc__), 50)

    def test_list_tasks_has_docstring(self):
        """Verify that list_tasks has a docstring."""
        self.assertIsNotNone(QueueBackend.list_tasks.__doc__)
        self.assertGreater(len(QueueBackend.list_tasks.__doc__), 50)

    def test_class_has_docstring(self):
        """Verify that QueueBackend class has a docstring."""
        self.assertIsNotNone(QueueBackend.__doc__)
        self.assertGreater(len(QueueBackend.__doc__), 100)


class TestCustomExceptions(unittest.TestCase):
    """Test the custom exception classes."""

    def test_queue_backend_error_exists(self):
        """Verify that QueueBackendError exists and is an Exception."""
        self.assertTrue(issubclass(QueueBackendError, Exception))

    def test_task_not_found_error_exists(self):
        """Verify that TaskNotFoundError exists and is a QueueBackendError."""
        self.assertTrue(issubclass(TaskNotFoundError, QueueBackendError))

    def test_task_not_found_error_accepts_task_id(self):
        """Verify that TaskNotFoundError can be initialized with a task_id."""
        task_id = uuid4()
        error = TaskNotFoundError(task_id)

        self.assertEqual(error.task_id, task_id)
        self.assertIn(str(task_id), str(error))

    def test_task_not_found_error_custom_message(self):
        """Verify that TaskNotFoundError accepts a custom message."""
        task_id = uuid4()
        custom_message = "Custom error message"
        error = TaskNotFoundError(task_id, custom_message)

        self.assertEqual(error.task_id, task_id)
        self.assertIn(custom_message, str(error))


class TestAbstractMethodContracts(unittest.TestCase):
    """Test the behavior of abstract methods through a simple implementation."""

    def setUp(self):
        """Create a simple backend for testing."""
        class SimpleBackend(QueueBackend):
            def __init__(self):
                self._tasks = []

            def enqueue(self, task: Task) -> None:
                self._tasks.append(task)

            def dequeue(self) -> Task | None:
                return self._tasks.pop(0) if self._tasks else None

            def peek(self) -> Task | None:
                return self._tasks[0] if self._tasks else None

            def size(self) -> int:
                return len(self._tasks)

            def acknowledge(self, task_id: UUID) -> None:
                self._tasks = [t for t in self._tasks if t.id != task_id]

            def fail(self, task_id: UUID, error: str) -> None:
                self._tasks = [t for t in self._tasks if t.id != task_id]

            def get_task(self, task_id: UUID) -> Task | None:
                for task in self._tasks:
                    if task.id == task_id:
                        return task
                return None

            def list_tasks(self, status: TaskStatus | None = None) -> list[Task]:
                if status is None:
                    return self._tasks.copy()
                return [t for t in self._tasks if t.status == status]

        self.backend = SimpleBackend()

    def test_enqueue_adds_task(self):
        """Verify that enqueue adds a task to the backend."""
        task = Task(name="test_task")
        self.assertEqual(self.backend.size(), 0)

        self.backend.enqueue(task)
        self.assertEqual(self.backend.size(), 1)

    def test_dequeue_removes_task(self):
        """Verify that dequeue removes and returns a task."""
        task = Task(name="test_task")
        self.backend.enqueue(task)

        dequeued = self.backend.dequeue()
        self.assertIsNotNone(dequeued)
        self.assertEqual(dequeued.id, task.id)
        self.assertEqual(self.backend.size(), 0)

    def test_dequeue_returns_none_when_empty(self):
        """Verify that dequeue returns None when the queue is empty."""
        result = self.backend.dequeue()
        self.assertIsNone(result)

    def test_peek_does_not_remove_task(self):
        """Verify that peek returns a task without removing it."""
        task = Task(name="test_task")
        self.backend.enqueue(task)

        peeked = self.backend.peek()
        self.assertIsNotNone(peeked)
        self.assertEqual(peeked.id, task.id)
        self.assertEqual(self.backend.size(), 1)

    def test_peek_returns_none_when_empty(self):
        """Verify that peek returns None when the queue is empty."""
        result = self.backend.peek()
        self.assertIsNone(result)

    def test_get_task_returns_correct_task(self):
        """Verify that get_task returns the correct task."""
        task = Task(name="test_task")
        self.backend.enqueue(task)

        retrieved = self.backend.get_task(task.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, task.id)

    def test_get_task_returns_none_for_missing_task(self):
        """Verify that get_task returns None for a non-existent task."""
        result = self.backend.get_task(uuid4())
        self.assertIsNone(result)

    def test_list_tasks_returns_all_tasks(self):
        """Verify that list_tasks returns all tasks when no filter is given."""
        task1 = Task(name="task1")
        task2 = Task(name="task2")
        self.backend.enqueue(task1)
        self.backend.enqueue(task2)

        tasks = self.backend.list_tasks()
        self.assertEqual(len(tasks), 2)

    def test_list_tasks_filters_by_status(self):
        """Verify that list_tasks can filter by status."""
        task1 = Task(name="task1")
        task2 = Task(name="task2")
        task2.status = TaskStatus.COMPLETED
        self.backend.enqueue(task1)
        self.backend.enqueue(task2)

        pending_tasks = self.backend.list_tasks(TaskStatus.PENDING)
        completed_tasks = self.backend.list_tasks(TaskStatus.COMPLETED)

        self.assertEqual(len(pending_tasks), 1)
        self.assertEqual(pending_tasks[0].id, task1.id)
        self.assertEqual(len(completed_tasks), 1)
        self.assertEqual(completed_tasks[0].id, task2.id)

    def test_acknowledge_removes_task(self):
        """Verify that acknowledge removes a task."""
        task = Task(name="test_task")
        self.backend.enqueue(task)

        self.backend.acknowledge(task.id)
        self.assertEqual(self.backend.size(), 0)

    def test_fail_removes_task(self):
        """Verify that fail removes a task."""
        task = Task(name="test_task")
        self.backend.enqueue(task)

        self.backend.fail(task.id, "Test error")
        self.assertEqual(self.backend.size(), 0)


class TestTypeHints(unittest.TestCase):
    """Test that methods have proper type hints."""

    def test_enqueue_type_hints(self):
        """Verify enqueue has type hints in signature."""
        sig = inspect.signature(QueueBackend.enqueue)
        # Task parameter is annotated
        self.assertIsNotNone(sig.parameters['task'].annotation)

    def test_dequeue_type_hints(self):
        """Verify dequeue has type hints in return annotation."""
        sig = inspect.signature(QueueBackend.dequeue)
        return_annotation = str(sig.return_annotation)
        self.assertIn('Optional', return_annotation)

    def test_peek_type_hints(self):
        """Verify peek has type hints in return annotation."""
        sig = inspect.signature(QueueBackend.peek)
        return_annotation = str(sig.return_annotation)
        self.assertIn('Optional', return_annotation)

    def test_size_type_hints(self):
        """Verify size has type hints in return annotation."""
        sig = inspect.signature(QueueBackend.size)
        self.assertEqual(sig.return_annotation.__name__, 'int')

    def test_get_task_type_hints(self):
        """Verify get_task has type hints for parameter and return."""
        sig = inspect.signature(QueueBackend.get_task)
        # Check parameter annotation
        param_annotation = str(sig.parameters['task_id'].annotation)
        self.assertIn('UUID', param_annotation)
        # Check return annotation
        return_annotation = str(sig.return_annotation)
        self.assertIn('Optional', return_annotation)

    def test_list_tasks_type_hints(self):
        """Verify list_tasks has type hints for parameter and return."""
        sig = inspect.signature(QueueBackend.list_tasks)
        # Check parameter annotation
        param_annotation = str(sig.parameters['status'].annotation)
        self.assertIn('Optional', param_annotation)
        # Check return annotation
        return_annotation = str(sig.return_annotation)
        self.assertIn('List', return_annotation)


class TestDocumentationQuality(unittest.TestCase):
    """Test the quality of documentation."""

    def test_docstring_contains_args_sections(self):
        """Verify method docstrings contain Args sections."""
        methods_to_check = [
            'enqueue', 'acknowledge', 'fail', 'get_task', 'list_tasks'
        ]
        for method_name in methods_to_check:
            method = getattr(QueueBackend, method_name)
            doc = method.__doc__
            self.assertIn('Args:', doc, f"{method_name} docstring should have Args section")

    def test_docstring_contains_returns_sections(self):
        """Verify method docstrings contain Returns sections."""
        methods_to_check = ['dequeue', 'peek', 'size', 'get_task', 'list_tasks']
        for method_name in methods_to_check:
            method = getattr(QueueBackend, method_name)
            doc = method.__doc__
            self.assertIn('Returns:', doc, f"{method_name} docstring should have Returns section")

    def test_docstring_contains_raises_sections(self):
        """Verify method docstrings contain Raises sections where appropriate."""
        methods_to_check = ['enqueue', 'acknowledge', 'fail']
        for method_name in methods_to_check:
            method = getattr(QueueBackend, method_name)
            doc = method.__doc__
            self.assertIn('Raises:', doc, f"{method_name} docstring should have Raises section")

    def test_class_docstring_contains_examples(self):
        """Verify class docstring contains examples."""
        doc = QueueBackend.__doc__
        self.assertIn('Examples', doc, "Class docstring should have Examples section")

    def test_method_docstrings_contain_notes(self):
        """Verify method docstrings contain Notes sections."""
        methods_to_check = ['enqueue', 'dequeue', 'acknowledge', 'fail']
        for method_name in methods_to_check:
            method = getattr(QueueBackend, method_name)
            doc = method.__doc__
            self.assertIn('Notes:', doc, f"{method_name} docstring should have Notes section")


if __name__ == '__main__':
    unittest.main(verbosity=2)