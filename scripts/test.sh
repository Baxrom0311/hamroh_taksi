#!/bin/bash
# scripts/test.sh
# 
# TEST RUNNER SCRIPT
# 
# ISHLATISH:
# ./scripts/test.sh             # Barcha testlar
# ./scripts/test.sh unit         # Faqat unit testlar
# ./scripts/test.sh integration  # Faqat integration testlar
# ./scripts/test.sh coverage     # Coverage report

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🧪 Starting tests...${NC}\n"

# Test type
TEST_TYPE=${1:-all}

# Activate virtual environment if exists
if [ -d ".venv" ]; then
    echo -e "${YELLOW}📦 Activating virtual environment...${NC}"
    source .venv/bin/activate
fi

# Check if pytest installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}❌ pytest not installed!${NC}"
    echo "Install with: pip install pytest pytest-asyncio pytest-cov"
    exit 1
fi

# Run tests based on type
case $TEST_TYPE in
    unit)
        echo -e "${GREEN}Running unit tests...${NC}\n"
        pytest tests/test_models/ tests/test_services/ -v
        ;;
    
    integration)
        echo -e "${GREEN}Running integration tests...${NC}\n"
        pytest tests/test_integration/ -v
        ;;
    
    coverage)
        echo -e "${GREEN}Running tests with coverage...${NC}\n"
        pytest tests/ -v \
            --cov=app \
            --cov-report=html \
            --cov-report=term-missing
        
        echo -e "\n${GREEN}✅ Coverage report generated: htmlcov/index.html${NC}"
        ;;
    
    quick)
        echo -e "${GREEN}Running quick smoke test...${NC}\n"
        pytest tests/ -v -k "test_database_connection or test_models_import" --maxfail=1
        ;;
    
    all|*)
        echo -e "${GREEN}Running all tests...${NC}\n"
        pytest tests/ -v
        ;;
esac

# Exit code
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}✅ All tests passed!${NC}"
else
    echo -e "\n${RED}❌ Tests failed with exit code $EXIT_CODE${NC}"
fi

exit $EXIT_CODE
