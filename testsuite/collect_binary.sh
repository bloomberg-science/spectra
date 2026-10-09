#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

# Extract ELF binaries from build output into subset_binaries/ for analysis.
# Usage: ./collect_binary.sh [opt_levels...]
# Default: collects O2 only. Pass "all" for O0 O1 O2 O3 Ofast Os.

TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
cd "$TESTSUITE_ROOT"

if [ "$1" = "all" ]; then
    opt_array=("O0" "O1" "O2" "O3" "Ofast" "Os")
elif [ $# -gt 0 ]; then
    opt_array=("$@")
else
    opt_array=("O2")
fi

packages=("apache" "bind" "bmq" "comdb2" "lighttpd" "memcached" "mysql" "nginx" "postgresql" "proftpd" "redis")

mkdir -p subset_binaries/gcc

for opt in "${opt_array[@]}"; do
    mkdir -p subset_binaries/gcc/${opt}/{fulldbg,symonly,stripped}

    for pkg in "${packages[@]}"; do
        # fulldbg: copy ELF files directly
        search_dir="./gcc/${opt}/fulldbg/${pkg}"
        if [ -d "${search_dir}" ]; then
            output_dir="subset_binaries/gcc/${opt}/fulldbg/${pkg}"
            mkdir -p "${output_dir}"
            find "${search_dir}" -type f -exec file {} + | grep ELF | cut -d: -f1 | while read fpath; do
                cp "${fpath}" "${output_dir}/"
            done
        fi

        # symonly: copy ELF files, also create stripped copies
        search_dir="./gcc/${opt}/symonly/${pkg}"
        if [ -d "${search_dir}" ]; then
            output_dir="subset_binaries/gcc/${opt}/symonly/${pkg}"
            output_dir2="subset_binaries/gcc/${opt}/stripped/${pkg}"
            mkdir -p "${output_dir}" "${output_dir2}"
            find "${search_dir}" -type f -exec file {} + | grep ELF | cut -d: -f1 | while read fpath; do
                filename=$(basename "${fpath}")
                cp "${fpath}" "${output_dir}/"
                cp "${fpath}" "${output_dir2}/"
                strip "${output_dir2}/${filename}"
            done
        fi
    done
done

echo "Binaries collected in: ${TESTSUITE_ROOT}/subset_binaries/"
