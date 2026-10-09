#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


# Script to build all packages with optional coverage instrumentation
# Usage: ./build_all.sh [coverage] [package1 package2 ...]
# If no packages specified, builds all available packages

coverage=${1:-no}  # First parameter: "coverage" to enable, defaults to "no"
shift  # Remove first argument so $@ contains only package names

TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
export TESTSUITE_ROOT

# If packages specified on command line, use those; otherwise use all
if [ $# -gt 0 ]; then
    packages=("$@")
else
    # Auto-detect all available packages from buildscripts directory
    packages=()
    for dir in ${TESTSUITE_ROOT}/buildscripts/*/; do
        pkg=$(basename "$dir")
        if [ -f "${TESTSUITE_ROOT}/buildscripts/${pkg}/build.sh" ]; then
            packages+=("$pkg")
        fi
    done
fi

echo "========================================="
echo "BUILD ALL PACKAGES"
echo "========================================="
echo "Coverage: ${coverage}"
echo "Packages to build: ${packages[@]}"
echo "Total: ${#packages[@]} packages"
echo "========================================="
echo ""

# Arrays to track results
declare -a successful_packages
declare -a failed_packages
declare -a skipped_packages

start_time=$(date +%s)

# Build each package
for pkg in "${packages[@]}"; do
    echo ""
    echo "========================================="
    echo "Building: ${pkg}"
    echo "========================================="

    # Check if package exists
    if [ ! -d "${pkg}" ]; then
        echo "⚠️  WARNING: Package directory '${pkg}' not found - SKIPPING"
        skipped_packages+=("${pkg}")
        continue
    fi

    if [ ! -f "buildscripts/${pkg}/build.sh" ]; then
        echo "⚠️  WARNING: Build script 'buildscripts/${pkg}/build.sh' not found - SKIPPING"
        skipped_packages+=("${pkg}")
        continue
    fi

    # Run the build
    ./build.sh "${pkg}" "${coverage}"

    if [ $? -eq 0 ]; then
        echo "✅ SUCCESS: ${pkg} built successfully"
        successful_packages+=("${pkg}")
    else
        echo "❌ FAILED: ${pkg} build failed"
        failed_packages+=("${pkg}")
    fi
done

end_time=$(date +%s)
duration=$((end_time - start_time))

# Print summary
echo ""
echo ""
echo "========================================="
echo "BUILD SUMMARY"
echo "========================================="
echo "Total time: ${duration} seconds"
echo ""

echo "✅ Successful (${#successful_packages[@]}):"
if [ ${#successful_packages[@]} -eq 0 ]; then
    echo "  (none)"
else
    for pkg in "${successful_packages[@]}"; do
        echo "  - ${pkg}"
    done
fi
echo ""

echo "❌ Failed (${#failed_packages[@]}):"
if [ ${#failed_packages[@]} -eq 0 ]; then
    echo "  (none)"
else
    for pkg in "${failed_packages[@]}"; do
        echo "  - ${pkg}"
    done
fi
echo ""

if [ ${#skipped_packages[@]} -gt 0 ]; then
    echo "⚠️  Skipped (${#skipped_packages[@]}):"
    for pkg in "${skipped_packages[@]}"; do
        echo "  - ${pkg}"
    done
    echo ""
fi

echo "========================================="

# Exit with error code if any package failed
if [ ${#failed_packages[@]} -gt 0 ]; then
    echo ""
    echo "❌ Build completed with ${#failed_packages[@]} failure(s)"
    exit 1
else
    echo ""
    echo "✅ All packages built successfully!"
    exit 0
fi
