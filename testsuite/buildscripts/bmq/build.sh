#!/usr/bin/env bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


# This script builds BlazingMQ and all of its dependencies.

set -e
set -u
[ -z "$BASH" ] || shopt -s expand_aliases

install_dir=$1
opt=$2
symlevel=$3
coverage=${4:-no}  # 4th parameter: "coverage" to enable, defaults to "no"

wd=`pwd`
TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
cur_dir="${TESTSUITE_ROOT}/bmq"

cd ${cur_dir}

CFLAGS="-${opt}"
CXXFLAGS="-${opt}"
LDFLAGS="${LDFLAGS:-}"

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

export CFLAGS="${CFLAGS}"
export CXXFLAGS="${CXXFLAGS}"
export LDFLAGS="${LDFLAGS}"



# :: Set some initial constants :::::::::::::::::::::::::::::::::::::::::::::::
DIR_ROOT="$(pwd)"

DIR_THIRDPARTY="${DIR_ROOT}/thirdparty"
mkdir -p "${DIR_THIRDPARTY}"

DIR_BUILD="${DIR_BUILD:-${DIR_ROOT}/build}"
rm -rf ${DIR_BUILD}
mkdir -p "${DIR_BUILD}"

DIR_INSTALL="${install_dir}"
mkdir -p "${DIR_INSTALL}"

BUILD_PROMETHEUS=false

# :: Clone dependencies :::::::::::::::::::::::::::::::::::::::::::::::::::::::

if [ ! -d "${DIR_THIRDPARTY}/bde-tools" ]; then
    git clone --depth 1 --branch 4.23.0.0 https://github.com/bloomberg/bde-tools "${DIR_THIRDPARTY}/bde-tools"
fi
if [ ! -d "${DIR_THIRDPARTY}/bde" ]; then
    git clone --depth 1 --branch 4.23.0.0 https://github.com/bloomberg/bde.git "${DIR_THIRDPARTY}/bde"
fi
if [ ! -d "${DIR_THIRDPARTY}/ntf-core" ]; then
    git clone --depth 1 --branch 2.4.2 https://github.com/bloomberg/ntf-core.git "${DIR_THIRDPARTY}/ntf-core"
fi

# :: Install required packages ::::::::::::::::::::::::::::::::::::::::::::::::

# Build and install BDE
# Refer to https://bloomberg.github.io/bde/library_information/build.html
PATH="${DIR_THIRDPARTY}/bde-tools/bin:$PATH"

if [ ! -e "${DIR_BUILD}/bde/.complete" ]; then
    pushd "${DIR_THIRDPARTY}/bde"
    eval "$(bbs_build_env -u opt_64_cpp17 -b "${DIR_BUILD}/bde" -i "${DIR_INSTALL}")"
    bbs_build configure --prefix="${DIR_INSTALL}"
    bbs_build build --prefix="${DIR_INSTALL}"
    bbs_build install --install_dir="/" --prefix="${DIR_INSTALL}"
    eval "$(bbs_build_env unset)"
    popd
    touch "${DIR_BUILD}/bde/.complete"
fi

if [ ! -e "${DIR_BUILD}/ntf/.complete" ]; then
    # Build and install NTF
    pushd "${DIR_THIRDPARTY}/ntf-core"
    ./configure --prefix "${DIR_INSTALL}" \
                --output "${DIR_BUILD}/ntf" \
                --without-warnings-as-errors \
                --without-usage-examples \
                --without-applications \
                --ufid opt_64_cpp17
    make -j 16
    make install
    popd
    touch "${DIR_BUILD}/ntf/.complete"
fi

# :: Build the BlazingMQ repo :::::::::::::::::::::::::::::::::::::::::::::::::
CMAKE_OPTIONS=(\
    -DBDE_BUILD_TARGET_64=1 \
    -DCMAKE_BUILD_TYPE=None \
    -DCMAKE_INSTALL_LIBDIR="lib" \
    -DCMAKE_INSTALL_PREFIX="${DIR_INSTALL}" \
    -DCMAKE_MODULE_PATH="${DIR_THIRDPARTY}/bde-tools/cmake;${DIR_THIRDPARTY}/bde-tools/BdeBuildSystem" \
    -DCMAKE_PREFIX_PATH="${DIR_INSTALL}" \
    -DCMAKE_TOOLCHAIN_FILE="${DIR_THIRDPARTY}/bde-tools/BdeBuildSystem/toolchains/linux/gcc-default.cmake" \
    -DCMAKE_CXX_STANDARD=17 \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DCMAKE_C_FLAGS="${CFLAGS}" \
    -DCMAKE_CXX_FLAGS="${CXXFLAGS}" \
    -DFLEX_ROOT=/usr/lib/x86_64-linux-gnu)

# Add linker flags if coverage is enabled
if [ "$coverage" = "coverage" ]; then
    CMAKE_OPTIONS+=(-DCMAKE_EXE_LINKER_FLAGS="${LDFLAGS}")
    CMAKE_OPTIONS+=(-DCMAKE_SHARED_LINKER_FLAGS="${LDFLAGS}")
fi

if [ "${BUILD_PROMETHEUS}" == true ]; then
    CMAKE_OPTIONS+=(-DINSTALL_TARGETS=prometheus);
else
    CMAKE_OPTIONS+=(-UINSTALL_TARGETS);
fi

PKG_CONFIG_PATH="${DIR_INSTALL}/lib64/pkgconfig:${DIR_INSTALL}/lib/pkgconfig:$(pkg-config --variable pc_path pkg-config)" \
cmake -B "${DIR_BUILD}/blazingmq" -S "${DIR_ROOT}" "${CMAKE_OPTIONS[@]}"
make -C "${DIR_BUILD}/blazingmq" -j 16
make -C "${DIR_BUILD}/blazingmq" install
cd ${wd}

echo broker is here: "${DIR_BUILD}/blazingmq/src/applications/bmqbrkr/bmqbrkr.tsk"
echo to run the broker: "${DIR_BUILD}/blazingmq/src/applications/bmqbrkr/run"
echo tool is here: "${DIR_BUILD}/blazingmq/src/applications/bmqtool/bmqtool.tsk"
