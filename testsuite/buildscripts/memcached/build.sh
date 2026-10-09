#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


install_dir=$1
opt=$2
symlevel=$3
coverage=${4:-no}  # 4th parameter: "coverage" to enable, defaults to "no"

wd=`pwd`
TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
cur_dir="${TESTSUITE_ROOT}/memcached"


cd ${cur_dir}

./autogen.sh

export CC=gcc

if [ "$symlevel" = "dbg" ]; then
    echo "Full debug" 
    export CFLAGS="-g -${opt} -DMEMCACHED_DEBUG"
    export CXXFLAGS="-g -${opt} -DMEMCACHED_DEBUG"
else
    echo "Symbol only"
    export CFLAGS="-${opt} -DMEMCACHED_DEBUG"
    export CXXFLAGS="-${opt} -DMEMCACHED_DEBUG"

fi

# Add coverage instrumentation if requested
if [ "$coverage" = "coverage" ]; then
    echo "Enabling coverage instrumentation"
    export CFLAGS="${CFLAGS} --coverage"
    export CXXFLAGS="${CXXFLAGS} --coverage"
    export LDFLAGS="${LDFLAGS} --coverage"
fi

make clean
./configure --prefix=${install_dir}
make
make install
cd ${wd}
