#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PKG_DIR="${TESTSUITE_ROOT}/apache"
TEST_DIR="${PKG_DIR}/test"
bin_dir=$1

wd=`pwd`

cd ${PKG_DIR}

# Detect if this is a coverage build by checking if .gcno files exist
IS_COVERAGE_BUILD=0
if find "${PKG_DIR}" -name "*.gcno" -type f 2>/dev/null | grep -q .; then
    IS_COVERAGE_BUILD=1
fi

if [[ ! -d "test_install" ]]; then
  echo "Test installation not found...creating" >&2
  mkdir test_install

  # Only rebuild if NOT a coverage build, to avoid destroying .gcno files
  if [ $IS_COVERAGE_BUILD -eq 0 ]; then
      echo "Standard build detected - rebuilding for tests"
      make clean
      ./configure --prefix=${PKG_DIR}/test_install --enable-http2 --enable-proxy --enable-proxy-http2
      make
      make install
  else
      echo "Coverage build detected - skipping rebuild to preserve coverage data"
      echo "Using coverage binaries from: ${bin_dir}"
  fi
fi

# ====== Config =======
CONFIG_FILE="${TEST_DIR}/pyhttpd/config.ini"
NEW_PREFIX="${PKG_DIR}/test_install"
NEW_BIN_DIR="${NEW_PREFIX}/bin"
NEW_SBIN_DIR="${NEW_PREFIX}/bin"
NEW_LIB_DIR="${NEW_PREFIX}/lib"
NEW_LIBEXEC_DIR="${NEW_PREFIX}/modules"
LOG_DIR="${TEST_DIR}/test_logs"
# =====================

cp ${bin_dir}/httpd ${NEW_BIN_DIR}/httpd

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"


# Update the prefix line in config.ini
echo "[INFO] Updating prefix in $CONFIG_FILE..."
sed -i "s|^prefix *=.*|prefix = $NEW_PREFIX|" "$CONFIG_FILE"
sed -i "s|^bindir *=.*|bindir = $NEW_BIN_DIR|" "$CONFIG_FILE"
sed -i "s|^sbindir *=.*|sbindir = $NEW_SBIN_DIR|" "$CONFIG_FILE"
sed -i "s|^libdir *=.*|libdir = $NEW_LIB_DIR|" "$CONFIG_FILE"
sed -i "s|^libexecdir *=.*|libexecdir = $NEW_LIBEXEC_DIR|" "$CONFIG_FILE"
sed -i "s|^apxs *=.*|apxs = $NEW_BIN_DIR/apxs|" "$CONFIG_FILE"

# Confirm the update
echo "[INFO] New config line:"
grep "^prefix" "$CONFIG_FILE"

# Run purest and save output to log
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOGFILE="$LOG_DIR/pytest_run_$TIMESTAMP.log"

echo "[INFO] Running tests with pytest..."
cd ${TEST_DIR}
pytest &> "$LOGFILE"
EXIT_CODE=$?

cd ${wd}

# Display summary
echo "[INFO] Test run complete."
echo "[INFO] Log saved to: $LOGFILE"
echo "[INFO] Exit code: $EXIT_CODE"

# Optionally display stats summary from log
#!/usr/bin/env bash
# parse_pytest_summary.sh <logfile>

summary=$(grep -E "====" "$LOGFILE" | tail -n 1)

# Extract counts
passed=$(echo "$summary"  | grep -oE '[0-9]+ passed'  | awk '{print $1}')
failed=$(echo "$summary"  | grep -oE '[0-9]+ failed'  | awk '{print $1}')
skipped=$(echo "$summary" | grep -oE '[0-9]+ skipped' | awk '{print $1}')
errors=$(echo "$summary"  | grep -oE '[0-9]+ error'   | awk '{print $1}')

# Default to 0 if not present
passed=${passed:-0}
failed=${failed:-0}
skipped=${skipped:-0}
errors=${errors:-0}

# Compute total
total=$((passed + failed + skipped + errors))

echo "Summary:"
echo "  Passed : $passed"
echo "  Failed : $failed"
echo "  Skipped: $skipped"
echo "  Errors : $errors"
echo "  Total  : $total"

source "${TESTSUITE_ROOT}/lib/coverage.sh"
collect_coverage "${PKG_DIR}" "${TIMESTAMP}"
