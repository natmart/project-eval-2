#!/usr/bin/env python3
"""
Test runner script for SQLite backend tests.
"""

import sys
import subprocess
import os


def run_tests():
    """Run the SQLite backend tests."""
    # Change to the tests directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Run pytest with the test file
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "test_sqlite_backend.py",
            "-v",
            "--tb=short",
            "--color=yes",
        ],
        capture_output=False,
    )

    return result.returncode


if __name__ == "__main__":
    print("=" * 70)
    print("Running SQLite Backend Tests")
    print("=" * 70)
    print()

    exit_code = run_tests()

    print()
    print("=" * 70)
    if exit_code == 0:
        print("✓ All tests passed!")
    else:
        print(f"✗ Tests failed with exit code {exit_code}")
    print("=" * 70)

    sys.exit(exit_code)