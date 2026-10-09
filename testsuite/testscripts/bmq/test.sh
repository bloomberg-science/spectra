#!/usr/bin/env bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


bin_path=$1

TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PKG_DIR="${TESTSUITE_ROOT}/bmq"

cp ${bin_path}/bmqbrkr.tsk ${PKG_DIR}/build/blazingmq/src/applications/bmqbrkr/
cp ${bin_path}/bmqtool.tsk ${PKG_DIR}/build/blazingmq/src/applications/bmqtool/
cp ${bin_path}/bmqstoragetool.tsk ${PKG_DIR}/build/blazingmq/src/applications/bmqstoragetool/

wd=`pwd`
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOGFILE="$PKG_DIR/test_run_$TIMESTAMP.log"

cd ${PKG_DIR}/build/blazingmq

ctest --force-new-ctest-process -j 8 &> $LOGFILE

# strip ANSI; then parse with awk (mawk-compatible, no 3-arg match)
sed -r 's/\x1B\[[0-9;]*[A-Za-z]//g' "${LOGFILE}" | awk '
BEGIN{
  total=passed=failed=0
  pcount=fcount=0
  total_guess=0
  in_fail_list=0
}

# Primary: CTest summary line (most reliable)
# e.g. "98% tests passed, 26 tests failed out of 1343"
/tests passed,.*tests failed out of/ {
  n=split($0, a, " ")
  for(i=1;i<=n;i++){
    if(a[i]=="failed") failed=a[i-1]+0
    if(a[i]=="of") total=a[i+1]+0
  }
  passed = total - failed
  next
}

# Count per-test "Passed" lines
/Test #[0-9]+:.*Passed/ { pcount++; next }

# Track denominator "1342/1343" to guess total if needed
/^[[:space:]]*[0-9]+\/[0-9]+[[:space:]]+Test #/ {
  split($1, parts, "/")
  v = parts[2]+0
  if (v > total_guess) total_guess = v
}

# Enter/exit the "The following tests FAILED:" block
/^The following tests FAILED:/ { in_fail_list=1; next }
in_fail_list && /^[[:space:]]*$/ { in_fail_list=0; next }

# Lines inside the failure list, e.g. "  39 - name (Failed)"
in_fail_list && /\(Failed\)/ { fcount++; next }

END{
  if (total==0) {
    failed = fcount
    if (pcount+fcount > 0) total = pcount + fcount
    else if (total_guess > 0) total = total_guess
    passed = (total>=failed) ? (total - failed) : 0
  }
  printf "Total : %d\nFailed : %d\nPassed : %d\n", total, failed, passed
}'


cd ${wd}
