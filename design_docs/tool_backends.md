# Tool Backends

## Registration System

All tool backends register via the `@register_tool` decorator in `analysistool.py`:

```python
@register_tool("tool_name", prog_flags={"enhancements": True})
class MyTool(AnalysisTool):
    def invoke(self, binary_path, main) -> Module:
        ...
```

The registry maps tool names to classes and associated Program flags. `gen_syscall.py` imports all tool modules at startup so decorators execute.

## AnalysisTool ABC (`analysistool.py`)

Base class providing:
- **`invoke(bin_path, main) → Module`**: Abstract method. Runs the backend tool on a single binary and returns a populated Module.
- **`extract(bin_path, main) → Module`**: Caching wrapper around `invoke()`. For non-main modules, checks JSON cache first. Cache stored at `<CACHE_DIR>/<tool_name>/<run_id>/<binary_name>.json`.
- **`json_to_function(json_fn, module_path) → Function`**: Deserializes a function from cached JSON back into a Function object with its CallSites.

## SAFER (`safer.py`)

**All 4 variants in one file** via `SaferBase`:

| Variant | Source Dir | Has Instrument | Prog Flags |
|---------|-----------|----------------|------------|
| `safer` | `safer_default` | Yes | (none) |
| `safer_enhanced` | `syscallpolicy` | Yes | enhancements, context, const_prop, sig_match, type_match |
| `safer_reloc` | `safer_reloc` | Yes | (none) |
| `safer_sysfilter` | `sysfilter` | No | enhancements, context |

**How it works:**
1. `__init__`: Copies source directory to a run-specific working dir, runs `make -j16`
2. `invoke`: Runs the compiled `run` binary on the target, parses `callgraph.json` output
3. `instrument` (optional): Writes syscall CSV, runs instrumentation binary, outputs `<binary>_2`

**Output format:** Line-delimited JSON in `tmp/cfg/callgraph.json`

## Angr (`angrext.py`)

Calls `analyze_binary()` from `bin_analysis_tools/angr/extract_syscall.py`.
Returns structured data with function names, addresses, syscalls, call targets, PLT targets, and indirect CF info.

## Ghidra (`ghidra.py`)

Runs `analyzeHeadless` with a PostScript (`extract_syscall.py`) that exports `functions.json`.
Requires Java 17+ runtime.

## IDA (`ida.py`)

Copies binary to temp dir, runs IDA in batch mode (`-A -c -S<script>`).
Script produces `<binary>.json` with function/call info.
Requires commercial IDA Pro license.

## Binary Ninja (`bninja.py`)

Calls `get_bininfo()` from `bin_analysis_tools/binary_ninja/extract_syscall.py`.
Similar output format to angr.
Requires commercial Binary Ninja license + Python API.

## Adding a New Backend

1. Create `mytool.py`:
```python
from analysistool import AnalysisTool, register_tool
from graph import Module, Function, CallSite

@register_tool("mytool", prog_flags={})
class MyTool(AnalysisTool):
    def __init__(self, run_id="none"):
        super().__init__()
        self.name = "mytool"
        self.runid = run_id

    def invoke(self, binary_path, main) -> Module:
        mod = Module(binary_path)
        # ... run your tool, parse output, create Function objects ...
        mod.add_function(fn)
        mod.main = main
        return mod
```

2. Add `import mytool` to `gen_syscall.py` (tool imports section)

3. Done — `python3 gen_syscall.py mytool /bin/ls` works
