# Architecture Overview

## System Purpose

BinaryAnalysis extracts the set of system calls reachable from a given binary by:
1. Resolving all shared library dependencies (transitive)
2. Running a binary analysis backend to extract per-function call graphs
3. Building a whole-program call graph (direct calls + PLT resolution + indirect call resolution)
4. Traversing the call graph from entry points to collect reachable syscalls

The extracted syscall set can then be used to generate SECCOMP filters that restrict the binary to only those syscalls at runtime.

## High-Level Data Flow

```
Binary (/bin/ls)
    │
    ▼
┌─────────────────────┐
│ Dependency Resolution│  ldd + transitive BFS
│  (gen_syscall.py)    │
└─────────┬───────────┘
          │  List of .so paths
          ▼
┌─────────────────────┐
│  Tool Backend        │  SAFER / Angr / Ghidra / IDA / BNinja
│  (safer.py, etc.)    │
│                      │  Per-module: functions, call sites, AT flags,
│                      │  PLT targets, indirect CF expressions
└─────────┬───────────┘
          │  Module objects (one per .so / binary)
          ▼
┌─────────────────────┐
│  Program Assembly    │  Combines all modules
│  (graph/program.py)  │  Resolves cross-module PLT calls
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Call Graph Build    │  Iterative fixpoint:
│  (build_call_graph)  │    1. Traverse direct call graph (DCG)
│                      │    2. Resolve indirect calls (AT linking)
│                      │    3. Repeat until no new edges
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Syscall Collection  │  BFS from entry points
│  (syscalls())        │  Collect fn.syscall_list for all reachable fns
└─────────┬───────────┘
          │
          ▼
    Set of syscall numbers
```

## Module Dependency Graph

```
gen_syscall.py / gen_pkg_syscalls.py
    │
    ├── analysistool.py (tool registry, ABC, caching)
    │       │
    │       ├── safer.py (SaferBase + 4 variants)
    │       ├── angrext.py
    │       ├── ghidra.py
    │       ├── ida.py
    │       └── bninja.py
    │
    ├── graph/
    │       ├── models.py (CallSite, Function, Module)
    │       ├── program.py (Program: call graph + syscall extraction)
    │       └── utils.py
    │
    ├── config.py (paths, tool locations)
    ├── errors.py (logging, exceptions, progress bar)
    ├── pkg_utils.py (shared package utilities)
    └── syscall_table.py (number → name mapping)
```

## Entry Points

| Script | Purpose | Output |
|--------|---------|--------|
| `gen_syscall.py` | Analyze one binary | Syscall list (stdout) |
| `gen_pkg_syscalls.py` | Analyze all binaries in a package | JSON file |
| `instrument_and_test_pkg.py` | Apply SECCOMP + run tests | Test results |
| `harden.py` | Produce hardened binary | `./hardened_binaries/<name>_2` |
| `compare_with_gt.py` | Evaluate against ground truth | Missing syscalls report |
| `handle_dyn_load.py` | Find dlopen/dlsym/execve usage | Library sets |
