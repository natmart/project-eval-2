#!/usr/bin/env python3
"""
Test runner for Dead Letter Queue tests.

This script runs the comprehensive DLQ test suite and provides
detailed output about test results.
"""

import sys
import time
from pathlib import Path

# Add parent directory to path to import python_task_queue
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
except ImportError:
    print("pytest is required. Install with: pip install pytest")
    sys.exit(1)


def main():
    """Run the DLQ test suite."""
    test_file = Path(__file__).parent / "test_dlq.py"

    if not test_file.exists():
        print(f"Error: Test file not found: {test_file}")
        sys.exit(1)

    print("=" * 70)
    print("Running Dead Letter Queue Test Suite")
    print("=" * 70)
    print()

    start_time = time.time()

    # Run pytest with verbose output
    exit_code = pytest.main([
        str(test_file),
        "-v",
        "--tb=short",
        "--color=yes",
    ])

    elapsed = time.time() - start_time

    print()
    print("=" * 70)
    if exit_code == 0:
        print("✅ All DLQ tests passed!")
    else:
        print("❌ Some DLQ tests failed.")
    print(f"Time elapsed: {elapsed:.2f}s")
    print("=" * 70)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())