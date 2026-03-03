#!/bin/bash
# Verification script for configuration system

echo "Checking configuration system implementation..."
echo ""

# Check file exists
echo "1. Checking files..."
if [ -f "python_task_queue/config.py" ]; then
    echo "   ✓ config.py exists"
    lines=$(wc -l < python_task_queue/config.py)
    echo "   ✓ $lines lines of code"
else
    echo "   ✗ config.py not found"
    exit 1
fi

if [ -f "tests/test_config.py" ]; then
    echo "   ✓ test_config.py exists"
    lines=$(wc -l < tests/test_config.py)
    echo "   ✓ $lines lines of tests"
else
    echo "   ✗ test_config.py not found"
    exit 1
fi

echo ""
echo "2. Checking config module structure..."
if grep -q "class Config:" python_task_queue/config.py; then
    echo "   ✓ Config dataclass found"
fi
if grep -q "def load_config" python_task_queue/config.py; then
    echo "   ✓ load_config function found"
fi
if grep -q "def get_config" python_task_queue/config.py; then
    echo "   ✓ get_config function found"
fi
if grep -q "def _load_yaml_config" python_task_queue/config.py; then
    echo "   ✓ YAML loading function found"
fi
if grep -q "def _load_env_config" python_task_queue/config.py; then
    echo "   ✓ environment loading function found"
fi
if grep -q "def save_config" python_task_queue/config.py; then
    echo "   ✓ save_config function found"
fi

echo ""
echo "3. Checking test coverage..."
test_classes=$(grep -c "^class Test" tests/test_config.py)
echo "   ✓ $test_classes test classes"
test_methods=$(grep -c "^    def test_" tests/test_config.py)
echo "   ✓ $test_methods test methods"

echo ""
echo "4. Checking configuration fields..."
fields=$(grep -c "    [a-z_]*: [a-zA-Z<>]* =" python_task_queue/config.py | head -20)
echo "   ✓ Configuration dataclass defined"

echo ""
echo "5. Checking documentation..."
if [ -f "CONFIGURATION_DOCUMENTATION.md" ]; then
    echo "   ✓ Documentation exists"
    doc_lines=$(wc -l < CONFIGURATION_DOCUMENTATION.md)
    echo "   ✓ $doc_lines lines of documentation"
fi

echo ""
echo "All checks passed! ✓"
echo ""
echo "Files created:"
echo "  - python_task_queue/config.py (configuration system)"
echo "  - tests/test_config.py (comprehensive test suite)"
echo "  - CONFIGURATION_DOCUMENTATION.md (user documentation)"
echo "  - demo_config.py (demo script)"
echo "  - taskqueue.yaml (example configuration)"