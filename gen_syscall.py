# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import argparse
import sys
import os
import subprocess
from graph import Function, Module, Program
from analysistool import create_tool, get_tool_prog_flags, available_tools
from errors import logger, DependencyNotFoundError, ProgressBar
from syscall_table import format_syscall_list
from typing import List

# Import all tool modules so their @register_tool decorators execute
import safer  # registers: safer, safer_enhanced, safer_reloc, safer_sysfilter
import angrext
import ghidra
import ida
import bninja


def get_direct_dependencies(binary_path: str) -> List[str]:
    try:
        result = subprocess.run(["ldd", binary_path], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError:
        return []

    deps = []
    for line in result.stdout.splitlines():
        if "linux-vdso.so" in line:
            continue
        parts = line.strip().split("=>")
        if len(parts) == 2:
            path = parts[1].strip().split(" ")[0]
            if os.path.isfile(path):
                deps.append(path)
            else:
                logger.warning(f"Dependency not found: {parts[0]} (skipping)")
        elif ".so" in parts[0]:
            path = parts[0].strip().split(" ")[0]
            if os.path.isfile(path):
                deps.append(path)
    return deps


def find_all_dependencies(binary_path: str) -> List[str]:
    visited = set()
    queue = [binary_path]

    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)
        deps = get_direct_dependencies(current)
        for dep in deps:
            if dep not in visited:
                queue.append(dep)

    return visited


def create_program(tool_name: str, prog_path: str, gt_syscall_list=set(), dlopen_libs=set(), dlsym_fns=set(), run_id="0", execve_bins=set()) -> Program:
    logger.info(f"Searching for dependencies in: {prog_path}")
    deps = find_all_dependencies(prog_path)

    dlopen_deps = set()
    for d in dlopen_libs:
        if os.path.exists(d):
            d_deps = find_all_dependencies(d)
            dlopen_deps.update(d_deps)

    for d in dlopen_deps:
        if os.path.exists(d):
            deps.add(d)

    execve_paths = set()
    for d in execve_bins:
        if os.path.exists(d):
            execve_paths.add(d)
            d_deps = find_all_dependencies(d)
            for dd in d_deps:
                if os.path.exists(dd):
                    deps.add(dd)

    if not deps:
        logger.warning("No ELF binaries found")
        return

    logger.info(f"Dependencies: {deps}")

    prog_name = os.path.basename(prog_path)
    prog = Program(prog_name)
    prog.gt_syscall_list = gt_syscall_list
    prog.dlsym_fns = dlsym_fns
    prog.execve_bins = execve_paths

    # Apply program flags from tool registration
    for attr, val in get_tool_prog_flags(tool_name).items():
        setattr(prog, attr, val)

    tool = create_tool(tool_name, run_id=run_id)
    tool.runid = run_id

    mod_map = {}
    progress = ProgressBar(len(deps), desc="Analyzing deps")

    for d in deps:
        main = False
        if os.path.basename(d) == prog_name:
            main = True
        if os.path.exists(d):
            progress.update(os.path.basename(d))
            mod = tool.extract(d, main)
            if main:
                mod.add_deps(deps)
            else:
                extra_deps = find_all_dependencies(d)
                mod.add_deps(extra_deps)
            prog.add_module(mod, main)
            mod_map[d] = mod
        else:
            progress.update(os.path.basename(d))
            logger.warning(f"Could not find dependency: {d}")

    progress.finish()

    for m, mod in mod_map.items():
        dep_list = mod.deps
        for d in dep_list:
            if os.path.exists(d):
                if d != m:
                    logger.info(f"{m} -> {d}")
                    d_mod = mod_map[d]
                    d_mod.add_deps([m])

    return prog


def main():
    parser = argparse.ArgumentParser(description="Analyze a binary and its dependencies using the specified tool.")
    parser.add_argument("tool", choices=available_tools(), help="Analysis tool to use")
    parser.add_argument("program", help="path to target binary")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        from errors import set_verbose
        set_verbose(True)

    p = create_program(args.tool, args.program)
    syscall_list = p.syscalls()

    print("Syscalls:", format_syscall_list(syscall_list))
    print("Syscall count:", len(syscall_list))


if __name__ == "__main__":
    main()
