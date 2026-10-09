# Call Graph Construction Algorithm

## Overview

The call graph is built iteratively. Each iteration discovers new edges (direct calls, PLT resolutions, indirect call targets). The fixpoint terminates when no new edges are added.

## Algorithm: `Program.build_call_graph(fn_list)`

```
Input:  fn_list — initial entry points (main, address-taken fns, loader entries)
Output: self.fn_set — all reachable functions with resolved call edges

1. populate_args_usage()        — compute per-function arg register usage counts
2. REPEAT:
     a. traverse_dcg(fn_list)   — BFS from fn_list, resolve direct calls + PLT
     b. resolve_ind()           — for all known fns, resolve indirect calls
     c. fn_list = newly discovered functions
   UNTIL no new edges added
3. link_left_over_icfs()        — final pass for any remaining unresolved ICFs
```

## Phase 1: Direct Call Graph Traversal (`traverse_dcg`)

BFS from entry points. For each function:
1. `populate_call_edges_fn(fn)` — resolve all call sites:
   - **Direct targets**: look up target address in the target module's function_map
   - **PLT calls**: resolve symbol name across all modules via `resolve_plt_call()`
   - **Indirect calls** (if `link_at` is set): link to address-taken functions

2. Add newly discovered callee functions to the BFS queue

## Phase 2: Indirect Call Resolution (`resolve_ind`)

For each function already in `fn_set`:
1. `const_prop_ind_cf_resolution(fn)` — attempt to resolve indirect calls via constant propagation:
   - If the ICF expression is a register, trace its value back through parent call sites
   - If a concrete address is found, add it as a resolved target
   - If value is "unknown", fall back to linking all address-taken functions (`link_at = True`)

2. `link_at_to_ind(fn)` — for unresolved ICFs marked `link_at`:
   - Populate argument passing info (for signature matching)
   - Mark the call site for AT linking in the next `populate_call_edges_fn` pass

3. `populate_call_edges_fn(fn)` — re-run edge resolution (picks up new AT links)

4. Return any child functions not yet in `fn_set` as `new_fn_set`

## Phase 3: Fixpoint

The loop terminates when `self.edges == self.prev_edges` — no new call graph edges were added in the last iteration. Typically converges in 3-8 iterations.

## Indirect Call Resolution Strategies

The framework supports progressive refinement of indirect call targets:

| Strategy | Flag | Effect |
|----------|------|--------|
| **Baseline** | (default) | Link ALL address-taken functions to every indirect call site |
| **Context-sensitive AT** | `context=True` | Only link AT functions visible in the current calling context |
| **Constant propagation** | `const_prop=True` | Trace register values through parents to resolve targets |
| **Signature matching** | `sig_match=True` | Filter AT functions by argument count match |
| **Type matching** | `type_match=True` | Filter AT functions by argument type (pointer vs integer) |

These are enabled via `prog_flags` in the tool registration:
- `safer` → all disabled (baseline)
- `safer_sysfilter` → enhancements + context
- `safer_enhanced` → all enabled

## Syscall Collection (`Program.syscalls()`)

After the call graph is built:
1. Determine entry points: `main()` functions + address-taken fns + loader entries
2. BFS from entry points over the resolved call graph
3. For each reachable function, add `fn.syscall_list` to the result set
4. Return the union of all syscall numbers

## Key Invariants

- A function appears in exactly one Module
- `fn.child_fns` / `fn.parent_fns` reflect resolved edges only
- `fn.processed` is a BFS visited flag, reset between passes via `Program.reset()`
- PLT resolution is cross-module: symbol lookup traverses all loaded modules
- The loader module (`ld-linux-x86-64.so.2`) entry points are added to root fn_list
