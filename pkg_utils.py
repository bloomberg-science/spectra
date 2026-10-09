# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import os
import json
import argparse
from elftools.elf.elffile import ELFFile
from elftools.elf.dynamic import DynamicSegment
import config
from errors import logger

DF_1_PIE = 0x08000000


def is_elf_file(filepath):
    try:
        with open(filepath, 'rb') as f:
            magic = f.read(4)
            return magic == b'\x7fELF'
    except Exception:
        return False


def is_executable(path: str):
    with open(path, 'rb') as f:
        elf = ELFFile(f)
        et = elf['e_type']

        flags1 = 0
        for seg in elf.iter_segments():
            if isinstance(seg, DynamicSegment):
                for tag in seg.iter_tags():
                    if tag.entry.d_tag == 'DT_FLAGS_1':
                        flags1 |= int(tag['d_val'])

        is_pie = bool(flags1 & DF_1_PIE)

        if et == 'ET_EXEC':
            return True
        if et == 'ET_DYN' and is_pie:
            return True
        return False


def list_executables(directory):
    logger.info(f"Listing elf files in directory: {directory}")
    elf_files = []
    for file in os.listdir(directory):
        path = os.path.join(directory, file)
        if is_elf_file(path) and is_executable(path):
            logger.info(f"Found executable: {path}")
            elf_files.append(path)
    return elf_files


def export_json(output_path, data):
    with open(output_path, "w") as f:
        json.dump(data, f, indent=4)
    logger.info(f"Exported to: {output_path}")


def resolve_paths(args):
    """Resolve testsuite and data paths from parsed args."""
    testsuite_dir = config.TESTSUITE_DIR
    binaries_dir = os.path.join(config.BINARIES_DIR, args.optimization, args.config)

    tool_name = getattr(args, 'tool', None) or getattr(args, 'policy_gen_tool', None)
    data_path = os.path.join(config.TESTDATA_DIR, tool_name) if tool_name else None

    return binaries_dir, data_path, testsuite_dir


def add_common_args(parser):
    """Add the standard arguments shared by eval_pkg and test_pkg."""
    parser.add_argument("optimization",
        nargs="?", default="O2",
        choices=["O0", "O1", "O2", "O3", "Ofast", "Os"],
        help="Optimization level"
    )
    parser.add_argument("config",
        nargs="?", default="stripped",
        choices=["fulldbg", "symonly", "stripped"],
        help="Symbol configuration for target binaries"
    )
    parser.add_argument("pkg",
        nargs="?", default="nginx",
        choices=config.PACKAGES + ["bas"],
        help="Package to evaluate"
    )



def load_gt_libs(testsuite_dir, pkg):
    """Load ground truth dlopen/execve library lists for a package."""
    gt_libs_path = os.path.join(testsuite_dir, "testdata", "libsdata", pkg)
    gt_dlopen = set()
    gt_execve = set()

    for fname, target_set in (("dlopen", gt_dlopen), ("execve", gt_execve)):
        fpath = os.path.join(gt_libs_path, fname)
        if os.path.exists(fpath):
            with open(fpath, "r") as f:
                for line in f:
                    target_set.add(line.rstrip("\n"))

    gt_dlsym = set()
    dlsym_path = os.path.join(gt_libs_path, "dlsym")
    if os.path.exists(dlsym_path):
        with open(dlsym_path, "r") as f:
            for line in f:
                gt_dlsym.add(line.rstrip("\n"))

    return gt_dlopen, gt_execve, gt_dlsym


def load_gt_syscalls(testsuite_dir, pkg):
    """Load ground truth syscall data for a package."""
    gt_path = os.path.join(testsuite_dir, "testdata", "gt", pkg + ".json")
    if os.path.exists(gt_path):
        with open(gt_path, "r") as f:
            return json.load(f)
    return []


def get_binary_gt_syscalls(gt_syscalls, bin_name):
    """Get ground truth syscall list for a specific binary."""
    for entry in gt_syscalls:
        if entry["binary"] == bin_name:
            return entry["syscall_list"]
    return []
