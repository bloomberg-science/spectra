#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


# Script to run tests for all packages
# Usage: ./test_all.sh [bin_base_path] [package1 package2 ...]
#
# Examples:
#   ./test_all.sh                                    # Test all packages (standard builds)
#   ./test_all.sh gcc-coverage/O2/fulldbg            # Test all packages (coverage builds)
#   ./test_all.sh gcc/O2/fulldbg nginx redis         # Test specific packages

# Default binary base path (where built binaries are located)
BIN_BASE_PATH=${1:-"gcc/O2/fulldbg"}
shift  # Remove first argument so $@ contains only package names

TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
export TESTSUITE_ROOT

# Packages to test
if [ $# -gt 0 ]; then
    # Use packages specified on command line
    packages=("$@")
else
    # Auto-detect packages with test scripts
    packages=()
    for dir in ${TESTSUITE_ROOT}/testscripts/*/; do
        pkg=$(basename "$dir")
        if [ -f "${TESTSUITE_ROOT}/testscripts/${pkg}/test.sh" ] && [ "$pkg" != "bmq" ] && [ "$pkg" != "bde" ]; then
            packages+=("$pkg")
        fi
    done
fi

echo "========================================="
echo "TEST ALL PACKAGES"
echo "========================================="
echo "Binary base path: ${TESTSUITE_ROOT}/${BIN_BASE_PATH}"
echo "Packages to test: ${packages[@]}"
echo "Total: ${#packages[@]} packages"
echo "========================================="
echo ""

# Arrays to track results
declare -a successful_tests
declare -a failed_tests
declare -a skipped_tests
declare -A coverage_reports
declare -A test_stats  # Store "passed:failed:skipped" for each package

start_time=$(date +%s)

# Test each package
for pkg in "${packages[@]}"; do
    echo ""
    echo "========================================="
    echo "Testing: ${pkg}"
    echo "========================================="

    # Determine binary path based on package
    case "${pkg}" in
        nginx|proftpd|lighttpd)
            bin_path="${TESTSUITE_ROOT}/${BIN_BASE_PATH}/${pkg}/sbin"
            ;;
        apache|postgresql|mysql|redis|memcached|bind|comdb2)
            bin_path="${TESTSUITE_ROOT}/${BIN_BASE_PATH}/${pkg}/bin"
            ;;
        *)
            bin_path="${TESTSUITE_ROOT}/${BIN_BASE_PATH}/${pkg}/bin"
            ;;
    esac

    # Check if package directory exists
    if [ ! -d "${TESTSUITE_ROOT}/${pkg}" ]; then
        echo "WARNING: Package directory not found - SKIPPING"
        skipped_tests+=("${pkg}")
        continue
    fi

    # Check if test script exists
    if [ ! -f "${TESTSUITE_ROOT}/testscripts/${pkg}/test.sh" ]; then
        echo "WARNING: Test script not found - SKIPPING"
        skipped_tests+=("${pkg}")
        continue
    fi

    # Check if binary path exists
    if [ ! -d "${bin_path}" ] && [ ! -f "${bin_path}" ]; then
        echo "WARNING: Binary path not found: ${bin_path} - SKIPPING"
        echo "   (Package may not be built yet)"
        skipped_tests+=("${pkg}")
        continue
    fi

    # Run the test and capture output
    test_output=$(mktemp)
    ./test.sh "${pkg}" "${bin_path}" 2>&1 | tee "${test_output}"
    test_exit=$?

    # Extract test stats (Failed/Passed/Skipped) if present
    passed=$(grep -i -E '^\s*(Passed|pass)\s*:\s*[0-9]+' "${test_output}" | tail -1 | awk '{print $NF}' || echo "")
    failed=$(grep -i -E '^\s*(Failed|fail)\s*:\s*[0-9]+' "${test_output}" | tail -1 | awk '{print $NF}' || echo "")
    skipped=$(grep -i -E '^\s*(Skipped|skip)\s*:\s*[0-9]+' "${test_output}" | tail -1 | awk '{print $NF}' || echo "")

    # Extract coverage percentage if available
    coverage_pct=""
    LATEST_COV=$(ls -td ${TESTSUITE_ROOT}/${pkg}/coverage_* 2>/dev/null | head -1)
    if [ -n "${LATEST_COV}" ] && [ -f "${LATEST_COV}/coverage_filtered.info" ]; then
        coverage_reports["${pkg}"]="${LATEST_COV}"
        coverage_pct=$(lcov --list "${LATEST_COV}/coverage_filtered.info" 2>/dev/null | \
                       awk '/Total:/ {printf "%s / %s", $2, $4; exit}' || echo "")
    fi

    # Store test stats with coverage percentage
    if [ -n "${passed}" ] || [ -n "${failed}" ] || [ -n "${skipped}" ]; then
        test_stats["${pkg}"]="${passed:-0}:${failed:-0}:${skipped:-0}:${coverage_pct:-N/A}"
    fi

    rm -f "${test_output}"

    if [ $test_exit -eq 0 ]; then
        echo "SUCCESS: ${pkg} tests passed"
        successful_tests+=("${pkg}")
    else
        echo "FAILED: ${pkg} tests failed"
        failed_tests+=("${pkg}")
    fi
done

end_time=$(date +%s)
duration=$((end_time - start_time))

# Print summary
echo ""
echo ""
echo "========================================="
echo "TEST SUMMARY"
echo "========================================="
echo "Total time: ${duration} seconds"
echo ""

# Test results table
if [ ${#test_stats[@]} -gt 0 ]; then
    echo "Test Results:"
    echo ""
    printf "  %-15s %8s %8s %8s %18s\n" "Package" "Passed" "Failed" "Skipped" "Coverage (L/F)"
    printf "  %-15s %8s %8s %8s %18s\n" "-------" "------" "------" "-------" "---------------"

    # Show stats for all packages (successful + failed)
    for pkg in "${successful_tests[@]}" "${failed_tests[@]}"; do
        if [ -n "${test_stats[$pkg]}" ]; then
            IFS=':' read -r passed failed skipped coverage <<< "${test_stats[$pkg]}"
            printf "  %-15s %8s %8s %8s %18s\n" "${pkg}" "${passed}" "${failed}" "${skipped}" "${coverage:-N/A}"
        fi
    done
    echo ""
fi

echo "Successful (${#successful_tests[@]}):"
if [ ${#successful_tests[@]} -eq 0 ]; then
    echo "  (none)"
else
    for pkg in "${successful_tests[@]}"; do
        echo "  - ${pkg}"
    done
fi
echo ""

echo "Failed (${#failed_tests[@]}):"
if [ ${#failed_tests[@]} -eq 0 ]; then
    echo "  (none)"
else
    for pkg in "${failed_tests[@]}"; do
        echo "  - ${pkg}"
    done
fi
echo ""

if [ ${#skipped_tests[@]} -gt 0 ]; then
    echo "Skipped (${#skipped_tests[@]}):"
    for pkg in "${skipped_tests[@]}"; do
        echo "  - ${pkg}"
    done
    echo ""
fi

# Coverage report summary
if [ ${#coverage_reports[@]} -gt 0 ]; then
    echo "========================================="
    echo "COVERAGE REPORTS GENERATED"
    echo "========================================="
    for pkg in "${!coverage_reports[@]}"; do
        cov_dir="${coverage_reports[$pkg]}"
        echo ""
        echo "${pkg}:"
        echo "   HTML: ${cov_dir}/html/index.html"

        # Show coverage percentage if available
        if [ -f "${cov_dir}/coverage_filtered.info" ]; then
            coverage_pct=$(lcov --list "${cov_dir}/coverage_filtered.info" 2>/dev/null | grep "lines" | tail -1 | awk '{print $2}')
            if [ -n "${coverage_pct}" ]; then
                echo "   Coverage: ${coverage_pct}"
            fi
        fi
    done
    echo ""
    echo "========================================="
fi

echo ""

# Exit with error code if any package failed
if [ ${#failed_tests[@]} -gt 0 ]; then
    echo "Testing completed with ${#failed_tests[@]} failure(s)"
    exit 1
else
    echo "All tests passed successfully!"
    exit 0
fi
