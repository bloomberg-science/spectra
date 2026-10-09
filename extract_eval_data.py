# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import json
import argparse
import pandas as pd
import os
import config

#packages = ["apache", "bind", "bmq"]
packages = ["bind", "bmq", "comdb2", "postgresql"]


def parse_filename(filename):
    base = os.path.basename(filename).replace(".json", "")
    parts = base.split("_")
    
    package = parts[0]
    stripped = "yes" if "stripped" in parts else "no"
    
    opt_level = next((part for part in parts if part.startswith("O")), "unknown")
    
    return package, stripped, opt_level

def load_syscall_table(json_path):
    package, stripped, opt_level = parse_filename(json_path)

    with open(json_path, 'r') as f:
        data = json.load(f)

    rows = []
    for entry in data:
        binary = entry["binary"]
        syscalls = entry.get("syscall_list", [])
        if len(syscalls) == 1 and syscalls[0] == -1:
            syscall_count = "FAIL"
        else:
            syscall_count = len(syscalls)
        rows.append({
            "Package": package,
            "Binary": binary,
            "Opt Level": opt_level,
            "Stripped": stripped,
            "Syscall Count": syscall_count
            #"Syscall List": ', '.join(map(str, syscalls))
        })

    return rows#pd.DataFrame(rows)



def main():
    parser = argparse.ArgumentParser(description="Analyze a binary and its dependencies using the specified tool.")

    parser.add_argument("tool",
        nargs="?", default="gt",
        choices=["gt", "angr", "ghidra", "safer", "ida", "bninja", "safer_reloc", "safer_split_escape", "safer_argmatch", "safer_enhanced", "safer_sysfilter"],
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

    current_dir = config.BASE_DIR
    testsuite = os.path.join(config.BINARIES_DIR, args.optimization, args.config)
    data_path = os.path.join(config.TESTDATA_DIR, args.tool)
    os.makedirs(data_path, exist_ok=True)
    all_rows = []
    pkg = args.pkg
    #for pkg in packages:
    pkg_path = testsuite + "/" + pkg
    outfile = data_path + "/" + pkg + "_" + args.config + "_" + args.optimization + ".json"
    if args.tool == "gt":
        outfile = data_path + "/" + pkg + ".json"
    rows = load_syscall_table(outfile)
    all_rows.extend(rows)
    df = pd.DataFrame(all_rows)
    print(df.to_markdown(index=False))

if __name__ == "__main__":
    main()

