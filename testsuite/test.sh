#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


prog=$1
bin_path=$2

TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
export TESTSUITE_ROOT

prog_path="${TESTSUITE_ROOT}/${prog}"

echo "========================================="
echo "Testing program: ${prog}"
echo "Binary path: ${bin_path}"
echo "========================================="

# Check if test script exists
if [ ! -f "${TESTSUITE_ROOT}/testscripts/${prog}/test.sh" ]; then
    echo "ERROR: Test script not found: ${TESTSUITE_ROOT}/testscripts/${prog}/test.sh"
    exit 1
fi

# Check if binary path exists
if [ ! -d "${bin_path}" ] && [ ! -f "${bin_path}" ]; then
    echo "ERROR: Binary path not found: ${bin_path}"
    exit 1
fi

# Run the test directly from testscripts (no copying)
echo ""
echo "Running tests for ${prog}..."
echo ""

${TESTSUITE_ROOT}/testscripts/${prog}/test.sh ${bin_path}
TEST_EXIT_CODE=$?

echo ""
echo "========================================="
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "Tests completed for ${prog}"
else
    echo "Tests completed with errors for ${prog} (exit code: $TEST_EXIT_CODE)"
fi

# Check if coverage was collected
LATEST_COVERAGE=$(ls -td ${prog_path}/coverage_* 2>/dev/null | head -1)
if [ -n "${LATEST_COVERAGE}" ]; then
    echo ""
    echo "Coverage Report Available:"
    echo "   HTML: ${LATEST_COVERAGE}/html/index.html"
    echo "   Data: ${LATEST_COVERAGE}/coverage_filtered.info"

    # Show quick coverage summary
    if [ -f "${LATEST_COVERAGE}/coverage_filtered.info" ]; then
        echo ""
        echo "Coverage Summary:"
        lcov --list "${LATEST_COVERAGE}/coverage_filtered.info" 2>/dev/null | tail -2 || echo "   (Summary not available)"
    fi
fi

echo "========================================="
echo ""

exit $TEST_EXIT_CODE
