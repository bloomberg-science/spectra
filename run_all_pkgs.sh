#!/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

# Run gen_pkg_syscalls.py for all target packages and record memory usage + results.
# Usage: ./run_all_pkgs.sh <tool> [opt] [config] [packages...]
# Example: ./run_all_pkgs.sh angr                          # O2, stripped, all packages
#          ./run_all_pkgs.sh safer O0 fulldbg               # O0, fulldbg, all packages
#          ./run_all_pkgs.sh safer O2 stripped nginx redis   # O2, stripped, specific packages

TOOL=${1:-angr}
shift

# Parse optional optimization level (O0/O1/O2/O3/Ofast/Os)
if [[ "$1" =~ ^O[0-3s]$|^Ofast$ ]]; then
    OPT="$1"
    shift
else
    OPT="O2"
fi

# Parse optional config (stripped/fulldbg/symonly)
if [[ "$1" =~ ^(stripped|fulldbg|symonly)$ ]]; then
    CONFIG="$1"
    shift
else
    CONFIG="stripped"
fi

if [ $# -gt 0 ]; then
    PACKAGES=("$@")
else
    PACKAGES=(nginx apache redis lighttpd memcached proftpd bind comdb2)
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTDIR="${SCRIPT_DIR}/eval_results/${TOOL}_${OPT}_${CONFIG}_${TIMESTAMP}"
mkdir -p "$OUTDIR"

SUMMARY_FILE="${OUTDIR}/summary.csv"
echo "package,tool,peak_memory_kb,time_seconds,num_binaries,total_syscalls,avg_aict,status" > "$SUMMARY_FILE"

echo "========================================="
echo "Running gen_pkg_syscalls.py"
echo "========================================="
echo "Tool: ${TOOL}"
echo "Optimization: ${OPT}"
echo "Config: ${CONFIG}"
echo "Packages: ${PACKAGES[*]}"
echo "Output: ${OUTDIR}"
echo "========================================="
echo ""

for pkg in "${PACKAGES[@]}"; do
    echo "--- ${pkg} ---"
    LOG_FILE="${OUTDIR}/${pkg}.log"
    RESULT_FILE="${SCRIPT_DIR}/testsuite/testdata/${TOOL}/${pkg}_${CONFIG}_${OPT}.json"

    START_TIME=$(date +%s)

    /usr/bin/time -v python3 "${SCRIPT_DIR}/gen_pkg_syscalls.py" "${TOOL}" "${OPT}" "${CONFIG}" "${pkg}" -v \
        > "${LOG_FILE}" 2>&1
    EXIT_CODE=$?

    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))

    PEAK_MEM=$(grep "Maximum resident set size" "${LOG_FILE}" | awk '{print $NF}')
    PEAK_MEM=${PEAK_MEM:-0}

    NUM_BINARIES=0
    TOTAL_SYSCALLS=0
    AVG_AICT=0
    SYSCALL_DETAIL=""

    if [ $EXIT_CODE -eq 0 ] && [ -f "$RESULT_FILE" ]; then
        STATUS="OK"
        NUM_BINARIES=$(python3 -c "
import json
with open('${RESULT_FILE}') as f:
    data = json.load(f)
print(len(data))
" 2>/dev/null)
        TOTAL_SYSCALLS=$(python3 -c "
import json
with open('${RESULT_FILE}') as f:
    data = json.load(f)
total = 0
for entry in data:
    total += len(entry.get('syscall_list', []))
print(total)
" 2>/dev/null)
        AVG_AICT=$(python3 -c "
import json
with open('${RESULT_FILE}') as f:
    data = json.load(f)
aicts = [entry['aict'] for entry in data if 'aict' in entry]
print(f'{sum(aicts)/len(aicts):.2f}' if aicts else '0')
" 2>/dev/null)
        SYSCALL_DETAIL=$(python3 -c "
import json
with open('${RESULT_FILE}') as f:
    data = json.load(f)
for entry in data:
    name = entry['binary']
    syscalls = sorted(entry.get('syscall_list', []))
    aict = entry.get('aict', 0)
    print(f'  {name}: {len(syscalls)} syscalls, AICT={aict:.2f}')
" 2>/dev/null)
    else
        STATUS="FAILED"
    fi

    echo "${pkg},${TOOL},${PEAK_MEM},${ELAPSED},${NUM_BINARIES},${TOTAL_SYSCALLS},${AVG_AICT},${STATUS}" >> "$SUMMARY_FILE"

    echo "  Status: ${STATUS}"
    echo "  Time: ${ELAPSED}s"
    echo "  Peak memory: ${PEAK_MEM} KB"
    echo "  Binaries: ${NUM_BINARIES}"
    echo "  Total syscalls: ${TOTAL_SYSCALLS}"
    echo "  Avg AICT: ${AVG_AICT}"
    if [ -n "$SYSCALL_DETAIL" ]; then
        echo "$SYSCALL_DETAIL"
    fi
    echo ""
done

echo "========================================="
echo "SUMMARY"
echo "========================================="
column -t -s',' "$SUMMARY_FILE"
echo ""
echo "Full logs: ${OUTDIR}/"
echo "CSV: ${SUMMARY_FILE}"
echo "========================================="
