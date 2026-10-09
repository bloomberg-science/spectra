#!/usr/bin/env bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


## Requirements
#    sudo apt-get update
#    sudo apt-get install -y libnet-inet6glue-perl
#    # optional, if later errors mention IO::Socket::IP/INET6 or Socket6:
#    sudo apt-get install -y libio-socket-ip-perl libio-socket-inet6-perl libsocket6-perl
#    sudo apt-get install -y libnet-address-ip-local-perl
##

# Args: path to your custom binary
: "${1:?Usage: $0 /path/to/memcached}"
binary_path="$(readlink -f "$1/memcached")"

# Where your proftpd checkout lives
TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PKG_PATH="${TESTSUITE_ROOT}/memcached"
tests_dir="$PKG_PATH"

# Clean old .gcda files to avoid stamp mismatch with .gcno files
if find "${PKG_PATH}" -name "*.gcno" -type f 2>/dev/null | grep -q .; then
    echo "Coverage build detected - cleaning old .gcda files..."
    find "${PKG_PATH}" -name "*.gcda" -type f -delete 2>/dev/null || true
fi

# Sanity checks
[[ -x "$binary_path" ]] || { echo "Not executable: $binary_path" >&2; exit 1; }
[[ -d "$tests_dir"   ]] || { echo "Missing tests dir: $tests_dir" >&2; exit 1; }

# Put your binary in place WITHOUT copying everything
ln -sf "$binary_path" "$PKG_PATH/memcached-debug"

timestamp="$(date +'%Y%m%d_%H%M%S')"
logfile="$PKG_PATH/test_run_${timestamp}.log"

pushd "$tests_dir" >/dev/null

# Run prove, capture both stdout+stderr to the log; do not spam stdout
prove -lr t/ -j 4 >"$logfile" 2>&1
prove_status=$?

# Parse the summary (total/failed/passed) from the log and print to stdout

# Strip ANSI then parse
sed -r 's/\[[0-9;]*[A-Za-z]//g' "$logfile" | awk '
BEGIN { total=0; passed=0; failed=0; skipped=0; }

/^t\/.*\.t[[:space:]].*/ {
  # One test-file line (e.g., "t/foo.t .... ok" or "t/foo.t .... skipped: ...")
  total++
  if ($0 ~ /[[:space:]]skipped:/i)                         { skipped++ }
  else if ($0 ~ /(^|[[:space:]])ok([[:space:]]|$)/)        { passed++  }
  else if ($0 ~ /not[[:space:]]+ok/i)                  { failed++  }
  else if ($0 ~ /(Dubious|Failed|wstat|exit status|Parse errors)/i) { failed++ }
  next
}

# If present, this gives us the authoritative total count of files
/^Files=/ {
  if (match($0, /Files=([0-9]+)/, m)) total = m[1]+0
  next
}

END {
  # If totals don’t add up (e.g., we only saw skipped/passed), infer passed
  if (total > 0 && (passed + failed + skipped) != total)
    passed = total - failed - skipped

  printf("Passed : %d\nFailed : %d\nSkipped : %d\nTotal : %d\n", passed, failed, skipped, total)
}'


popd >/dev/null

source "${TESTSUITE_ROOT}/lib/coverage.sh"
collect_coverage "${PKG_PATH}" "${timestamp}"
