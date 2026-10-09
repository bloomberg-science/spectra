#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


install_dir=$1
opt=$2
symlevel=$3
coverage=${4:-no}  # 4th parameter: "coverage" to enable, defaults to "no"

wd=`pwd`
TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
cur_dir="${TESTSUITE_ROOT}/bind"


cd ${cur_dir}

CFLAGS="-${opt}"
CXXFLAGS="-${opt}"

if [ "$symlevel" = "dbg" ]; then
    echo "Full debug"
    CFLAGS="-g -${opt}"
    CXXFLAGS="-g -${opt}"
else
    echo "Symbol only"
fi

# Add coverage instrumentation if requested
if [ "$coverage" = "coverage" ]; then
    echo "Enabling coverage instrumentation"
    CFLAGS="${CFLAGS} --coverage"
    CXXFLAGS="${CXXFLAGS} --coverage"
    LDFLAGS="${LDFLAGS} --coverage"
fi

# Always rebuild from scratch
rm -rf build-dir

export CC=gcc
export CXX=g++

if [ "$coverage" = "coverage" ]; then
    # Meson needs explicit -Dc_args and -Dc_link_args for coverage
    meson setup --prefix=${install_dir} -Dc_args='--coverage' -Dc_link_args='--coverage' build-dir
else
    meson setup --prefix=${install_dir} build-dir
fi

meson compile -C build-dir
meson install -C build-dir


if [ $? -ne 0 ]; then
    echo "Make failed with an error."
    echo "optimization level: ${opt}"
    exit 1
else
    echo "Make completed successfully."
fi

cd ${wd}
