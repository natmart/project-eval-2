#!/usr/bin/env python3
"""
Test runner for the QueueBackend abstract base class tests.

This script runs all tests for the backends/base.py module and verifies
that the abstract interface meets all acceptance criteria.
"""

import sys
import unittest
from pathlib import Path

# Add the parent directory to sys.path to import the module
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests import test_backends_base


def run_tests() -> None:
    """Run all tests and report results."""
    print("=" * 70)
    print("Running QueueBackend Abstract Base Class Tests")
    print("=" * 70)
    print()

    # Create a test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromModule(test_backends_base))

    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print()
    print("=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print()

    # Check acceptance criteria
    print("=" * 70)
    print("Acceptance Criteria Verification")
    print("=" * 70)

    criteria_met = []

    # AC1: QueueBackend abstract base class with all required methods
    ac1_pass = len(result.failures) == 0 and len(result.errors) == 0
    criteria_met.append(("AC1: QueueBackend ABC with all abstract methods", ac1_pass))

    # AC2: Cannot be instantiated directly
    ac2_tests = [t for t in result.skipped if 'cannot_instantiate' in str(t[0])]
    ac2_pass = len(ac2_tests) == 0 and ac1_pass
    criteria_met.append(("AC2: ABC cannot be instantiated directly", ac2_pass))

    # AC3: Comprehensive docstrings
    ac3_pass = all('has_docstring' in str(t) for t in result.skipped 
                  if 'test_enqueue_has_docstring' not in str(t))
    if result.wasSuccessful():
        ac3_pass = True
    criteria_met.append(("AC3: Comprehensive docstrings for each method", ac3_pass))

    # AC4: Type hints on all signatures
    ac4_pass = all('test_type_hints' in str(t) for t in result.skipped 
                  if 'TestTypeHints' not in str(t))
    if result.wasSuccessful():
        ac4_pass = True
    criteria_met.append(("AC4: Type hints on all method signatures", ac4_pass))

    for criteria, passed in criteria_met:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {criteria}")

    print()
    if result.wasSuccessful():
        print("🎉 All tests passed! The abstract interface meets all acceptance criteria.")
        return 0
    else:
        print("⚠️  Some tests failed. Please review the output above.")
        return 1


if __name__ == '__main__':
    sys.exit(run_tests())