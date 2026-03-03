#!/usr/bin/env python3
"""
Run and verify tests for the task queue models.

This script executes all model tests and provides a summary of results.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest

def run_tests():
    """Run all model tests and return results."""
    print("=" * 70)
    print("Running Task Queue Models Test Suite")
    print("=" * 70)
    print()
    
    # Run pytest with verbose output
    test_path = project_root / "tests" / "test_models.py"
    
    result = pytest.main([
        str(test_path),
        "-v",
        "--tb=short",
        "--color=yes",
        "-p", "no:warnings",
    ])
    
    print()
    print("=" * 70)
    if result == 0:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 70)
    
    return result

if __name__ == "__main__":
    sys.exit(run_tests())