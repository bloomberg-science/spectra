#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


## Requirements
#    sudo apt-get update
#    sudo apt-get install -y libnet-inet6glue-perl
#    # optional, if later errors mention IO::Socket::IP/INET6 or Socket6:
#    sudo apt-get install -y libio-socket-ip-perl libio-socket-inet6-perl libsocket6-perl
#    sudo apt-get install -y libnet-address-ip-local-perl
##

# Args: path to your custom proftpd binary
: "${1:?Usage: $0 /path/to/proftpd}"
binary_path="$(readlink -f "${1}/proftpd")"
echo "Proftpd binary path: ${binary_path}"
# Where your proftpd checkout lives
TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PKG_PATH="${TESTSUITE_ROOT}/proftpd"
tests_dir="$PKG_PATH/tests"

# Clean old .gcda files to avoid stamp mismatch with .gcno files
if find "${PKG_PATH}" -name "*.gcno" -type f 2>/dev/null | grep -q .; then
    echo "Coverage build detected - cleaning old .gcda files..."
    find "${PKG_PATH}" -name "*.gcda" -type f -delete 2>/dev/null || true
fi

# Sanity checks
[[ -x "$binary_path" ]] || { echo "Not executable: $binary_path" >&2; exit 1; }
[[ -d "$tests_dir"   ]] || { echo "Missing tests dir: $tests_dir" >&2; exit 1; }

# Put your binary in place WITHOUT copying everything
ln -sf "$binary_path" "$PKG_PATH/proftpd"

timestamp="$(date +'%Y%m%d_%H%M%S')"
logfile="$PKG_PATH/test_run_${timestamp}.log"

pushd "$tests_dir" >/dev/null

# Run prove, capture both stdout+stderr to the log; do not spam stdout
prove -lr -j 16 t/ >"$logfile" 2>&1
prove_status=$?

# Parse the summary (total/failed/passed) from the log (mawk-compatible)
sed -r 's/\[[0-9;]*[A-Za-z]//g' "$logfile" | awk '
BEGIN{ total=0; failed=0; fallback=0 }
/^Files=/ {
  n=split($0, parts, ",")
  for(i=1;i<=n;i++){
    if(parts[i] ~ /Tests=/){ sub(/.*Tests=/, "", parts[i]); sub(/[^0-9].*/, "", parts[i]); total=parts[i]+0 }
  }
  next
}
(/\(Wstat:/ && $1 ~ /\.t$/) {
  if(match($0, /Tests:[[:space:]]*[0-9]+/)){
    s=substr($0, RSTART, RLENGTH); sub(/Tests:[[:space:]]*/, "", s); fallback+=s+0
  }
  next
}
/[[:space:]]+Failed tests?:/ {
  line=$0; sub(/^[[:space:]]+Failed tests?:[[:space:]]*/,"",line); gsub(/,/, " ", line)
  n=split(line,t," ")
  for(i=1;i<=n;i++){
    tok=t[i]
    if(tok ~ /^[0-9]+$/) failed++
    else if(tok ~ /^[0-9]+-[0-9]+$/){ split(tok,ab,"-"); a=ab[1]+0; b=ab[2]+0; if(b<a){c=a;a=b;b=c} failed += (b-a+1) }
  }
}
END{
  if (total==0) total=fallback
  passed = (total>=failed)?(total-failed):0
  printf("Passed : %d\nFailed : %d\nTotal : %d\n", passed, failed, total)
}'
popd >/dev/null

# Do NOT 'set -e' — we want to finish with exit 0 no matter what.
set -u  # treat unset vars as an error (doesn't affect exit status below)

PATTERN='proftpd'
# Exclude any command lines that contain these substrings (extend as needed)
EXCLUDE_REGEX='(test.sh|install|eval|apply_filter|grep)'

# Collect candidate PIDs: match lines containing PATTERN but not excluded terms.
# Uses portable ps output (PID + full args), then AWK filters.
pids="$(
  ps -eo pid=,args= 2>/dev/null | \
  awk -v pat="$PATTERN" -v ex="$EXCLUDE_REGEX" '
    $0 ~ pat && $0 !~ ex { print $1 }
  ' | tr -s "[:space:]" "
" | grep -E '^[0-9]+$' || true
)"

# If PIDs matched, try to kill them; ignore any errors (e.g., permissions, already exited).
# Avoid GNU-only xargs -r by guarding the call when $pids is non-empty.
if [ -n "${pids}" ]; then
  printf '%s
' $pids | xargs -n 50 kill -9 >/dev/null 2>&1 || true
fi

source "${TESTSUITE_ROOT}/lib/coverage.sh"
collect_coverage "${PKG_PATH}" "${timestamp}"

# Always succeed (exit after coverage collection)
exit 0
