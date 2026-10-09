#!/usr/bin/env bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

# Generic perf-trace-based syscall capture script.
# Used by: redis, bind, comdb2, bmq
#
# Usage:
#   ./capture_syscall_perf.sh <bin_dir> <run_command...>
#
# The script runs the given command under perf trace, identifies which target
# binaries were executed (by matching comm names), propagates PID-to-binary
# mapping through clone/fork, and outputs a JSON file with syscall numbers.
#
# Output (in OUTDIR):
#   syscalls.json  — [{"binary":"name","syscall_list":[nums...]}]
#
# Requires: perf, ausyscall

set -euo pipefail

TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

BIN_DIR="${1:-}"
shift || true

[[ -n "$BIN_DIR" && -d "$BIN_DIR" ]] || { echo "Need a valid bin dir as 1st arg"; exit 2; }

# Collect target comm names (basenames of executable files)
mapfile -t TARGETS < <(find "$BIN_DIR" -maxdepth 1 -type f -perm -111 -printf "%f\n" 2>/dev/null || find "$BIN_DIR" -maxdepth 1 -type f -perm +111 -exec basename {} \; | sort -u)
[[ ${#TARGETS[@]} -gt 0 ]] || { echo "No executables in $BIN_DIR"; exit 2; }

OUTDIR="${OUTDIR:-/tmp/perf_targets_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUTDIR"

TARGETS_FILE="$OUTDIR/targets.list"
printf "%s\n" "${TARGETS[@]}" > "$TARGETS_FILE"

LOG="$OUTDIR/perf.trace.log"
echo "[*] Targets: $(tr '\n' ' ' < "$TARGETS_FILE")" >&2
echo "[*] Running: $* (perf trace). Log -> $LOG" >&2

sudo perf trace -o "$LOG" "$@" || true

# Parse the perf trace log with awk
SYS_PAIRS="$OUTDIR/sys_pairs.tsv"
BINS_SEEN="$OUTDIR/bins_seen.txt"

awk -v TF="$TARGETS_FILE" -v OUT_SYS="$SYS_PAIRS" -v OUT_BINS="$BINS_SEEN" '
  BEGIN {
    while ((getline line < TF) > 0) { gsub(/^[ \t]+|[ \t]+$/, "", line); if (line!="") targets[line]=1 }
    close(TF)
  }
  function parse_comm_pid(line,   m){
    if (match(line, /[[:space:]]([A-Za-z0-9_.:+-]+)\/([0-9]+)[[:space:]]/, m)) {
      H_comm=m[1]; H_pid=m[2]+0; return 1
    }
    return 0
  }
  function parse_sys(line,   m){
    if (match(line, /<\.\.\.\s*([a-z_][a-z0-9_]*)\s+resumed>/, m)) return m[1]
    if (match(line, /[[:alnum:]_.:+-]+\/[0-9]+[[:space:]]+([a-z_][a-z0-9_]*)\(/, m)) return m[1]
    if (match(line, /[[:space:]]+([a-z_][a-z0-9_]*)\(/, m)) return m[1]
    return ""
  }
  function parse_ret(line,   m){
    if (match(line, /=\s*(-?[0-9]+)([[:space:]]|$)/, m)) return m[1]+0
    return ""
  }
  function is_completed(line){
    return (index(line,"[continued]:")>0 ||
            line ~ /\)\s*=\s/ ||
            line ~ /[[:space:]]rt_sigreturn\(\).*\.{3}$/)
  }
  function add_bin(pid, bin,    cur, needle) {
    cur = (pid in root_of ? root_of[pid] : "")
    needle = "\n" bin "\n"
    if (index("\n" cur "\n", needle) == 0) {
      root_of[pid] = (cur ? cur "\n" : "") bin
      bins_seen[bin] = 1
    }
  }
  function propagate_bins(parent_pid, child_pid,    i, bins) {
    if (!(parent_pid in root_of)) return
    split(root_of[parent_pid], bins, "\n")
    for (i in bins) if (bins[i] != "") add_bin(child_pid, bins[i])
  }
  {
    if (!parse_comm_pid($0)) next
    comm = H_comm; pid = H_pid
    if (comm in targets) add_bin(pid, comm)
    sys = parse_sys($0); if (sys == "") next
    if ((pid in root_of) && (sys=="clone" || sys=="clone3" || sys=="fork" || sys=="vfork")) {
      ret = parse_ret($0)
      if (ret != "" && ret > 0) propagate_bins(pid, ret)
    }
    if (!is_completed($0)) next
    if (pid in root_of) {
      split(root_of[pid], bins, "\n")
      for (i in bins) {
        bin = bins[i]
        if (bin == "") continue
        key = bin "\t" sys
        if (!(key in seen_sys)) {
          print bin "\t" sys >> OUT_SYS
          seen_sys[key] = 1
        }
      }
    }
  }
  END {
    for (b in bins_seen) print b > OUT_BINS
  }
' "$LOG"

# Resolve syscall names to numbers
command -v ausyscall >/dev/null 2>&1 || { echo "ausyscall not found; install auditd/audit tools" >&2; exit 1; }
ARCH="$(uname -m)"
declare -A NAME2NUM

while read -r nr name; do
  [[ "$nr" =~ ^[0-9]+$ && "$name" =~ ^[A-Za-z0-9_]+$ ]] || continue
  NAME2NUM["$name"]="$nr"
done < <(ausyscall -a "$ARCH" --dump 2>/dev/null | awk 'NR>1{print $1, $2}')

resolve_num() {
  local name="$1" n=""
  case "$name" in
    pread64)  name="pread" ;;
    pwrite64) name="pwrite" ;;
  esac
  if [[ -n "${NAME2NUM[$name]:-}" ]]; then
    echo "${NAME2NUM[$name]}"; return
  fi
  if command -v scmp_sys_resolver >/dev/null 2>&1; then
    n=$(scmp_sys_resolver "$name" 2>/dev/null || true)
    [[ "$n" =~ ^[0-9]+$ ]] && echo "$n" && return
  fi
  echo "NA"
}

declare -A SYSCALLS_BY_BIN

if [[ -f "$SYS_PAIRS" ]]; then
  while IFS=$'\t' read -r bin sys; do
    n=$(resolve_num "$sys")
    [[ "$n" =~ ^[0-9]+$ ]] || continue
    SYSCALLS_BY_BIN["$bin"]+="$n "
  done < <(sort -u "$SYS_PAIRS")
fi

# Build syscalls.json
JSON_SYSC="${JSON_OUT:-$OUTDIR/syscalls.json}"
{
  echo "["
  first=1
  if [[ -f "$BINS_SEEN" ]]; then
    while IFS= read -r bin; do
      nums="${SYSCALLS_BY_BIN[$bin]-}"
      if [[ -n "$nums" ]]; then
        mapfile -t arr < <(tr ' ' '\n' <<<"$nums" | sed '/^$/d' | sort -n -u)
        sysjson="$(printf "%s," "${arr[@]}")"; sysjson="[${sysjson%,}]"
      else
        sysjson="[]"
      fi
      if (( first )); then first=0; else echo ","; fi
      printf '{"binary":"%s","syscall_list":%s}' "$bin" "$sysjson"
    done < <(sort -u "$BINS_SEEN")
  fi
  echo
  echo "]"
} > "$JSON_SYSC"

echo "[*] Wrote: $JSON_SYSC"
