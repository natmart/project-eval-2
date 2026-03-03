#!/usr/bin/env python
"""
Test runner for integration tests.

Run all integration tests to verify complete end-to-end functionality.
"""

import sys
import unittest
import argparse

# Import test modules
from tests.test_integration import (
    TaskLifecycleIntegrationTest,
    WorkerQueueRetryIntegrationTest,
    MultiWorkerIntegrationTest,
    ConfigurationIntegrationTest,
    MiddlewareIntegrationTest,
    BackendIntegrationTest,
    RegistryIntegrationTest,
    WorkerStatsIntegrationTest,
)

from tests.test_sqlite_backend_integration import SQLiteBackendIntegrationTest
from tests.test_dlq_integration import DLQIntegrationTest
from tests.test_scheduler_integration import SchedulerIntegrationTest


def run_suite(test_class=None, verbose=False):
    """
    Run test suite.

    Args:
        test_class: Specific test class to run, or None for all
        verbose: Whether to use verbose output

    Returns:
        True if all tests passed, False otherwise
    """
    if test_class:
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
    else:
        # Load all integration tests
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()

        # Add all test classes
        suite.addTests(loader.loadTestsFromTestCase(TaskLifecycleIntegrationTest))
        suite.addTests(loader.loadTestsFromTestCase(WorkerQueueRetryIntegrationTest))
        suite.addTests(loader.loadTestsFromTestCase(MultiWorkerIntegrationTest))
        suite.addTests(loader.loadTestsFromTestCase(ConfigurationIntegrationTest))
        suite.addTests(loader.loadTestsFromTestCase(MiddlewareIntegrationTest))
        suite.addTests(loader.loadTestsFromTestCase(BackendIntegrationTest))
        suite.addTests(loader.loadTestsFromTestCase(RegistryIntegrationTest))
        suite.addTests(loader.loadTestsFromTestCase(WorkerStatsIntegrationTest))
        suite.addTests(loader.loadTestsFromTestCase(SQLiteBackendIntegrationTest))
        suite.addTests(loader.loadTestsFromTestCase(DLQIntegrationTest))
        suite.addTests(loader.loadTestsFromTestCase(SchedulerIntegrationTest))

    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    result = runner.run(suite)

    return result.wasSuccessful()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run integration tests for Python Task Queue Library"
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    parser.add_argument(
        '--class',
        dest='test_class',
        choices=[
            'TaskLifecycle',
            'WorkerQueueRetry',
            'MultiWorker',
            'Configuration',
            'Middleware',
            'Backend',
            'Registry',
            'WorkerStats',
            'SQLiteBackend',
            'DLQ',
            'Scheduler',
        ],
        help='Run specific test class'
    )

    args = parser.parse_args()

    # Map class names to test classes
    class_map = {
        'TaskLifecycle': TaskLifecycleIntegrationTest,
        'WorkerQueueRetry': WorkerQueueRetryIntegrationTest,
        'MultiWorker': MultiWorkerIntegrationTest,
        'Configuration': ConfigurationIntegrationTest,
        'Middleware': MiddlewareIntegrationTest,
        'Backend': BackendIntegrationTest,
        'Registry': RegistryIntegrationTest,
        'WorkerStats': WorkerStatsIntegrationTest,
        'SQLiteBackend': SQLiteBackendIntegrationTest,
        'DLQ': DLQIntegrationTest,
        'Scheduler': SchedulerIntegrationTest,
    }

    test_class = class_map.get(args.test_class) if args.test_class else None

    print("=" * 70)
    print("Python Task Queue Library - Integration Tests")
    print("=" * 70)
    print()

    if test_class:
        print(f"Running test class: {test_class.__name__}")
    else:
        print("Running all integration tests")
    print()

    success = run_suite(test_class, verbose=args.verbose)

    print()
    print("=" * 70)
    if success:
        print("✓ All integration tests passed!")
        print("=" * 70)
        return 0
    else:
        print("✗ Some integration tests failed")
        print("=" * 70)
        return 1


if __name__ == '__main__':
    sys.exit(main())