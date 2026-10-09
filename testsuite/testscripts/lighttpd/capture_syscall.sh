#!/usr/bin/env bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

# Usage:
#   ./strace_syscalls_map.sh /path/to/test.sh <suite> </path/to/lighttpd/bin_dir> [more args...]
# Prints: "binary_name: syscall1 syscall2 ..."

set -euo pipefail
TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PKG_DIR="${TESTSUITE_ROOT}/lighttpd"

# --- find the binaries dir among args (or via $BIN_DIR) ---
mapfile -t TARGETS < <(find "$PKG_DIR/src/" -maxdepth 1 -type f -perm -111 -print | sort | grep -v "\.so")
[[ ${#TARGETS[@]} -gt 0 ]] || { echo "No executables in $BIN_DIR"; exit 3; }

# canonical (real) paths + fast membership set
declare -A TARGET_SET
for i in "${!TARGETS[@]}"; do
  rp="$(readlink -f "${TARGETS[$i]}" || printf '%s' "${TARGETS[$i]}")"
  echo "Target: ${rp}"
  TARGETS[$i]="$rp"
  TARGET_SET["$rp"]=1
done

TS="$(date +%Y%m%d_%H%M%S)"
OUTDIR=${OUTDIR:-/tmp/strace_lighttpd_${TS}}
mkdir -p "$OUTDIR"

# --- run the test under strace ---
# -ff: one file per PID, -f follow forks, -ttt timestamps, -s0 full strings, -qq less noise
strace -ff -f -ttt -s 0 -qq -o "$OUTDIR/strace" -- "$@" || true

# --- helper: extract syscall names from strace logs (handles -ttt and [pid]) ---
extract_syscalls() {
  awk '
    # strip leading timestamp and optional [pid N]
    { sub(/^[0-9.]+[[:space:]]+/, "", $0) }
    { sub(/^\[pid[[:space:]]+[0-9]+\][[:space:]]+/, "", $0) }

    # case 1: resumed line  <... name resumed> ...)
    match($0, /^<\.\.\.[[:space:]]+([A-Za-z_][A-Za-z0-9_]*)[[:space:]]+resumed>.*/, m) { print m[1]; next }

    # case 2: normal syscall line  name(args) = ...
    match($0, /^([A-Za-z_][A-Za-z0-9_]*)\(/, m) { print m[1]; next }
  ' "$@"
}

extract_libs() {
  cat "$@" | grep "open" | grep "\.so" | grep -v "ENOENT" | grep -v "ld.so.cache" | awk '{print $3}' | sed 's/,//g' | sed 's/"//g' | sort -u
}


# --- map each PID file -> which target exec it belongs to (first exec line) ---
declare -A PID2EXE           # pid -> canonical target path
KEEP_LIST="$OUTDIR/pids.keep"; : > "$KEEP_LIST"

for f in "$OUTDIR"/strace.*; do
  [[ -f "$f" ]] || continue
  line="$(grep -m1 -E '(^|[[:space:]])execve(at)?\(' "$f" || true)"
  [[ -n "$line" ]] || continue
  while read -r q; do
    p="${q%\"}"; p="${p#\"}"                        # strip quotes
    if [[ -n "${TARGET_SET[$p]:-}" ]]; then
      pid="${f##*.}"
      PID2EXE["$pid"]="$p"
      echo "PID: $pid exe: $p"
      echo "$pid" >> "$KEEP_LIST"
      break
    fi
  done < <(grep -oE '"[^"]+"' <<<"$line")
done

# --- propagate mapping to children so forked workers count too ---
# --- collect children for each parent PID ---
# Collect children per parent (no subshells; filter only positive PIDs)
declare -A CHILDREN
for pf in "$OUTDIR"/strace.*; do
  [[ -f "$pf" ]] || continue
  parent="${pf##*.}"
  while read -r c; do
    [[ "$c" =~ ^[1-9][0-9]*$ ]] || continue     # only positive integers
    CHILDREN["$parent"]="${CHILDREN[$parent]-} $c"
  done < <(awk 'match($0, /(clone3?\(|fork\(|vfork\().*=\s*([0-9]+)/, m){print m[2]}' "$pf")
done

# BFS propagate mapping (safe for unset keys)
queue=(); for p in "${!PID2EXE[@]}"; do queue+=("$p"); done
while ((${#queue[@]})); do
  p="${queue[0]}"; queue=("${queue[@]:1}")
  children="${CHILDREN[$p]-}"                   # empty if unset → no nounset error
  for c in $children; do
    if [[ -z "${PID2EXE[$c]+x}" ]]; then
      PID2EXE["$c"]="${PID2EXE[$p]}"
      echo "$c" >> "$KEEP_LIST"
      queue+=("$c")
    fi
  done
done


NUM_KEEP=$(wc -l < "$KEEP_LIST" | tr -d ' ')
[[ "$NUM_KEEP" -gt 0 ]] || { echo "No target PIDs found. Is BIN_DIR correct?"; exit 4; }

# --- aggregate by binary path (many PIDs per binary) and print mapping ---
declare -A FILES_BY_EXE  # exe path -> " file1 file2 ..."
while read -r pid; do
  exe="${PID2EXE[$pid]}"
  FILES_BY_EXE["$exe"]+="$OUTDIR/strace.$pid "
done < "$KEEP_LIST"

# Output: "<basename>: syscall1 syscall2 ..."
#for exe in "${!FILES_BY_EXE[@]}"; do
#  IFS=' ' read -r -a files <<< "${FILES_BY_EXE[$exe]}"
#  # unique, sorted list of syscalls for this binary
#  syscalls="$(extract_syscalls "${files[@]}" | sort -u | tr '\n' ' ')"
#  syscalls="${syscalls%" "}"   # trim trailing space
#  echo "$(basename "$exe"): $syscalls"
#done | sort   # sort lines by binary name

# --- build a name->number resolver (prefer ausyscall, fallback to libseccomp) ---
ARCH=$(uname -m)
declare -A NAME2NUM

if command -v ausyscall >/dev/null 2>&1; then
  # ausyscall --dump: columns are "NR  NAME" (skip header)
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
  if [[ "$name" == "pread64" ]]; then
    name="pread"
  elif [[ "$name" == "pwrite64" ]]; then
    name="pwrite"
  fi
  if [[ -n "${NAME2NUM[$name]:-}" ]]; then
    echo "${NAME2NUM[$name]}"; return
  fi
  if [[ "$RESOLVER" == "seccomp" ]]; then
    n=$(scmp_sys_resolver "$name" 2>/dev/null || true)
    [[ "$n" =~ ^[0-9]+$ ]] && echo "$n" && return
  fi
  echo "NA"
}

# --- produce JSON: [{"binary":"<name>","syscall_list":[<nums>]}, ...] ---

JSON_OUT=${JSON_OUT:-"$OUTDIR/syscalls_by_binary.json"}
: > "$JSON_OUT"
echo "[" >> "$JSON_OUT"
LIBS_OUT=${LIBS_OUT:-"$OUTDIR/libs.json"}
: > "$LIBS_OUT"
echo "[" >> "$LIBS_OUT"
first_obj=1

for exe in "${!FILES_BY_EXE[@]}"; do
  IFS=' ' read -r -a files <<< "${FILES_BY_EXE[$exe]}"

  # unique syscall names for this binary
  mapfile -t names < <(extract_syscalls "${files[@]}" | sort -u)
  mapfile -t libs < <(extract_libs "${files[@]}" | sort -u)

  # map to numbers, dedupe & sort numerically
  declare -A seen=()
  nums=()
  for s in "${names[@]}"; do
    n=$(resolve_num "$s")
    [[ "$n" =~ ^[0-9]+$ ]] || continue
    [[ -n "${seen[$n]:-}" ]] && continue
    seen[$n]=1
    nums+=("$n")
  done
  # sort numbers
  mapfile -t nums < <(printf "%s\n" "${nums[@]}" | sort -n)

  # join as JSON array
  if ((${#nums[@]})); then
    printf -v nums_csv '%s,' "${nums[@]}"
    nums_json="[${nums_csv%,}]"
  else
    nums_json="[]"
  fi

  printf -v libs_csv '"%s",' "${libs[@]}"
  libs_json="[${libs_csv%,}]"

  bin_name="$(basename "$exe")"

  # write JSON object (add comma between objects)
  if (( first_obj )); then first_obj=0; else echo "," >> "$JSON_OUT"; echo "," >> "$LIBS_OUT"; fi
  printf '{"binary":"%s","syscall_list":%s}' "$bin_name" "$nums_json" >> "$JSON_OUT"
  printf '{"binary":"%s","libs_list":%s}' "$bin_name" "$libs_json" >> "$LIBS_OUT"
done

echo "]" >> "$JSON_OUT"
echo "Wrote: $JSON_OUT"
echo "]" >> "$LIBS_OUT"
echo "Wrote: $LIBS_OUT"
