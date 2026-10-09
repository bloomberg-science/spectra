#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PKG_DIR="${TESTSUITE_ROOT}/lighttpd"
TEST_DIR="${PKG_DIR}"
bin_path=$1

wd=`pwd`

LOG_DIR="${TEST_DIR}/test_logs"
mkdir -p $LOG_DIR 

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOGFILE="$LOG_DIR/test_run_$TIMESTAMP.log"

cd ${PKG_DIR}

# Clean old .gcda files to avoid stamp mismatch with .gcno files
if find "${PKG_DIR}" -name "*.gcno" -type f 2>/dev/null | grep -q .; then
    echo "Coverage build detected - cleaning old .gcda files..."
    find "${PKG_DIR}" -name "*.gcda" -type f -delete 2>/dev/null || true
fi

cp ${bin_path}/* ./src/
cp ${bin_path}/*.so ./src/.libs/
cp ${bin_path}/../*.so ./src/.libs/

make check &> $LOGFILE

cd $wd

awk -v IGNORECASE=1 '
BEGIN {
  pass=fail=skip=0;      # Automake-style PASS:/FAIL:/SKIP:/XPASS:/XFAIL:/ERROR:
  tpass=tfail=tskip=0;   # TAP-style per-file lines ending with "ok"/"not ok" or with "# SKIP"
}

{
  line = $0

  # --- Count automake-style tokens (avoid double-counting XPASS as PASS) ---
  tmp=line; n=gsub(/(^|[^A-Za-z])PASS:/,  "", tmp);      pass += n
  tmp=line; n=gsub(/(^|[^A-Za-z])FAIL:/,  "", tmp);      fail += n
  tmp=line; n=gsub(/(^|[^A-Za-z])ERROR:/, "", tmp);      fail += n
  tmp=line; n=gsub(/(^|[^A-Za-z])XPASS:/, "", tmp);      fail += n   # unexpected pass -> fail bucket
  tmp=line; n=gsub(/(^|[^A-Za-z])SKIP:/,  "", tmp);      skip += n
  tmp=line; n=gsub(/(^|[^A-Za-z])XFAIL:/, "", tmp);      skip += n

  # --- TAP-style (Perl .t) lines like: "./foo.t .... ok" or "not ok" ---
  # Count only if the line references a .t file to avoid stray "ok" elsewhere.
  if (line ~ /\.t/) {
    if (line ~ /(^|[[:space:]])not[[:space:]]+ok([[:space:]]|$)/) { tfail++; next }
    if (line ~ /[[:space:]]ok[[:space:]]*$/)                      { tpass++; next }
    if (line ~ /#\s*SKIP[[:space:]]/ )                            { tskip++;       }
  }
}

END {
  # Prefer explicit PASS:/FAIL:/SKIP: tokens if present; otherwise fall back to TAP counts.
  p=pass; f=fail; s=skip;
  if ((p+f+s)==0 && (tpass+tfail+tskip)>0) { p=tpass; f=tfail; s=tskip; }

  total = p + f + s;
  printf("Passed : %d\nFailed : %d\nSkipped : %d\nTotal : %d\n", p, f, s, total);
}
' "${LOGFILE}"

source "${TESTSUITE_ROOT}/lib/coverage.sh"
collect_coverage "${PKG_DIR}" "${TIMESTAMP}"
