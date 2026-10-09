# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import argparse
import os
import subprocess
import sys
import json
import config

from elftools.elf.elffile import ELFFile
from elftools.elf.dynamic import DynamicSegment
from gen_syscall import create_program
from safer import Safer

#packages = ["postgresql", "proftpd", "redis"]
packages = ["bmq"]
#packages = ["bind"]
#packages = ["apache", "bde", "bind", "bmq", "comdb2", "lighttpd", "memcached", "mysql", "nginx", "postgresql", "proftpd", "redis"]

#packages = ["lighttpd", "memcached", "mysql", "nginx", "postgresql", "proftpd", "redis"]

import re
from subprocess import run, PIPE


def create_syscall_list(binaries, outfile, tool):
    data = []
    for b in binaries:
        p = create_program(tool, b)
        syscall_list = p.syscalls()
        print("[+] -----binary: ", b, "-----")
        print("[+] Syscalls: ", syscall_list)
        print("[+] Syscall count: ", len(syscall_list))
        bin_name = os.path.basename(b)

        func_info = {
            "binary": bin_name,
            "syscall_list": list(syscall_list)
        }

        data.append(func_info)

    export_function_info_json(outfile, data)
    return data

IGNORED_SYSCALLS = {219}

def compare_syscall_gt(gt_syscalls, syscalls):
    missing = []
    for s_gt in gt_syscalls:
        if s_gt in IGNORED_SYSCALLS:
            continue
        found = False
        for s in syscalls:
            if s == s_gt:
                found = True
                break
        if found == False:
            missing.append(s_gt)

    return missing

def main():

    parser = argparse.ArgumentParser(
        description="Analyze a binary and its dependencies using the specified tool."
    )
    
    parser.add_argument("policy_gen_tool",
        nargs="?", default="angr",
        choices=["angr", "ghidra", "safer", "ida", "bninja", "safer_reloc", "safer_split_escape", "safer_argmatch", "safer_enhanced", "safer_sysfilter"],
        help="Analysis tool to use (angr, ghidra, safer) or the ground truth data (gt)"
    )
    parser.add_argument("pkg",
        nargs="?", default="nginx",
        choices=["nginx", "apache", "lighttpd", "proftpd", "memcached", "redis", "bind", "bmq", "comdb2", "postgresql", "mysql"],
        help="Package to evaluate"
    )
    
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
    
    args = parser.parse_args()
    print(args)

    current_dir = config.BASE_DIR
    testsuite_dir = config.TESTSUITE_DIR
    testsuite = os.path.join(config.BINARIES_DIR, args.optimization, args.config)
    data_path = os.path.join(testsuite_dir, "testdata", args.policy_gen_tool)
    os.makedirs(data_path, exist_ok=True)
    pkg = args.pkg
    pkg_path = testsuite + "/" + pkg
    outfile = data_path + "/" + pkg + "_" + args.config + "_" + args.optimization + ".json"
    gtfile = testsuite_dir + "/testdata/gt/" + pkg + ".json"
    data = None
    if os.path.exists(outfile):
        with open(outfile, "r") as f:
            data = json.load(f)
    else:
        data = create_syscall_list(binaries, outfile, args.policy_gen_tool)

    gt_data = None
    if os.path.exists(gtfile):
        with open(gtfile, "r") as f:
            gt_data = json.load(f)
    else:
        print("[!] gt data file ", gtfile, " does not exist. Please create ground truth data")
    for gt_d in gt_data:
        exe = gt_d["binary"]
        syscall_list = gt_d["syscall_list"]
        for d in data:
            exe_to_check = d["binary"]
            if exe_to_check == exe:
                syscall_list_to_check = d["syscall_list"]
                missing = compare_syscall_gt(syscall_list, syscall_list_to_check)
                print("[", args.policy_gen_tool, "]", "Binary: ", pkg,"-",exe, " Missing syscalls: ", missing)




if __name__ == "__main__":
    main()
