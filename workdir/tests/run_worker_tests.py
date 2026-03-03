#!/usr/bin/env python3
"""
Test runner for worker tests.
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import tests
from tests.test_worker import (
    TestWorkerStats,
    TestWorkerInitialization,
    TestWorkerLifecycle,
    TestTaskProcessing,
    TestRetryLogic,
    TestMiddleware,
    TestStatistics,
    TestGracefulShutdown,
    TestErrorHandling,
    TestIntegration,
)


def run_tests():
    """Run all worker tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestWorkerStats))
    suite.addTests(loader.loadTestsFromTestCase(TestWorkerInitialization))
    suite.addTests(loader.loadTestsFromTestCase(TestWorkerLifecycle))
    suite.addTests(loader.loadTestsFromTestCase(TestTaskProcessing))
    suite.addTests(loader.loadTestsFromTestCase(TestRetryLogic))
    suite.addTests(loader.loadTestsFromTestCase(TestMiddleware))
    suite.addTests(loader.loadTestsFromTestCase(TestStatistics))
    suite.addTests(loader.loadTestsFromTestCase(TestGracefulShutdown))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandling))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())