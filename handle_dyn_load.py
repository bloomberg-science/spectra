# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import argparse
import sys
import os
import subprocess
import config
from safer import Safer, SaferSysfilter, SaferEnhanced
from angrext import AngrTool
from ghidra import Ghidra
from graph import Function, Module, Program
from ida import IDA
from typing import List
from bninja import BNinja
from gen_syscall import create_program
from pkg_utils import list_executables

def main():
    parser = argparse.ArgumentParser(
        description="Analyze a binary and its dependencies using the specified tool."
    )
    
    parser.add_argument("tool",
        nargs="?", default="angr",
        choices=["angr", "ghidra", "safer", "ida", "bninja", "safer_reloc", "safer_enhanced", "safer_sysfilter"],
        help="Analysis tool to use (angr, ghidra, safer)"
    )

    parser.add_argument("pkg",
        nargs="?", default="nginx",
        choices=["nginx", "apache", "lighttpd", "proftpd", "memcached", "redis", "bind", "bmq", "comdb2", "postgresql", "mysql","bas"],
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
    
    pkg = args.pkg
    pkg_path = testsuite + "/" + pkg
    binaries = list_executables(pkg_path)
    all_dlopen_set = set()
    all_dlsym_set = set()
    all_execve_set = set()
    for b in binaries:
        bin_name = os.path.basename(b)
        p = create_program(args.tool, b, [])
        dlopen_set = p.mods_with_plt_target("dlopen")
        dlsym_set = p.mods_with_plt_target("dlsym")
        execve_set = p.mods_with_plt_target("execve")
        execve_set.update(p.mods_with_plt_target("execv"))
        execve_set.update(p.mods_with_plt_target("execl"))
        execve_set.update(p.mods_with_plt_target("system"))
        execve_set.update(p.mods_with_plt_target("execvpe"))
        execve_set.update(p.mods_with_plt_target("execveat"))
        execve_set.update(p.mods_with_plt_target("execvp"))
        execve_set.update(p.mods_with_plt_target("fexecve"))
        all_dlopen_set.update(dlopen_set)
        all_dlsym_set.update(dlsym_set)
        all_execve_set.update(execve_set)

    print("dlopen --",all_dlopen_set)
    print("dlsym --",all_dlsym_set)
    print("execve --",all_execve_set)

    all_tgt_libs = set()
    all_tgt_libs.update(all_dlopen_set)
    all_tgt_libs.update(all_dlsym_set)
    all_tgt_libs.update(all_execve_set)

    testlib_dir = testsuite_dir + "/testlibs/"
    os.makedirs(testlib_dir, exist_ok=True)
    testlib_dir = testlib_dir + pkg
    os.makedirs(testlib_dir, exist_ok=True)

    inst_tool = Safer("dlopen_instrument")

    for lib in all_tgt_libs:
        lib_name = os.path.basename(lib)
        cmd = [
            "cp",
            lib,
            testlib_dir + "/" + lib_name + ".orig"
        ]
        result = subprocess.run(cmd, capture_output=True, check=True)
        inst_bin = inst_tool.instrument(testlib_dir + "/" + lib_name + ".orig",[])
        cmd = [
            "mv",
            inst_bin,
            testlib_dir + "/" + lib_name
        ]
        result = subprocess.run(cmd, capture_output=True, check=True)


if __name__ == "__main__":
    main()
