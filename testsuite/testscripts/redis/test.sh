#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PKG_DIR="${TESTSUITE_ROOT}/redis"
bin_dir=$1

wd=`pwd`

cd "$PKG_DIR"

# Clean old .gcda files to avoid stamp mismatch with .gcno files
if find "${PKG_DIR}" -name "*.gcno" -type f 2>/dev/null | grep -q .; then
    echo "Coverage build detected - cleaning old .gcda files..."
    find "${PKG_DIR}" -name "*.gcda" -type f -delete 2>/dev/null || true
fi

ls -1 ${bin_dir}/* | grep -v "\.so" | xargs -I {} cp {} ./src/

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOGFILE="$PKG_DIR/test_run_$TIMESTAMP.log"

./runtest --large-memory &> $LOGFILE

awk '
BEGIN {
  IGNORECASE=1
  passed=failed=skipped=0
}

# Bracketed markers
/^\[[[:space:]]*ok[[:space:]]*\][[:space:]]*:?/        { passed++;  next }
/^\[[[:space:]]*(ignore|skip(ped)?|todo|xfail)[[:space:]]*\][[:space:]]*:?/ { skipped++; next }
/^\[[[:space:]]*(err(or)?|fail(ed)?|fatal)[[:space:]]*\][[:space:]]*:?/     { failed++;  next }

# TAP fallback
/^(ok)[[:space:]]/ && $0 !~ /^\[/                        { passed++;  next }
/^not[[:space:]]+ok/ && $0 !~ /^\[/                      { failed++;  next }
/^(ok|not[[:space:]]+ok).*#[[:space:]]*(SKIP|TODO)/      { skipped++; next }

END {
  printf("Passed : %d\nFailed : %d\nSkipped : %d\n", passed, failed, skipped)
}
' "${LOGFILE}"

source "${TESTSUITE_ROOT}/lib/coverage.sh"
collect_coverage "${PKG_DIR}" "${TIMESTAMP}"
