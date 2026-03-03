#!/usr/bin/env python3
"""
Test runner script for configuration system tests.
"""

import sys
import subprocess


def main():
    """Run the configuration system tests."""
    print("=" * 70)
    print("Running Configuration System Tests")
    print("=" * 70)
    print()

    # Run pytest with verbose output
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_config.py", "-v", "--tb=short"],
        cwd=".",
        env={"PYTHONPATH": "."},
    )

    print()
    print("=" * 70)
    if result.returncode == 0:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
    print("=" * 70)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())