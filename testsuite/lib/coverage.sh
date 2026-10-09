#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

# Shared coverage collection helper.
# Usage: source this file, then call collect_coverage <pkg_dir> <timestamp> [title]

collect_coverage() {
    local PKG_DIR="$1"
    local TIMESTAMP="$2"
    local TITLE="${3:-$(basename "$PKG_DIR")}"

    echo ""
    echo "Checking for coverage data..."

    if ! find "${PKG_DIR}" -name "*.gcno" -type f 2>/dev/null | grep -q .; then
        echo "No coverage data found (not a coverage build)."
        return 0
    fi

    echo "Coverage build detected! Collecting coverage data..."

    local COVERAGE_DIR="${PKG_DIR}/coverage_${TIMESTAMP}"
    mkdir -p "${COVERAGE_DIR}"

    echo "Running lcov to capture coverage..."
    echo "Capturing coverage data from ${PKG_DIR}"
    lcov --capture \
         --directory "${PKG_DIR}" \
         --output-file "${COVERAGE_DIR}/coverage.info" \
         --ignore-errors source,gcov \
         --rc lcov_branch_coverage=0 \
         2>&1 | tee "${COVERAGE_DIR}/lcov_capture.log"

    if [ $? -eq 0 ] && [ -f "${COVERAGE_DIR}/coverage.info" ]; then
        echo "Filtering coverage data..."
        lcov --remove "${COVERAGE_DIR}/coverage.info" \
             '/usr/*' \
             '*/test/*' \
             '*/tests/*' \
             --output-file "${COVERAGE_DIR}/coverage_filtered.info" \
             2>&1 | tee -a "${COVERAGE_DIR}/lcov_capture.log"

        echo "Generating HTML coverage report..."
        genhtml "${COVERAGE_DIR}/coverage_filtered.info" \
                --output-directory "${COVERAGE_DIR}/html" \
                --title "${TITLE} Coverage Report" \
                --legend \
                2>&1 | tee "${COVERAGE_DIR}/genhtml.log"

        echo ""
        echo "========================================="
        echo "Coverage Report Generated!"
        echo "========================================="
        lcov --list "${COVERAGE_DIR}/coverage_filtered.info" | tail -20
        echo ""
        echo "HTML Report: ${COVERAGE_DIR}/html/index.html"
        echo "Coverage Data: ${COVERAGE_DIR}/coverage_filtered.info"
        echo "========================================="
    else
        echo "Warning: lcov capture failed. Check ${COVERAGE_DIR}/lcov_capture.log"
    fi
}
