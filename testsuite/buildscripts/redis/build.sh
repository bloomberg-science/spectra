#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


install_dir=$1
opt=$2
symlevel=$3
coverage=${4:-no}  # 4th parameter: "coverage" to enable, defaults to "no"

wd=`pwd`
TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
cur_dir="${TESTSUITE_ROOT}/redis"


cd ${cur_dir}

export DISABLE_WERRORS=yes

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

make distclean
#make CC=gcc OPTIMIZATION="-${opt}" CFLAGS="${CFLAGS}" -j 4 all
make CC=gcc OPTIMIZATION="-${opt}" CFLAGS="${CFLAGS}" LDFLAGS="${LDFLAGS}" PREFIX="${install_dir}" -j 4 install

cd ${wd}
