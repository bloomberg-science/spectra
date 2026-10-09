#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


install_dir=$1
opt=$2
symlevel=$3
coverage=${4:-no}  # 4th parameter: "coverage" to enable, defaults to "no"

wd=`pwd`
TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
cur_dir="${TESTSUITE_ROOT}/mysql"


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

rm -rf test_build
mkdir test_build
cd test_build
#cmake -DCMAKE_INSTALL_PREFIX=${install_dir} -DCMAKE_C_FLAGS="${CFLAGS}" -DCMAKE_CXX_FLAGS="${CXXFLAGS}" -DCMAKE_BUILD_TYPE=None -DWITH_SSL=system ..
cmake -DCMAKE_INSTALL_PREFIX=${install_dir} -DCMAKE_C_FLAGS="${CFLAGS}" -DCMAKE_CXX_FLAGS="${CXXFLAGS}" -DCMAKE_EXE_LINKER_FLAGS="${LDFLAGS}" -DCMAKE_SHARED_LINKER_FLAGS="${LDFLAGS}" -DWITH_SSL=system ..

make -j20

if [ $? -ne 0 ]; then
    echo "Make failed with an error."
    echo "optimization level: ${opt}"
    exit 1
else
    echo "Make completed successfully."
fi

make install

# For coverage builds, also create test_install in source directory for tests
# The test script needs this directory to run tests
if [ "$coverage" = "coverage" ]; then
    echo "Creating test_install for coverage tests..."
    rm -rf "${cur_dir}/test_install"
    cp -r "${install_dir}" "${cur_dir}/test_install"
    echo "test_install created at ${cur_dir}/test_install"
fi

cd ${wd}
