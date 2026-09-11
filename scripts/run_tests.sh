#!/bin/bash
# Test runner script for FEMA CRIA
# Usage: ./scripts/run_tests.sh [unit|integration|coverage|all|watch]

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Banner
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}   FEMA CRIA Test Runner${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Determine test type
TEST_TYPE="${1:-all}"

case "$TEST_TYPE" in
    unit)
        echo -e "${YELLOW}Running unit tests only...${NC}"
        pytest -m unit -v
        ;;
    integration)
        echo -e "${YELLOW}Running integration tests only...${NC}"
        pytest -m integration -v
        ;;
    coverage)
        echo -e "${YELLOW}Running all tests with coverage...${NC}"
        pytest --cov=src --cov-report=html --cov-report=term -v
        echo ""
        echo -e "${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        ;;
    watch)
        echo -e "${YELLOW}Running tests in watch mode...${NC}"
        echo -e "${YELLOW}(requires pytest-watch: pip install pytest-watch)${NC}"
        ptw -- -v
        ;;
    failed)
        echo -e "${YELLOW}Re-running failed tests...${NC}"
        pytest --lf -v
        ;;
    quick)
        echo -e "${YELLOW}Running quick sanity check (unit tests, no slow)${NC}"
        pytest -m "unit and not slow" -v --tb=line
        ;;
    all|*)
        echo -e "${YELLOW}Running all tests...${NC}"
        pytest -v
        ;;
esac

# Exit code
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Tests passed!${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}✗ Tests failed!${NC}"
    exit 1
fi
