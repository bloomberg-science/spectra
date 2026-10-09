# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import argparse
import os
import json
import config
import pkg_utils
from gen_syscall import create_program
from errors import logger, set_verbose, ProgressBar
from syscall_table import format_syscall_list


def main():
    parser = argparse.ArgumentParser(
        description="Analyze a binary and its dependencies using the specified tool."
    )

    parser.add_argument("tool",
        nargs="?", default="angr",
        choices=["angr", "ghidra", "safer", "ida", "bninja", "safer_reloc", "safer_split_escape", "safer_argmatch", "safer_enhanced", "safer_sysfilter"],
        help="Analysis tool to use (angr, ghidra, safer)"
    )
    pkg_utils.add_common_args(parser)
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()
    if args.verbose:
        set_verbose(True)

    binaries_dir, data_path, testsuite_dir = pkg_utils.resolve_paths(args)
    os.makedirs(data_path, exist_ok=True)

    pkg = args.pkg
    pkg_path = os.path.join(binaries_dir, pkg)
    binaries = pkg_utils.list_executables(pkg_path)

    outfile = os.path.join(data_path, f"{pkg}_{args.config}_{args.optimization}.json")

    gt_dlopen, gt_execve, gt_dlsym = pkg_utils.load_gt_libs(testsuite_dir, pkg)
    gt_syscalls = pkg_utils.load_gt_syscalls(testsuite_dir, pkg)

    data = []
    pkg_progress = ProgressBar(len(binaries), desc=f"Package {pkg}")
    for b in binaries:
        bin_name = os.path.basename(b)
        pkg_progress.update(bin_name)
        b_gt_syscall = pkg_utils.get_binary_gt_syscalls(gt_syscalls, bin_name)

        p = create_program(args.tool, b, b_gt_syscall, gt_dlopen, gt_dlsym, args.optimization, gt_execve)
        syscall_list = p.syscalls()

        print(f"\n  {bin_name}: {len(syscall_list)} syscalls — {format_syscall_list(syscall_list)}")
        print(f"  AICT: {p.aict:.2f}")

        data.append({
            "binary": bin_name,
            "syscall_list": list(syscall_list),
            "aict": p.aict,
        })

    pkg_progress.finish()
    pkg_utils.export_json(outfile, data)


if __name__ == "__main__":
    main()
