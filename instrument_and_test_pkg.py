# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import argparse
import os
import subprocess
import sys
import json
import re
import config
import pkg_utils
from gen_syscall import create_program
from safer import Safer

SUMMARY_RE = re.compile(
    r'^\s*(Passed|Failed|Skipped|Errors?|Total)\s*:\s*(\d+)\s*$',
    re.IGNORECASE | re.MULTILINE
)


def parse_test_summary(text: str):
    out = {}
    for key, num in SUMMARY_RE.findall(text):
        k = key.lower()
        if k.startswith("error"):
            k = "errors"
        out[k] = int(num)

    if "total" not in out:
        out["total"] = sum(out.get(k, 0) for k in ("passed", "failed", "skipped", "errors"))
    for k in ("passed", "failed", "skipped", "errors"):
        out.setdefault(k, 0)
    return out


def parse_from_completed_process(cp):
    stdout = cp.stdout.decode("utf-8", errors="replace") if isinstance(cp.stdout, (bytes, bytearray)) else cp.stdout
    return parse_test_summary(stdout)


def create_syscall_list(binaries, outfile, tool):
    data = []
    for b in binaries:
        p = create_program(tool, b)
        syscall_list = p.syscalls()
        print(f"[+] -----binary: {b} -----")
        print(f"[+] Syscalls: {syscall_list}")
        print(f"[+] Syscall count: {len(syscall_list)}")
        bin_name = os.path.basename(b)

        data.append({
            "binary": bin_name,
            "syscall_list": list(syscall_list)
        })

    pkg_utils.export_json(outfile, data)
    return data


def main():
    parser = argparse.ArgumentParser(
        description="Analyze, instrument, and test a package with SECCOMP filters."
    )

    parser.add_argument("policy_gen_tool",
        nargs="?", default="angr",
        choices=["angr", "ghidra", "safer", "ida", "bninja", "safer_reloc", "safer_split_escape", "safer_argmatch", "safer_enhanced", "safer_sysfilter", "gt"],
        help="Analysis tool to use for policy generation (or 'gt' for ground truth)"
    )
    pkg_utils.add_common_args(parser)
    parser.add_argument("instrumentation_tool",
        nargs="?", default="safer",
        choices=["safer"],
        help="Tool used for binary instrumentation"
    )

    args = parser.parse_args()
    print(args)

    testsuite_dir = config.TESTSUITE_DIR
    binaries_dir = os.path.join(config.BINARIES_DIR, args.optimization, args.config)

    data_path = os.path.join(testsuite_dir, "testdata", args.policy_gen_tool)
    os.makedirs(data_path, exist_ok=True)

    pkg = args.pkg
    pkg_path = os.path.join(binaries_dir, pkg)
    binaries = pkg_utils.list_executables(pkg_path)

    outfile = os.path.join(data_path, f"{pkg}_{args.config}_{args.optimization}.json")
    if args.policy_gen_tool == "gt":
        outfile = os.path.join(data_path, f"{pkg}.json")

    data = []
    if os.path.exists(outfile):
        with open(outfile, "r") as f:
            data = json.load(f)
    else:
        if args.policy_gen_tool == "gt":
            print(f"[!] ground truth syscall data for {pkg} does not exist")
            for b in binaries:
                exename = os.path.basename(b)
                data.append({"binary": exename, "syscall_list": []})
        else:
            data = create_syscall_list(binaries, outfile, args.policy_gen_tool)

    inst_tool = None
    if args.instrumentation_tool == "safer":
        inst_tool = Safer()
    else:
        print(f"[!] {args.instrumentation_tool} is not supported for instrumentation")
        sys.exit(1)

    inst_dir = os.path.join(pkg_path, args.policy_gen_tool + ".instrumented")
    os.makedirs(inst_dir, exist_ok=True)

    for b in binaries:
        exename = os.path.basename(b)
        syscall_list_found = False
        for d in data:
            if d["binary"] == exename:
                syscall_list_found = True
                inst_bin = inst_tool.instrument(b, d["syscall_list"])
                final_inst_bin = os.path.join(inst_dir, exename)
                subprocess.run(["mv", inst_bin, final_inst_bin], capture_output=True, check=True)

        if not syscall_list_found:
            print(f"[!] syscall list not found for {pkg} -- {exename}. Using the original binary for testing")
            final_inst_bin = os.path.join(inst_dir, exename)
            subprocess.run(["cp", b, final_inst_bin], capture_output=True, check=True)

    cmd = [
        os.path.join(config.TESTSUITE_DIR, "test.sh"),
        pkg,
        inst_dir
    ]
    result = subprocess.run(cmd, capture_output=True, check=True)
    summary = parse_from_completed_process(result)
    print(summary)


if __name__ == "__main__":
    main()
