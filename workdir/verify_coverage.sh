#!/bin/bash
#
# Coverage Verification Script for Python Task Queue Library
# This script verifies 80% test coverage across all modules
#

set -e

echo "================================"
echo "Coverage Verification Script"
echo "================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python installation
echo "Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON=python3
    echo "Found python3"
elif command -v python &> /dev/null; then
    PYTHON=python
    echo "Found python"
else
    echo -e "${RED}ERROR: Python not found in PATH${NC}"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$($PYTHON --version 2>&1)
echo "Using: $PYTHON_VERSION"
echo ""

# Install dependencies
echo "Installing dependencies..."
$PYTHON -m pip install pytest pytest-cov pytest-asyncio click pyyaml --quiet --upgrade
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Install package in development mode
echo "Installing package in development mode..."
$PYTHON -m pip install -e . --quiet
echo -e "${GREEN}✓ Package installed${NC}"
echo ""

# Run coverage
echo "Running coverage tests..."
echo "================================"

$PYTHON -m pytest tests/ \
    --cov=python_task_queue \
    --cov-report=term-missing \
    --cov-report=html:htmlcov \
    --cov-report=xml:coverage.xml \
    --cov-report=json:coverage.json \
    -v \
    --tb=short

echo ""
echo "================================"
echo "Coverage Summary"
echo "================================"

# Calculate actual coverage if coverage.txt exists
if [ -f coverage.json ]; then
    TOTAL_COVERAGE=$($PYTHON -c "import json; data=json.load(open('coverage.json')); print(f'{data[\"totals\"][\"percent_covered\"]:.1f}')")
    
    echo "Total Coverage: ${TOTAL_COVERAGE}%"
    echo ""

    # Check if coverage meets threshold
    THRESHOLD=80
    COVERAGE_FLOAT=$(echo "$TOTAL_COVERAGE" | awk '{printf "%.0f", $1}')
    
    if [ $COVERAGE_FLOAT -ge $THRESHOLD ]; then
        echo -e "${GREEN}✓ Coverage meets the ${THRESHOLD}% threshold!${NC}"
        exit 0
    else
        echo -e "${RED}✗ Coverage below ${THRESHOLD}% threshold${NC}"
        echo ""
        echo "Modules with low coverage:"
        $PYTHON -c "
import json
data = json.load(open('coverage.json'))
threshold = 80
for file, metrics in data['files'].items():
    if file.startswith('python_task_queue/'):
        percent = metrics['summary']['percent_covered']
        if percent < threshold:
            print(f'  {file}: {percent:.1f}%')
            lines = metrics['summary']['num_statements'] - metrics['summary']['covered_lines']
            if lines > 0:
                print(f'    Missing: {lines} lines')
"
        exit 1
    fi
else
    echo -e "${YELLOW}Warning: coverage.json not generated${NC}"
    exit 1
fi