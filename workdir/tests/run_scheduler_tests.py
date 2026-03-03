#!/usr/bin/env python3
"""
Test runner for cron scheduler tests.
"""

import sys
import pytest


if __name__ == "__main__":
    # Run the scheduler tests
    exit_code = pytest.main([
        "test_scheduler.py",
        "-v",
        "--tb=short",
        "--color=yes",
    ])

    sys.exit(exit_code)