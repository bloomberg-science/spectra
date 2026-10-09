#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PKG_DIR="${TESTSUITE_ROOT}/nginx"
TEST_DIR="${PKG_DIR}/nginx-tests"
bin_path=$1

wd=`pwd`

LOG_DIR="${TEST_DIR}/test_logs"
mkdir -p $LOG_DIR

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOGFILE="$LOG_DIR/test_run_$TIMESTAMP.log"

cd ${PKG_DIR}

# Clean old .gcda files to avoid stamp mismatch with .gcno files
# This ensures fresh coverage data for each test run
if find "${PKG_DIR}" -name "*.gcno" -type f 2>/dev/null | grep -q .; then
    echo "Coverage build detected - cleaning old .gcda files..."
    find "${PKG_DIR}" -name "*.gcda" -type f -delete 2>/dev/null || true
fi

cd ./nginx-tests

TEST_NGINX_BINARY=${bin_path}/nginx prove . &> ${LOGFILE}

cd ${wd}

awk '
BEGIN { passed=failed=skipped=0; in_sum=0 }

# Enter summary block when we see the header
/^Test Summary Report/ { in_sum=1; next }

# Leave summary block at totals or explicit result line
in_sum && (/^Files=/ || /^Result:/) { in_sum=0 }

# In the summary block, each test file line indicates a failure
in_sum && $0 ~ /^\.\// { failed++; next }

# Per-file lines: count skipped
$0 ~ /^\.\// && $0 ~ /skipped:/ { skipped++; next }

# Per-file lines: count ok
$0 ~ /^\.\// && $0 ~ /(^|[[:space:]])ok([[:space:]]|$)/ { passed++; next }

END {
  total = passed + failed + skipped;
  print "Passed:",  passed;
  print "Failed:",  failed;
  print "Skipped:", skipped;
  print "Total:",   total;
}
' "$LOGFILE"

source "${TESTSUITE_ROOT}/lib/coverage.sh"
collect_coverage "${PKG_DIR}" "${TIMESTAMP}"
