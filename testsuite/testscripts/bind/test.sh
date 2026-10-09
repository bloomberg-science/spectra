#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PKG_DIR="${TESTSUITE_ROOT}/bind"
install_dir=${PKG_DIR}/build-dir
bin_dir=$1

wd=`pwd`

cd "$PKG_DIR"

# Clean old .gcda files to avoid stamp mismatch with .gcno files
IS_COVERAGE_BUILD=0
if find "${PKG_DIR}" -name "*.gcno" -type f 2>/dev/null | grep -q .; then
    IS_COVERAGE_BUILD=1
    echo "Coverage build detected - cleaning old .gcda files..."
    find "${PKG_DIR}" -name "*.gcda" -type f -delete 2>/dev/null || true
fi

if [[ ! -d "$install_dir" ]]; then
  echo "Test installation not found...creating" >&2
  if [ $IS_COVERAGE_BUILD -eq 0 ]; then
      echo "Standard build detected - rebuilding for tests"
      meson setup build-dir
      meson compile -C build-dir
  else
      echo "Coverage build detected - skipping rebuild to preserve coverage data"
  fi
fi

# Always set up test dependencies (required for pytest to work)
if [[ -d "$install_dir" ]]; then
  echo "Setting up test dependencies..."
  ninja -C build-dir system-test-dependencies 2>&1 | grep -v "no work to do" || true
fi

find ${bin_dir} -maxdepth 1 -type f ! -name "*.so" -exec cp {} ${install_dir}/ \;


TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOGFILE="$PKG_DIR/pytest_run_$TIMESTAMP.log"

cd ${PKG_DIR}
./bin/tests/system/ifconfig.sh up

PYTEST="${PYTEST:-pytest}"
$PYTEST -n 16 bin/tests/system &> "${LOGFILE}"

./bin/tests/system/ifconfig.sh down

echo "[INFO] Test run complete."
echo "[INFO] Log saved to: $LOGFILE"

# Optionally display stats summary from log

set -euo pipefail

# Find the last pytest summary line in the log
line=$(
  grep -oP '={5,}\s*.*?in\s+\d+(?:\.\d+)?s\s+\(\d+:\d{2}:\d{2}\)\s*={5,}' "$LOGFILE" \
  | tail -n1 || true
)

if [[ -z "${line:-}" ]]; then
  echo "No pytest summary line found in $LOGFILE" >&2
  # Don't exit - continue to coverage collection
  # exit 1
fi

# Helper: extract first regex match from $line (Perl regex)
getnum() { echo "$line" | grep -oP "$1" | head -n1 || true; }

failed=$(getnum '\d+(?=\s+failed)');           : "${failed:=0}"
passed=$(getnum '\d+(?=\s+passed)');           : "${passed:=0}"
skipped=$(getnum '\d+(?=\s+skipped)');         : "${skipped:=0}"
xfailed=$(getnum '\d+(?=\s+xfailed)');         : "${xfailed:=0}"
xpassed=$(getnum '\d+(?=\s+xpassed)');         : "${xpassed:=0}"
errors=$(getnum '\d+(?=\s+errors?)');          : "${errors:=0}"
deselected=$(getnum '\d+(?=\s+deselected)');   : "${deselected:=0}"
warnings=$(getnum '\d+(?=\s+warnings?)');      : "${warnings:=0}"
time_seconds=$(getnum '\d+(?:\.\d+)?(?=s \()');: "${time_seconds:=0}"
time_hms=$(getnum '(?<=\()\d+:\d{2}:\d{2}(?=\))'); : "${time_hms:=0}"

echo "Failed : $failed"
echo "Passed : $passed"
echo "Skipped : $skipped"

# Disable strict error checking before coverage collection
set +euo pipefail

cd ${wd}

source "${TESTSUITE_ROOT}/lib/coverage.sh"
collect_coverage "${PKG_DIR}" "${TIMESTAMP}"
