#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


prog=$1
coverage=${2:-no}  # 2nd parameter: "coverage" to enable coverage builds, defaults to "no"

TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")" && pwd)}"

# Optimization levels to build, e.g. OPT_LEVELS="O0 O1 O2" (supported: O0 O1 O2 O3 Ofast Os)
read -ra opt_array <<< "${OPT_LEVELS:-O2}"
install_path="${TESTSUITE_ROOT}/gcc"

# If coverage is enabled, use a different install path
if [ "$coverage" = "coverage" ]; then
    install_path="${TESTSUITE_ROOT}/gcc-coverage"
    echo "========================================="
    echo "COVERAGE BUILD ENABLED"
    echo "Install path: ${install_path}"
    echo "========================================="
fi

prog_path="${TESTSUITE_ROOT}/${prog}"

echo "building program: ${prog}"

for opt in "${opt_array[@]}"; do
    echo "optimization: $opt"

    # Build with full debug symbols
    build_root="${install_path}/${opt}/fulldbg"
    mkdir -p $build_root
    build_root="${build_root}/${prog}"
    mkdir -p $build_root

    ${TESTSUITE_ROOT}/buildscripts/${prog}/build.sh ${build_root} ${opt} "dbg" ${coverage}
    if [ $? -ne 0 ]; then
        echo "Build failed"
        echo "optimization level: ${opt} debug level dbg"
        exit 1
    else
        echo "Build completed successfully."
    fi

    # Build with symbols only (skip for coverage builds to avoid .gcno timestamp conflicts)
    if [ "$coverage" != "coverage" ]; then
        build_root="${install_path}/${opt}/symonly"
        mkdir -p $build_root
        build_root="${build_root}/${prog}"
        mkdir -p $build_root

        ${TESTSUITE_ROOT}/buildscripts/${prog}/build.sh ${build_root} ${opt} "sym" ${coverage}
        if [ $? -ne 0 ]; then
            echo "Build failed"
            echo "optimization level: ${opt} debug level sym"
            exit 1
        else
            echo "Build completed successfully."
        fi
    else
        echo "Skipping symonly build for coverage (would overwrite .gcno files)"
    fi

done

echo ""
echo "========================================="
echo "All builds completed successfully!"
if [ "$coverage" = "coverage" ]; then
    echo ""
    echo "Coverage-instrumented binaries are in:"
    echo "  ${install_path}"
    echo ""
    echo "After running tests, collect coverage with:"
    echo "  cd ${TESTSUITE_ROOT}/${prog}"
    echo "  lcov --capture --directory . --output-file coverage.info"
    echo "  genhtml coverage.info --output-directory coverage-report"
fi
echo "========================================="
