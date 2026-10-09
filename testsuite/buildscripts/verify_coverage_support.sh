#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


# Script to verify that all build scripts support coverage instrumentation

echo "========================================="
echo "Verifying Coverage Support in Build Scripts"
echo "========================================="
echo ""

packages=("nginx" "apache" "memcached" "proftpd" "redis" "postgresql" "lighttpd" "bind" "mysql" "comdb2" "bmq" "bde")

all_good=true

for pkg in "${packages[@]}"; do
    script="$pkg/build.sh"

    if [ ! -f "$script" ]; then
        echo "❌ MISSING: $script"
        all_good=false
        continue
    fi

    # Check if the script has coverage parameter
    if grep -q 'coverage=${4:-no}' "$script"; then
        echo "✅ $pkg: Coverage support verified"
    else
        echo "❌ $pkg: Coverage support NOT found"
        all_good=false
    fi

    # Check if --coverage flag is added
    if grep -q '"\${CFLAGS} --coverage"' "$script" || grep -q '${CFLAGS} --coverage' "$script"; then
        # Additional check passed
        :
    else
        echo "   ⚠️  WARNING: $pkg may not properly add --coverage flag"
    fi
done

echo ""
echo "========================================="
if [ "$all_good" = true ]; then
    echo "✅ All packages support coverage instrumentation!"
else
    echo "❌ Some packages are missing coverage support"
    exit 1
fi
echo "========================================="
