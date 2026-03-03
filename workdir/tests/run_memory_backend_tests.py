#!/usr/bin/env python3
"""
Test runner for InMemoryBackend tests.

This script runs all tests for the InMemoryBackend implementation and
provides detailed output about test results.
"""

import sys
import unittest
import time

# Add the parent directory to the path to import the module
sys.path.insert(0, "..")

from tests.test_memory_backend import (
    TestInMemoryBackendBasic,
    TestInMemoryBackendPriority,
    TestInMemoryAcknowledge,
    TestInMemoryFail,
    TestInMemoryGetTask,
    TestInMemoryListTasks,
    TestInMemoryThreadSafety,
    TestInMemoryClear,
    TestInMemoryEdgeCases,
)


def run_tests():
    """Run all memory backend tests with detailed output."""
    print("\n" + "=" * 70)
    print("Running InMemoryBackend Test Suite")
    print("=" * 70 + "\n")
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestInMemoryBackendBasic))
    suite.addTests(loader.loadTestsFromTestCase(TestInMemoryBackendPriority))
    suite.addTests(loader.loadTestsFromTestCase(TestInMemoryAcknowledge))
    suite.addTests(loader.loadTestsFromTestCase(TestInMemoryFail))
    suite.addTests(loader.loadTestsFromTestCase(TestInMemoryGetTask))
    suite.addTests(loader.loadTestsFromTestCase(TestInMemoryListTasks))
    suite.addTests(loader.loadTestsFromTestCase(TestInMemoryThreadSafety))
    suite.addTests(loader.loadTestsFromTestCase(TestInMemoryClear))
    suite.addTests(loader.loadTestsFromTestCase(TestInMemoryEdgeCases))
    
    # Run tests
    start_time = time.time()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    end_time = time.time()
    
    # Print summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Time: {end_time - start_time:.2f} seconds")
    print("=" * 70 + "\n")
    
    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())