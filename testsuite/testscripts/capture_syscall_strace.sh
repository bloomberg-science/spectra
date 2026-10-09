#!/usr/bin/env bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

# Generic strace-based syscall capture script.
# Used by: nginx, postgresql, proftpd, memcached
#
# Usage:
#   ./capture_syscall_strace.sh <test_command> <bin_dir> [more args...]
#   BIN_DIR=/path/to/bins ./capture_syscall_strace.sh <test_command> [args...]
#
# The script runs the given command under strace, identifies which target
# binaries were executed, propagates PID-to-binary mapping through fork/clone,
# and outputs JSON files with syscall numbers and opened libraries per binary.
#
# Output (in OUTDIR):
#   syscalls_by_binary.json  — [{"binary":"name","syscall_list":[nums...]}]
#   libs.json                — [{"binary":"name","libs_list":["path",...]}]

extract_syscalls() {
  awk '
    { sub(/^[0-9.]+[[:space:]]+/, "", $0) }
    { sub(/^\[pid[[:space:]]+[0-9]+\][[:space:]]+/, "", $0) }
    match($0, /^<\.\.\.[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+resumed>.*/, m) { print m[1]; next }
    match($0, /^([A-Za-z_][A-Za-z0-9_]*)\(/, m) { print m[1]; next }
  ' "$@"
}

extract_libs() {
  cat "$@" | grep "open" | grep "\.so" | grep -v "ENOENT" | grep -v "ld.so.cache" | awk '{print $3}' | sed 's/,//g' | sed 's/"//g' | sort -u
}

set -euo pipefail

TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

BIN_DIR="${BIN_DIR:-}"
if [[ -z "${BIN_DIR}" ]]; then
  for a in "$@"; do
    [[ "$a" == /* && -d "$a" ]] && BIN_DIR="$a"
  done
fi
[[ -n "$BIN_DIR" ]] || { echo "Could not detect bin dir. Set BIN_DIR or pass an absolute dir arg."; exit 2; }
[[ -d "$BIN_DIR" ]] || { echo "Not a directory: $BIN_DIR"; exit 2; }

mapfile -t TARGETS < <(find "${BIN_DIR}/" -maxdepth 1 -type f -print | sort)
[[ ${#TARGETS[@]} -gt 0 ]] || { echo "No executables in $BIN_DIR"; exit 3; }

declare -A TARGET_SET
for i in "${!TARGETS[@]}"; do
  rp="$(readlink -f "${TARGETS[$i]}" || printf '%s' "${TARGETS[$i]}")"
  echo "Target: ${rp}"
  TARGETS[$i]="$rp"
  TARGET_SET["$rp"]=1
done

TS="$(date +%Y%m%d_%H%M%S)"
OUTDIR=${OUTDIR:-/tmp/strace_capture_${TS}}
mkdir -p "$OUTDIR"

strace -ff -f -ttt -s 0 -qq -o "$OUTDIR/strace" -- "$@" || true

declare -A PID2EXE
KEEP_LIST="$OUTDIR/pids.keep"; : > "$KEEP_LIST"

for f in "$OUTDIR"/strace.*; do
  [[ -f "$f" ]] || continue
  while IFS= read -r line; do
    [[ $line =~ execve(at)?\(\"([^\"]+)\" ]] || continue
    path="${BASH_REMATCH[2]}"
    rp="$(readlink -f -- "$path" 2>/dev/null || printf '%s' "$path")"
    base="${path##*/}"
    if [[ -n ${TARGET_SET[$rp]:-} || -n ${TARGET_SET[$base]:-} ]]; then
      pid="${f##*.}"
      PID2EXE["$pid"]="$rp"
      echo "$pid" >> "$KEEP_LIST"
    fi
  done < "$f"
done

declare -A CHILDREN
for pf in "$OUTDIR"/strace.*; do
  [[ -f "$pf" ]] || continue
  parent="${pf##*.}"
  while read -r c; do
    [[ "$c" =~ ^[1-9][0-9]*$ ]] || continue
    CHILDREN["$parent"]="${CHILDREN[$parent]-} $c"
  done < <(awk 'match($0, /(clone3?\(|fork\(|vfork\().*=\s*([0-9]+)/, m){print m[2]}' "$pf")
done

add_exe() {
  local pid="$1" exe="$2"
  local cur="${PID2EXE[$pid]-}"
  case $'\n'"$cur"$'\n' in
    *$'\n'"$exe"$'\n'*) ;;
    *) PID2EXE["$pid"]="${cur:+$cur$'\n'}$exe" ;;
  esac
}

queue=(); for p in "${!PID2EXE[@]}"; do queue+=("$p"); done
while ((${#queue[@]})); do
  p="${queue[0]}"; queue=("${queue[@]:1}")
  children="${CHILDREN[$p]-}"
  for c in $children; do
    add_exe "$c" "${PID2EXE[$p]-}"
    echo "$c" >> "$KEEP_LIST"
    queue+=("$c")
  done
done

NUM_KEEP=$(wc -l < "$KEEP_LIST" | tr -d ' ')
[[ "$NUM_KEEP" -gt 0 ]] || { echo "No target PIDs found. Is BIN_DIR correct?"; exit 4; }

declare -A FILES_BY_EXE
while read -r pid; do
  mapfile -t exes < <(printf '%s\n' "${PID2EXE[$pid]-}")
  for exe in "${exes[@]}"; do
    FILES_BY_EXE["$exe"]+="$OUTDIR/strace.$pid "
  done
done < "$KEEP_LIST"

ARCH=$(uname -m)
declare -A NAME2NUM

if command -v ausyscall >/dev/null 2>&1; then
  while read -r nr name; do
    [[ "$nr" =~ ^[0-9]+$ && "$name" =~ ^[A-Za-z0-9_]+$ ]] || continue
    NAME2NUM["$name"]="$nr"
  done < <(ausyscall -a "$ARCH" --dump 2>/dev/null | awk 'NR>1{print $1, $2}')
  RESOLVER="ausyscall"
elif command -v scmp_sys_resolver >/dev/null 2>&1; then
  RESOLVER="seccomp"
else
  echo "ERROR: need ausyscall or scmp_sys_resolver to map syscalls to numbers." >&2
  exit 1
fi

resolve_num() {
  local name="$1" n=""
  if [[ "$name" == "pread64" ]]; then name="pread"
  elif [[ "$name" == "pwrite64" ]]; then name="pwrite"; fi
  if [[ -n "${NAME2NUM[$name]:-}" ]]; then
    echo "${NAME2NUM[$name]}"; return
  fi
  if [[ "$RESOLVER" == "seccomp" ]]; then
    n=$(scmp_sys_resolver "$name" 2>/dev/null || true)
    [[ "$n" =~ ^[0-9]+$ ]] && echo "$n" && return
  fi
  echo "NA"
}

JSON_OUT=${JSON_OUT:-"$OUTDIR/syscalls_by_binary.json"}
: > "$JSON_OUT"
echo "[" >> "$JSON_OUT"
LIBS_OUT=${LIBS_OUT:-"$OUTDIR/libs.json"}
: > "$LIBS_OUT"
echo "[" >> "$LIBS_OUT"
first_obj=1

for exe in "${!FILES_BY_EXE[@]}"; do
  IFS=' ' read -r -a files <<< "${FILES_BY_EXE[$exe]}"

  mapfile -t names < <(extract_syscalls "${files[@]}" | sort -u)
  mapfile -t libs < <(extract_libs "${files[@]}" | sort -u)

  declare -A seen=()
  nums=()
  for s in "${names[@]}"; do
    n=$(resolve_num "$s")
    [[ "$n" =~ ^[0-9]+$ ]] || continue
    [[ -n "${seen[$n]:-}" ]] && continue
    seen[$n]=1
    nums+=("$n")
  done
  mapfile -t nums < <(printf "%s\n" "${nums[@]}" | sort -n)

  if ((${#nums[@]})); then
    printf -v nums_csv '%s,' "${nums[@]}"
    nums_json="[${nums_csv%,}]"
  else
    nums_json="[]"
  fi

  printf -v libs_csv '"%s",' "${libs[@]}"
  libs_json="[${libs_csv%,}]"

  bin_name="$(basename "$exe")"

  if (( first_obj )); then first_obj=0; else echo "," >> "$JSON_OUT"; echo "," >> "$LIBS_OUT"; fi
  printf '{"binary":"%s","syscall_list":%s}' "$bin_name" "$nums_json" >> "$JSON_OUT"
  printf '{"binary":"%s","libs_list":%s}' "$bin_name" "$libs_json" >> "$LIBS_OUT"
done

echo "]" >> "$JSON_OUT"
echo "Wrote: $JSON_OUT"
echo "]" >> "$LIBS_OUT"
echo "Wrote: $LIBS_OUT"
