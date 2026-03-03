#!/usr/bin/env python3
"""
Test runner for DLQ tests.

This script runs the DLQ test suite and outputs the results.
"""

import sys

# Add parent directory to path for imports
sys.path.insert(0, '..')

import pytest

if __name__ == "__main__":
    # Run the DLQ tests
    exit_code = pytest.main([
        "test_dlq.py",
        "-v",
        "--tb=short",
        "--strict-markers",
    ])
    
    sys.exit(exit_code)