#!/usr/bin/env python3
# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

"""Fix libsdata files: deduplicate entries and resolve stale or relative dlopen/execve paths
(execve command lines are reduced to their executables)."""

import os
import subprocess
import sys
import config


SYSTEM_PREFIXES = ("/usr/", "/lib/", "/lib64/")
SYSTEM_BIN_DIRS = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")


def dedup_lines(filepath):
    """Read file, return deduplicated lines preserving first-occurrence order."""
    seen = set()
    result = []
    with open(filepath, "r") as f:
        for line in f:
            entry = line.rstrip("\n")
            if entry and entry not in seen:
                seen.add(entry)
                result.append(entry)
    return result


def find_lib(basename, testsuite_dir, pkg):
    """Search testsuite/ for a library by basename, preferring gcc/O2/fulldbg/<pkg>/."""
    result = subprocess.run(
        ["find", testsuite_dir, "-name", basename, "-type", "f"],
        capture_output=True, text=True
    )
    candidates = [p.strip() for p in result.stdout.splitlines() if p.strip()]
    if not candidates:
        return None

    preferred = f"gcc/O2/fulldbg/{pkg}/"
    for c in candidates:
        if preferred in c:
            return c

    for c in candidates:
        if "subset_binaries" in c:
            return c

    for c in candidates:
        if f"/{pkg}/" in c:
            return c

    return candidates[0]


def find_system_bin(name):
    """Locate a bare command name (e.g. 'rm') in the system bin directories.

    A fixed list is used instead of PATH so a virtualenv's bin/ cannot shadow system binaries.
    """
    for d in SYSTEM_BIN_DIRS:
        candidate = os.path.join(d, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def execve_targets(filepath):
    """Return the deduplicated executables from an execve log.

    Logged entries may be full command lines ('comdb2/build/db/comdb2 db -lrl ...');
    only the executable (first token) is a target.
    """
    seen = set()
    result = []
    for entry in dedup_lines(filepath):
        target = entry.split()[0] if entry.split() else ""
        if target and target not in seen:
            seen.add(target)
            result.append(target)
    return result


def is_path(entry):
    """True for file-path entries; false for logged shell commands (e.g. 'rm -rf ...')."""
    return "/" in entry and not any(c.isspace() for c in entry)


def fix_paths(entries, testsuite_dir, pkg, bare_names_are_bins=False):
    """Resolve stale or testsuite-relative paths in deduplicated dlopen/execve entries.

    Entries may be absolute paths from another machine or paths relative to testsuite/
    (the form stored in the repo); both are resolved against this checkout. With
    bare_names_are_bins, bare command names (execve targets such as 'rm') are looked
    up in the system bin directories.
    """
    fixed = []
    stats = {"kept": 0, "resolved": 0, "not_found": 0}

    for entry in entries:
        if bare_names_are_bins and "/" not in entry:
            resolved = find_system_bin(entry)
            if resolved:
                fixed.append(resolved)
                stats["resolved"] += 1
            else:
                fixed.append(entry)
                stats["not_found"] += 1
                print(f"    WARNING: not found in {', '.join(SYSTEM_BIN_DIRS)}: {entry}")
            continue

        if entry.startswith(SYSTEM_PREFIXES) or not is_path(entry):
            fixed.append(entry)
            stats["kept"] += 1
            continue

        if os.path.isabs(entry) and os.path.exists(entry):
            fixed.append(entry)
            stats["kept"] += 1
            continue

        if not os.path.isabs(entry):
            candidate = os.path.join(testsuite_dir, entry)
            if os.path.exists(candidate):
                fixed.append(candidate)
                stats["resolved"] += 1
                continue

        basename = os.path.basename(entry)
        resolved = find_lib(basename, testsuite_dir, pkg)
        if resolved:
            fixed.append(resolved)
            stats["resolved"] += 1
            print(f"    resolved: {basename} -> {resolved}")
        else:
            fixed.append(entry)
            stats["not_found"] += 1
            print(f"    WARNING: not found: {basename} (keeping original: {entry})")

    return fixed, stats


def fix_package(pkg_dir, testsuite_dir):
    """Fix all libsdata files for one package."""
    pkg = os.path.basename(pkg_dir)
    print(f"\n  {pkg}/")

    dlsym_path = os.path.join(pkg_dir, "dlsym")
    if os.path.exists(dlsym_path):
        original_count = sum(1 for _ in open(dlsym_path))
        entries = dedup_lines(dlsym_path)
        with open(dlsym_path, "w") as f:
            f.write("\n".join(entries) + "\n" if entries else "")
        print(f"    dlsym: {original_count} -> {len(entries)} entries")

    for fname in ("dlopen", "execve"):
        fpath = os.path.join(pkg_dir, fname)
        if not os.path.exists(fpath):
            continue
        original_count = sum(1 for _ in open(fpath))
        if fname == "execve":
            fixed, stats = fix_paths(execve_targets(fpath), testsuite_dir, pkg, bare_names_are_bins=True)
        else:
            fixed, stats = fix_paths(dedup_lines(fpath), testsuite_dir, pkg)
        with open(fpath, "w") as f:
            f.write("\n".join(fixed) + "\n" if fixed else "")
        print(f"    {fname}: {original_count} -> {len(fixed)} entries "
              f"(resolved: {stats['resolved']}, not_found: {stats['not_found']})")


def main():
    libsdata_dir = config.LIBSDATA_DIR
    testsuite_dir = config.TESTSUITE_DIR

    if not os.path.isdir(libsdata_dir):
        print(f"Error: {libsdata_dir} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Fixing libsdata in: {libsdata_dir}")
    print(f"Searching for libs in: {testsuite_dir}")

    for pkg in sorted(os.listdir(libsdata_dir)):
        pkg_dir = os.path.join(libsdata_dir, pkg)
        if os.path.isdir(pkg_dir):
            fix_package(pkg_dir, testsuite_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
