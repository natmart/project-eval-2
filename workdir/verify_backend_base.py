#!/usr/bin/env python3
"""
Verification script for the QueueBackend abstract base class.

This script verifies that:
1. The module can be imported
2. QueueBackend is defined as an abstract base class
3. All required methods exist
4. Custom exceptions are defined
"""

import sys
import inspect
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def verify_imports():
    """Verify that all imports work."""
    print("📦 Verifying imports...")
    try:
        from python_task_queue.backends.base import (
            QueueBackend,
            QueueBackendError,
            TaskNotFoundError
        )
        print("✅ Successfully imported QueueBackend, QueueBackendError, TaskNotFoundError")
        return True, (QueueBackend, QueueBackendError, TaskNotFoundError)
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False, None


def verify_abstract_class(QueueBackend):
    """Verify that QueueBackend is an abstract base class."""
    print("\n🔍 Verifying QueueBackend is an abstract base class...")

    from abc import ABC, ABCMeta

    # Check for ABC in MRO
    if ABC not in QueueBackend.__mro__:
        print("❌ QueueBackend does not inherit from ABC")
        return False
    print("✅ QueueBackend inherits from ABC")

    # Check metaclass
    if not isinstance(QueueBackend, ABCMeta):
        print("❌ QueueBackend does not use ABCMeta metaclass")
        return False
    print("✅ QueueBackend uses ABCMeta metaclass")

    # Check for abstract methods
    abstract_methods = QueueBackend.__abstractmethods__
    print(f"✅ Found {len(abstract_methods)} abstract methods")
    for method in sorted(abstract_methods):
        print(f"   - {method}")

    return True


def verify_required_methods(QueueBackend):
    """Verify that all required methods exist and are abstract."""
    print("\n📋 Verifying required methods...")

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

    found_methods = {m for m in dir(QueueBackend) if not m.startswith('_')}
    abstract_methods = QueueBackend.__abstractmethods__

    all_present = True
    for method in required_methods:
        if not hasattr(QueueBackend, method):
            print(f"❌ Method '{method}' not found")
            all_present = False
        elif method not in abstract_methods:
            print(f"⚠️  Method '{method}' exists but is not abstract")
            all_present = False
        else:
            print(f"✅ Method '{method}' is abstract")

    if all_present:
        print("✅ All 8 required methods are present and abstract")
    else:
        print(f"❌ Some required methods are missing or not abstract")

    return all_present


def verify_docstrings(QueueBackend):
    """Verify that all methods have docstrings."""
    print("\n📝 Verifying docstrings...")

    required_methods = ['enqueue', 'dequeue', 'peek', 'size', 'acknowledge', 'fail', 'get_task', 'list_tasks']

    all_have_docs = True
    for method_name in required_methods:
        method = getattr(QueueBackend, method_name)
        if not method.__doc__ or len(method.__doc__) < 50:
            print(f"⚠️  Method '{method_name}' has insufficient docstring")
            all_have_docs = False
        else:
            doc_length = len(method.__doc__)
            print(f"✅ Method '{method_name}' has docstring ({doc_length} characters)")

    # Check class docstring
    if not QueueBackend.__doc__ or len(QueueBackend.__doc__) < 100:
        print("⚠️  QueueBackend class has insufficient docstring")
        all_have_docs = False
    else:
        doc_length = len(QueueBackend.__doc__)
        print(f"✅ QueueBackend class has docstring ({doc_length} characters)")

    if all_have_docs:
        print("✅ All methods and class have proper docstrings")

    return all_have_docs


def verify_type_hints(QueueBackend):
    """Verify that methods have type hints."""
    print("\n💡 Verifying type hints...")

    required_methods = ['enqueue', 'dequeue', 'peek', 'size', 'acknowledge', 'fail', 'get_task', 'list_tasks']

    has_hints = True
    for method_name in required_methods:
        sig = inspect.signature(getattr(QueueBackend, method_name))
        if not sig.parameters:
            # Skip if no parameters (shouldn't happen with self)
            continue

        # Check if any parameter has an annotation
        params_with_annotations = sum(
            1 for p in sig.parameters.values()
            if p.annotation != inspect.Parameter.empty
        )
        return_annotation = sig.return_annotation != inspect.Signature.empty

        if params_with_annotations > 0 or return_annotation:
            print(f"✅ Method '{method_name}' has type hints")
        else:
            print(f"⚠️  Method '{method_name}' lacks type hints")
            has_hints = False

    if has_hints:
        print("✅ Methods have type hints")

    return has_hints


