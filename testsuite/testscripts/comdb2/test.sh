#!/usr/bin/bash
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.


TESTSUITE_ROOT="${TESTSUITE_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
PKG_DIR="${TESTSUITE_ROOT}/comdb2"

wd=`pwd`
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOGFILE="$PKG_DIR/test_run_$TIMESTAMP.log"

usage() {
  echo "Usage: $0 <INSTALL_DIR>" >&2
  exit 1
}

[[ $# -ge 1 ]] || usage
INSTALL_DIR="$1"; shift || true

cd "${PKG_DIR}"

# Clean old .gcda files to avoid stamp mismatch with .gcno files
if find "${PKG_DIR}" -name "*.gcno" -type f 2>/dev/null | grep -q .; then
    echo "Coverage build detected - cleaning old .gcda files..."
    find "${PKG_DIR}" -name "*.gcda" -type f -delete 2>/dev/null || true
fi
BIN_DIR="$INSTALL_DIR"
[[ -d "$BIN_DIR" ]] || { echo "No such bin dir: $BIN_DIR" >&2; exit 1; }
[[ -d build ]] || { echo "Run from repo root (must have ./build)" >&2; exit 1; }

copied=0; missing=0

mapfile -t src_bins < <(find "$BIN_DIR" -maxdepth 1 -type f -perm -u+x -printf '%p
' | sort)

# shows every element, one per line

for i in "${!src_bins[@]}"; do
  printf '%3d  %s
' "$i" "${src_bins[$i]}"
done


if [[ ${#src_bins[@]} -eq 0 ]]; then
  echo "No executables found in $BIN_DIR" >&2
  exit 1
fi

for src in "${src_bins[@]}"; do
  name="$(basename $src)"
  # find matching targets in the build/ tree
  # first prefer executable files named exactly like the source

  mapfile -t matches < <(find build -type f -name "$name" -print 2>/dev/null)

  if [[ ${#matches[@]} -eq 0 ]]; then
    echo "MISS: $name (no matching file in ./build)" >&2
    ((missing++))
    continue
  fi

  for dest in "${matches[@]}"; do
    dest_dir="$(dirname $dest)"
    [[ -d "$dest_dir" ]] || mkdir -p "$dest_dir"
    cp "$src" "$dest"
    echo "COPIED:  $src -> $dest"
    ((copied++))
  done
done

echo
echo "Summary:"
echo "  copied = $copied"
echo "  no-match (missing) = $missing"


for d in ./tests/*.test; do
  [[ -d "$d" ]] || continue
  f="$d/lrl.options"

  if [[ -e "$f" ]]; then
    # Append only if the line (any spacing/case) isn’t present
    if ! grep -qiE '^[[:space:]]*directio[[:space:]]+off[[:space:]]*$' "$f"; then
      printf '
%s
' 'directio off' >> "$f"
      echo "added -> $f"
    else
      echo "already set -> $f"
    fi
  else
    # Create the file with the setting
    printf '%s
' 'directio off' > "$f"
    echo "created -> $f"
  fi
done

cd ./tests

export MAX_TEST_FAILURES=1000

make -kj20 &> "$LOGFILE"

pass=`grep "logs in" $LOGFILE | grep "success" | wc -l`
fail=`grep "logs in" $LOGFILE | grep "failed\|timeout" | wc -l`

echo "Passed : ${pass}"
echo "Failed : ${fail}"

cd "${wd}"

source "${TESTSUITE_ROOT}/lib/coverage.sh"
collect_coverage "${PKG_DIR}" "${TIMESTAMP}"
