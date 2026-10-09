# Data Model — `graph/models.py`

## Class Hierarchy

```
CallSite        — A single call instruction within a function
Function        — A function with its call sites, syscalls, and metadata
Module          — A loaded ELF binary/library with its function map
Program         — Collection of modules forming the whole-program view
Callee          — (addr, module_path) pair for unresolved call targets
IndCFExpr       — Indirect control flow expression (register + access type)
MemRange        — Virtual address range (start, end)
```

## CallSite

Represents a single call instruction at a specific address.

| Field | Type | Description |
|-------|------|-------------|
| `site` | int | Address of the call instruction |
| `fn_addr` | int | Address of the containing function |
| `expects_ret` | bool | Whether the caller uses the return value |
| `targets` | list[int] | Statically resolved call target addresses |
| `plt_target` | str | PLT symbol name (if this is a PLT call) |
| `unresolved_icf` | bool | True if this is an unresolved indirect call |
| `args_reg_state` | dict | Register state at call site (rdi, rsi, ...) |
| `ind_cf_expr` | IndCFExpr | Expression driving the indirect call |
| `link_at` | bool | Whether to link all address-taken functions here |
| `resolved_targets` | list[Function] | Functions resolved as targets |
| `unprocessed_targets` | list[Callee] | Targets awaiting resolution |
| `args_passed_cnt` | int | Number of arguments being passed (-1 = unknown) |

## Function

Represents a single function within a module.

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Symbol name |
| `addr` | int | Entry point address |
| `syscall_list` | list[int] | Direct syscalls made by this function |
| `address_taken` | bool | Whether the function's address is taken |
| `call_site_list` | list[CallSite] | All call sites within this function |
| `args_use` | dict | Register usage: "R"(read), "W"(write), "U"(unused) |
| `at_set` | list[int] | Addresses of functions referenced in this function's body |
| `parent_fns` | set[Function] | Functions that call this one |
| `child_fns` | set[Function] | Functions called by this one |
| `main` | bool | True if this is an entry point |
| `processed` | bool | BFS visited flag |
| `returns_val` | bool | Whether the function returns a value |

## Module

Represents one loaded ELF binary or shared library.

| Field | Type | Description |
|-------|------|-------------|
| `module_path` | str | Filesystem path to the ELF file |
| `function_map` | dict[int, Function] | addr → Function mapping |
| `symbol_map` | dict[str, int] | symbol name → address (from .dynsym + .symtab) |
| `deps` | set[str] | Paths of dependencies |
| `main` | bool | True if this is the primary executable |
| `at` | list[Function] | All address-taken functions in this module |
| `rx_segment` | MemRange | Executable memory range |
| `rw_segment` | MemRange | Writable memory range |
| `ro_segment` | MemRange | Read-only memory range |

**On construction:** Module reads the ELF file to populate `symbol_map` (from `.dynsym` and `.symtab`) and segment memory ranges.

## Program

The whole-program container. Owns all modules and performs cross-module analysis.

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Binary name |
| `module_list` | list[Module] | All loaded modules |
| `fn_set` | set[Function] | All reachable functions discovered |
| `edges` | int | Total call graph edges |
| `enhancements` | bool | Enable enhanced analysis |
| `const_prop` | bool | Enable constant propagation for ICF resolution |
| `context` | bool | Enable context-sensitive address-taken |
| `sig_match` | bool | Enable signature-based filtering |
| `type_match` | bool | Enable type-based filtering |
| `gt_syscall_list` | set | Ground truth syscalls (for evaluation) |
| `dlsym_fns` | set[str] | Functions loaded via dlsym |

## JSON Serialization

Each Module can export to JSON via `export_to_json()`. Format:

```json
[
  {"module": "/path/to/binary"},
  {
    "name": "main",
    "address": 4194304,
    "address_taken": false,
    "return_val": true,
    "main": true,
    "args_use": {"rdi": "R", "rsi": "R", ...},
    "syscall": [1, 59, 231],
    "at_list": [4194560, 4194688],
    "call_sites": [
      {
        "site": 4194320,
        "args": {"rdi": "0x401000", ...},
        "expects_ret": true,
        "targets": [4194560],
        "plt_target": null,
        "unresolved_icf": false,
        "icf_details": []
      }
    ]
  }
]
```
