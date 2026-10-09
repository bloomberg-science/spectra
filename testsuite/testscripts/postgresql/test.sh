#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PKG_DIR="${TESTSUITE_ROOT}/postgresql"
install_dir=${PKG_DIR}/test_install
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

if [[ ! -d "test_install" ]]; then
  echo "Test installation not found...creating" >&2
  if [ $IS_COVERAGE_BUILD -eq 0 ]; then
      echo "Standard build detected - rebuilding for tests"
      rm -rf build-dir
      meson setup --prefix=${install_dir} build-dir
      meson compile -C build-dir
      meson install -C build-dir
  else
      echo "Coverage build detected - skipping rebuild to preserve coverage data"
  fi
fi

ls -1 ${bin_dir}/* | grep -v "\.so" | xargs -I {} cp {} ${install_dir}/bin/

PATH="${install_dir}/bin:${PKG_DIR}/build-dir/src/test/regress:$PATH"
LD_LIBRARY_PATH="${install_dir}/lib"
INITDB_TEMPLATE=/tmp/initdb-template
rm -rf /tmp/initdb-template
${install_dir}/bin/initdb --auth trust --no-sync --no-instructions --lc-messages=C --no-clean /tmp/initdb-template

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOGFILE="$PKG_DIR/test_run_$TIMESTAMP.log"


${PKG_DIR}/build-dir/src/test/regress/pg_regress --temp-instance=./tmp_check \
	--inputdir=${PKG_DIR}/src/test/regress \
	--bindir= \
      	--dlpath=${PKG_DIR}/build-dir/src/test/regress \
	--max-concurrent-tests=20 \
       	--schedule=${PKG_DIR}/src/test/regress/parallel_schedule &> $LOGFILE


awk '
BEGIN { pass=fail=skip=0; IGNORECASE=1 }

# Only consider TAP result lines
/^(ok|not[[:space:]]+ok)[[:space:]]/ {
  line = $0
  # Extract directive after "#" (if any)
  dir = ""
  h = index(line, "#")
  if (h > 0) dir = substr(line, h+1)

  if ($1 == "ok") {
    # ok with "# SKIP ..." => planned skip
    if (dir ~ /^[[:space:]]*SKIP/) { skip++ }
    # ok with "# TODO ..." => unexpected success (count as fail)
    else if (dir ~ /^[[:space:]]*TODO/) { fail++ }
    else { pass++ }
  } else {
    # not ok with "# SKIP|TODO ..." => expected fail (treat as skip)
    if (dir ~ /^[[:space:]]*(SKIP|TODO)/) { skip++ }
    else { fail++ }
  }
  next
}

END {
  total = pass + fail + skip
  printf("Passed : %d\nFailed : %d\nSkipped : %d\nTotal : %d\n", pass, fail, skip, total)
}
' "${LOGFILE}"

source "${TESTSUITE_ROOT}/lib/coverage.sh"
collect_coverage "${PKG_DIR}" "${TIMESTAMP}"

cd $wd
