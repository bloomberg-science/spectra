#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


# Script to verify that test_all.sh will use correct paths

BIN_BASE_PATH=${1:-"gcc-coverage/O2/fulldbg"}
TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")" && pwd)}"

echo "========================================="
echo "Path Verification for test_all.sh"
echo "========================================="
echo "TESTSUITE_ROOT: ${TESTSUITE_ROOT}"
echo "Base Path: ${BIN_BASE_PATH}"
echo ""

packages=("nginx" "apache" "redis" "postgresql" "mysql" "memcached" "proftpd" "lighttpd" "bind" "comdb2")

echo "Expected Binary Paths:"
echo ""

for pkg in "${packages[@]}"; do
    case "${pkg}" in
        nginx|proftpd|lighttpd)
            bin_path="${TESTSUITE_ROOT}/${BIN_BASE_PATH}/${pkg}/sbin"
            ;;
        *)
            bin_path="${TESTSUITE_ROOT}/${BIN_BASE_PATH}/${pkg}/bin"
            ;;
    esac

    # Check if path exists
    if [ -d "${bin_path}" ]; then
        status="EXISTS"
    else
        status="NOT FOUND"
    fi

    echo "${status} ${pkg}: ${bin_path}"
done

echo ""
echo "========================================="
echo "Summary:"
echo ""
echo "For coverage testing, use:"
echo "  ./test_all.sh gcc-coverage/O2/fulldbg"
echo ""
echo "For standard testing, use:"
echo "  ./test_all.sh gcc/O2/fulldbg"
echo "========================================="
