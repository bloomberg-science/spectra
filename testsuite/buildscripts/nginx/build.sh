#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


install_dir=$1
opt=$2
symlevel=$3
coverage=${4:-no}  # 4th parameter: "coverage" to enable, defaults to "no"

wd=`pwd`
TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
cur_dir="${TESTSUITE_ROOT}/nginx"


cd ${cur_dir}

export CC=gcc

if [ "$symlevel" = "dbg" ]; then
    echo "Full debug" 
    export CFLAGS="-g -${opt}"
    export CXXFLAGS="-g -${opt}"
else
    echo "Symbol only"
    export CFLAGS="-${opt}"
    export CXXFLAGS="-${opt}"

fi

# Add coverage instrumentation if requested
if [ "$coverage" = "coverage" ]; then
    echo "Enabling coverage instrumentation"
    export CFLAGS="${CFLAGS} --coverage"
    export CXXFLAGS="${CXXFLAGS} --coverage"
    export LDFLAGS="${LDFLAGS} --coverage"
fi

make clean

# nginx's custom build system needs explicit flags via --with-cc-opt and --with-ld-opt
# Unlike autotools, it doesn't automatically pick up CFLAGS/LDFLAGS from environment
./auto/configure --prefix=${install_dir} --with-cc-opt="${CFLAGS}" --with-ld-opt="${LDFLAGS}"
if [ $? -ne 0 ]; then
    echo "ERROR: nginx configure failed"
    exit 1
fi

make
if [ $? -ne 0 ]; then
    echo "ERROR: nginx make failed"
    exit 1
fi

make install
if [ $? -ne 0 ]; then
    echo "ERROR: nginx make install failed"
    exit 1
fi

cd ${wd}
