#!/usr/bin/env python
"""
Test runner for retry policy system tests.
"""

import sys
import subprocess


def main():
    """Run retry policy tests."""
    print("=" * 70)
    print("Running Retry Policy System Tests")
    print("=" * 70)
    print()

    # Run pytest with verbose output
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_retry.py",
            "-v",
            "--tb=short",
            "--color=yes",
        ],
        cwd="workdir",
    )

    print()
    print("=" * 70)
    if result.returncode == 0:
        print("✓ All retry policy tests PASSED")
    else:
        print("✗ Some tests FAILED")
    print("=" * 70)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())