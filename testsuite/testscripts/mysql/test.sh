#!/usr/bin/env bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

set -euo pipefail

TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PKG_DIR="${TESTSUITE_ROOT}/mysql"

wd=$PWD
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOGFILE="$PKG_DIR/test_run_$TIMESTAMP.log"

usage() {
  echo "Usage: $0 <INSTALL_DIR>" >&2
  exit 1
}

[[ $# -ge 1 ]] || usage
INSTALL_DIR="$1"

cd "$PKG_DIR"

# Detect if this is a coverage build by checking if .gcno files exist
IS_COVERAGE_BUILD=0
if find "${PKG_DIR}" -name "*.gcno" -type f 2>/dev/null | grep -q .; then
    IS_COVERAGE_BUILD=1
    echo "Coverage build detected - cleaning old .gcda files..."
    find "${PKG_DIR}" -name "*.gcda" -type f -delete 2>/dev/null || true
fi

BIN_DIR="$INSTALL_DIR"
[[ -d "$BIN_DIR" ]] || { echo "No such bin dir: $BIN_DIR" >&2; exit 1; }

# If test_install is missing, build+install it (only for non-coverage builds)
if [[ ! -d "test_install" ]]; then
  if [ $IS_COVERAGE_BUILD -eq 0 ]; then
      echo "Test installation not found...creating" >&2
      echo "Standard build detected - rebuilding for tests"
      rm -rf build
      mkdir -p build
      cd build
      cmake -DCMAKE_INSTALL_PREFIX="$PKG_DIR/test_install" -DWITH_SSL=system ..
      make -j20
      make install
      cd "$PKG_DIR"
  else
      echo "Coverage build detected - skipping rebuild to preserve coverage data"
      echo "NOTE: Using coverage binaries from: ${BIN_DIR}"
      # For coverage builds, copy from install_dir to test_install
      cp -r "${BIN_DIR}/.." "${PKG_DIR}/test_install"
  fi
fi

TEST_DIR="$PKG_DIR/test_install/mysql-test"

echo "Bin dir: $BIN_DIR"
ls -1 "$BIN_DIR"/*

cp $BIN_DIR/* $PKG_DIR/test_install/bin/

cd "$TEST_DIR"

# Disable strict error checking - tests are expected to fail sometimes
set +e

export MTR_MAX_TEST_FAIL=0
./mtr --parallel=16 --nounit-tests --force &> "$LOGFILE"

# Strip ANSI color codes, then parse
awk '
BEGIN{
  IGNORECASE=1
  pass=fail=skip=0
  have_completed=0
  run_total=0
  failed_completed=0
  skipped_from_summary=-1
}

/^\[[[:space:]]*[0-9]+%] .* \[[[:space:]]*(pass|ok|fail|failed|skipped)[[:space:]]*\]/ {
  if (match($0, /\[[[:space:]]*(pass|ok|fail|failed|skipped)[[:space:]]*\]/, m)) {
    s=tolower(m[1])
    if (s=="pass" || s=="ok") pass++
    else if (s=="fail" || s=="failed") fail++
    else if (s=="skipped") skip++
  }
  next
}

/Completed:/ {
  if (match($0, /Failed[[:space:]]+([0-9]+)\/([0-9]+)[[:space:]]+tests/, m)) {
    failed_completed = m[1]+0
    run_total        = m[2]+0
    have_completed   = 1
  }
  next
}

/^[[:space:]]*[0-9]+[[:space:]]+tests[[:space:]]+were[[:space:]]+skipped/ {
  if (match($0, /^[[:space:]]*([0-9]+)/, m)) skipped_from_summary = m[1]+0
  next
}

END{
  if (have_completed) {
    failed = failed_completed
    ran    = run_total
    skipped = (skipped_from_summary >= 0) ? skipped_from_summary : skip
    passed  = ran - failed
    total   = ran + skipped
  } else {
    # Fallback: derive from counted lines
    failed = fail
    skipped = skip
    passed = pass
    total = passed + failed + skipped
  }
  printf("Passed : %d\nFailed : %d\nSkipped : %d\nTotal : %d\n", passed, failed, skipped, total)
}' "${LOGFILE}"


cd "$wd"

source "${TESTSUITE_ROOT}/lib/coverage.sh"
collect_coverage "${PKG_DIR}" "${TIMESTAMP}"

