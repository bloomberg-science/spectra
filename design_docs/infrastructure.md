# Infrastructure Modules

## `config.py` — Configuration

Centralizes all path definitions. No other file contains hardcoded absolute paths.

| Constant | Purpose |
|----------|---------|
| `BASE_DIR` | Root of the BinaryAnalysis repo (auto-detected) |
| `TESTSUITE_DIR` | `<BASE_DIR>/testsuite` |
| `TESTDATA_DIR` | `<TESTSUITE_DIR>/testdata` |
| `CACHE_DIR` | `<TESTDATA_DIR>/external_libs` — per-tool JSON cache |
| `GT_DIR` | `<TESTDATA_DIR>/gt` — ground truth data |
| `BINARIES_DIR` | `<TESTSUITE_DIR>/subset_binaries/gcc` |
| `TMP_DIR` | Temp dir for tool workspaces (env: `BINARY_ANALYSIS_TMP`) |
| `TOOL_PATHS` | Dict of tool binary locations (env-overridable) |
| `LOADER_PATH` | Path to dynamic linker (default: `/lib64/ld-linux-x86-64.so.2`) |
| `PACKAGES` | List of supported package names |

## `errors.py` — Logging, Exceptions, Progress

**Logging:**
- Default level: WARNING (quiet — only errors and progress bars)
- Enable verbose: `-v` flag or `BA_LOG_LEVEL=INFO`
- Logger: `errors.logger` (named "binaryanalysis")
- Output: stderr (doesn't interfere with piped stdout)
- `set_verbose(True/False)` — programmatic control

**Exceptions:**
```
BinaryAnalysisError         — base exception
├── ToolExecutionError      — tool failed to run or produced invalid output
├── DependencyNotFoundError — shared library not found
└── ConfigurationError      — invalid config or missing paths
```

Tools raise exceptions; top-level scripts catch and handle.

**ProgressBar:**
- Lightweight, no external dependencies (no tqdm)
- Writes to stderr, always visible regardless of log level
- Shows: description, bar, count, ETA, current item name
- Usage: `ProgressBar(total, desc="...").update(item_name)` + `.finish()`

## `pkg_utils.py` — Package Script Utilities

Shared functions extracted from `gen_pkg_syscalls.py` and `instrument_and_test_pkg.py`:

| Function | Purpose |
|----------|---------|
| `is_elf_file(path)` | Check ELF magic bytes |
| `is_executable(path)` | Check ET_EXEC or PIE (not .so) |
| `list_executables(dir)` | List all executable ELFs in a directory |
| `export_json(path, data)` | Write JSON with indent |
| `resolve_paths(args)` | Resolve binaries_dir, data_path from parsed CLI args |
| `add_common_args(parser)` | Add optimization/config/pkg args to argparse |
| `add_os_arg(parser)` | Add OS choice arg |
| `load_gt_libs(dir, pkg)` | Load dlopen/execve/dlsym ground truth |
| `load_gt_syscalls(dir, pkg)` | Load ground truth syscall JSON |
| `get_binary_gt_syscalls(gt, name)` | Look up GT syscalls for one binary |

## `syscall_table.py` — Syscall Name Resolution

Maps x86-64 Linux syscall numbers to human-readable names.

| Function | Purpose |
|----------|---------|
| `syscall_name(num)` | Single number → name (e.g., `0` → `"read"`) |
| `format_syscall_list(nums)` | Set/list of numbers → sorted list of names |

Used only for display output. JSON storage keeps raw numbers.

## Caching Strategy

Per-tool, per-run-id JSON cache in `<CACHE_DIR>/<tool>/<run_id>/<binary>.json`:
- `extract()` checks cache before calling `invoke()`
- Cache hit: deserialize from JSON (fast)
- Cache miss: run tool, serialize result to JSON
- Main binary is never cached (always re-analyzed)
- Libraries are cached (avoid re-analyzing libc.so for every binary)

## Testsuite Structure

```
testsuite/
├── build.sh            — Build one package (optional coverage flag)
├── build_all.sh        — Build all/subset packages
├── test.sh             — Run tests for one package
├── test_all.sh         — Run tests for all packages
├── buildscripts/       — Per-package build scripts (12 packages)
│   └── <pkg>/build.sh
├── testscripts/        — Per-package test scripts
│   └── <pkg>/test.sh
├── binaries/gcc/       — Standard builds: <opt>/<config>/<pkg>/
├── subset_binaries/gcc/ — Subset for evaluation: <opt>/<config>/<pkg>/
├── gcc-coverage/       — Coverage-instrumented builds
└── testdata/
    ├── <tool>/         — Analysis results JSON
    ├── gt/             — Ground truth syscall lists
    ├── libsdata/       — dlopen/dlsym/execve metadata
    └── external_libs/  — Cached per-library analysis results
```
