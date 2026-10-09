# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import argparse
import os
import subprocess
import sys
import config
from gen_syscall import create_program
from safer import Safer


def main():
    parser = argparse.ArgumentParser(
        description="Harden a binary by generating a syscall policy and instrumenting it with SECCOMP filters."
    )

    parser.add_argument("policy_gen_tool",
        nargs="?", default="angr",
        choices=["angr", "ghidra", "safer", "ida", "bninja", "safer_reloc", "safer_enhanced", "safer_sysfilter"],
        help="Analysis tool to use for syscall policy generation"
    )

    parser.add_argument("binary",
        help="Path to the binary to harden"
    )

    parser.add_argument("instrumentation_tool",
        nargs="?", default="safer",
        choices=["safer"],
        help="Tool used for binary instrumentation"
    )

    args = parser.parse_args()
    print(args)

    inst_tool = None
    if args.instrumentation_tool == "safer":
        inst_tool = Safer()
    else:
        print(f"[!] {args.instrumentation_tool} is not supported for instrumentation")
        sys.exit(1)

    inst_dir = os.path.join(config.BASE_DIR, "hardened_binaries")
    os.makedirs(inst_dir, exist_ok=True)

    b = args.binary
    exename = os.path.basename(b)

    copy_bin = os.path.join(inst_dir, exename)
    subprocess.run(["cp", b, copy_bin], capture_output=True, check=True)

    p = create_program(args.policy_gen_tool, copy_bin)
    syscall_list = p.syscalls()
    print(f"[+] Syscalls ({len(syscall_list)}): {sorted(syscall_list)}")

    inst_bin = inst_tool.instrument(copy_bin, syscall_list)
    print(f"[+] Final hardened binary: {inst_bin}")


if __name__ == "__main__":
    main()