def verify_exceptions(QueueBackendError, TaskNotFoundError):
    """Verify that custom exceptions are properly defined."""
    print("\n⚠️  Verifying custom exceptions...")

    # Check QueueBackendError
    if not issubclass(QueueBackendError, Exception):
        print("❌ QueueBackendError is not a subclass of Exception")
        return False
    print("✅ QueueBackendError is a subclass of Exception")

    # Check TaskNotFoundError
    if not issubclass(TaskNotFoundError, QueueBackendError):
        print("❌ TaskNotFoundError is not a subclass of QueueBackendError")
        return False
    print("✅ TaskNotFoundError is a subclass of QueueBackendError")

    # Test instantiation
    try:
        from uuid import uuid4
        task_id = uuid4()
        error = TaskNotFoundError(task_id)
        if error.task_id != task_id:
            print("❌ TaskNotFoundError doesn't store task_id correctly")
            return False
        print("✅ TaskNotFoundError can be instantiated with task_id")
    except Exception as e:
        print(f"❌ TaskNotFoundError instantiation failed: {e}")
        return False

    # Test custom message
    try:
        from uuid import uuid4
        task_id = uuid4()
        custom_msg = "Custom message"
        error = TaskNotFoundError(task_id, custom_msg)
        if custom_msg not in str(error):
            print("❌ TaskNotFoundError doesn't use custom message")
            return False
        print("✅ TaskNotFoundError accepts custom message")
    except Exception as e:
        print(f"❌ TaskNotFoundError with custom message failed: {e}")
        return False

    return True


def verify_cannot_instantiate(QueueBackend):
    """Verify that QueueBackend cannot be instantiated directly."""
    print("\n🚫 Verifying that QueueBackend cannot be instantiated...")

    try:
        backend = QueueBackend()
        print("❌ QueueBackend was instantiated (should raise TypeError)")
        return False
    except TypeError as e:
        if "abstract" in str(e).lower():
            print(f"✅ QueueBackend raises TypeError when instantiated: {e}")
            return True
        else:
            print(f"⚠️  QueueBackend raises TypeError but message doesn't mention 'abstract': {e}")
            return True
    except Exception as e:
        print(f"⚠️  QueueBackend raised unexpected exception: {e}")
        return False


def main():
    """Run all verification checks."""
    print("=" * 70)
    print("🔎 QueueBackend Abstract Base Class Verification")
    print("=" * 70)

    results = {}

    # Import check
    import_ok, classes = verify_imports()
    if not import_ok:
        print("\n❌ Cannot proceed without successful imports")
        return 1

    QueueBackend, QueueBackendError, TaskNotFoundError = classes

    # Run all verifications
    results['Abstract Class'] = verify_abstract_class(QueueBackend)
    results['Required Methods'] = verify_required_methods(QueueBackend)
    results['Docstrings'] = verify_docstrings(QueueBackend)
    results['Type Hints'] = verify_type_hints(QueueBackend)
    results['Exceptions'] = verify_exceptions(QueueBackendError, TaskNotFoundError)
    results['Cannot Instantiate'] = verify_cannot_instantiate(QueueBackend)

    # Print summary
    print("\n" + "=" * 70)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 70)

    all_pass = True
    for check, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {check}")
        if not passed:
            all_pass = False

    # Check against acceptance criteria
    print("\n" + "=" * 70)
    print("🎯 ACCEPTANCE CRITERIA CHECK")
    print("=" * 70)

    ac_checks = [
        ("AC1: QueueBackend ABC with 8 abstract methods", results['Abstract Class'] and results['Required Methods']),
        ("AC2: ABCMeta used for metaclass", results['Abstract Class']),
        ("AC3: Comprehensive docstrings for each method", results['Docstrings']),
        ("AC4: Type hints on all method signatures", results['Type Hints']),
        ("AC5: Abstract nature raises TypeError", results['Cannot Instantiate']),
    ]

    for criteria, passed in ac_checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {criteria}")

    print()
    if all(results.values()):
        print("🎉 ALL VERIFICATIONS PASSED!")
        return 0
    else:
        print("⚠️  SOME VERIFICATIONS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())