#!/usr/bin/env python3
"""
Test runner for Scheduler tests.

This script runs the Scheduler test suite and outputs the results.
"""

import sys

# Add parent directory to path for imports
sys.path.insert(0, '..')

import pytest

if __name__ == "__main__":
    # Run the Scheduler tests
    exit_code = pytest.main([
        "test_scheduler.py",
        "-v",
        "--tb=short",
        "--strict-markers",
    ])
    
    sys.exit(exit_code)