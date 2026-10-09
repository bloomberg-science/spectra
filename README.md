# SPECTRA: Syscall Policy Extraction with Configurable Tool Refinement and Analysis

**S**yscall **P**olicy **E**xtraction with **C**onfigurable **T**ool **R**efinement and **A**nalysis (SPECTRA) is a framework for binary analysis, call graph generation, and system call extraction. It supports multiple analysis backends, automatic dependency resolution, and binary hardening with SECCOMP filters.

**Artifact Evaluation:** For ISSTA 2026 artifact evaluation, please refer to [ARTIFACT_EVALUATION.md](ARTIFACT_EVALUATION.md) for Docker-based setup and step-by-step reproduction instructions.

## Quick Start

```bash
# Install everything (requires sudo for system deps)
./install.sh

# Activate the environment
source analysisenv/bin/activate

# Analyze a binary
python3 gen_syscall.py safer /bin/ls

# Analyze a package
python3 gen_pkg_syscalls.py safer O2 stripped nginx
```

## Supported Analysis Tools

| Tool | Backend | Setup |
|------|---------|-------|
| `safer` | SAFER baseline | `./install.sh` (auto) |
| `safer_enhanced` | SAFER + constant propagation, signature/type matching | `./install.sh` (auto) |
| `safer_reloc` | SAFER with relocation support | `./install.sh` (auto) |
| `safer_sysfilter` | Sysfilter call graph on SAFER | `./install.sh` (auto) |
| `angr` | Angr symbolic execution | `./install.sh` (auto) |
| `ghidra` | NSA Ghidra | `./install.sh` (auto) |
| `ida` | IDA Pro | Manual — set `IDA_PATH` |
| `bninja` | Binary Ninja | Manual — set `BNINJA_PATH` |

## Core Scripts

### `gen_syscall.py` — Analyze a single binary

```bash
python3 gen_syscall.py <tool> <binary_path> [-v]
```

Extracts all syscalls reachable from a binary and its shared library dependencies.

### `gen_pkg_syscalls.py` — Analyze all binaries in a package

```bash
python3 gen_pkg_syscalls.py <tool> <optimization> <config> <pkg> [-v]
```

Arguments:
- `optimization`: O0, O1, O2, O3, Ofast, Os
- `config`: fulldbg, symonly, stripped
- `pkg`: nginx, apache, lighttpd, proftpd, memcached, redis, bind, bmq, comdb2, mysql, postgresql

Output: JSON file in `testsuite/testdata/<tool>/`

### `instrument_and_test_pkg.py` — Apply SECCOMP filter and test

```bash
python3 instrument_and_test_pkg.py <policy_tool> <optimization> <config> <pkg> [instrumentation_tool] [-v]
```

Generates syscall policy, instruments binaries, and runs the package test suite.

### `compare_with_gt.py` — Compare against ground truth

```bash
python3 compare_with_gt.py <tool> <pkg> [OS] [optimization] [config]
```

### `harden.py` — Harden a single binary

```bash
python3 harden.py <tool> <binary_path>
```

Outputs hardened binary to `./hardened_binaries/`

### `handle_dyn_load.py` — Analyze dynamic loading

```bash
python3 handle_dyn_load.py <tool> <pkg> [optimization] [config]
```

Finds the modules of a package that call `dlopen`, `dlsym` or `execve`-family functions and
writes SAFER-instrumented copies of them to `testsuite/testlibs/<pkg>/` (the originals are kept
next to them as `<name>.orig`). The instrumented copies log every call argument to
`/tmp/safer_profile_data/{dlopen,dlsym,execve}`.

### Regenerating the dynamic-loading ground truth (`testsuite/testdata/libsdata/`)

`testsuite/testdata/libsdata/<pkg>/{dlopen,dlsym,execve}` lists the libraries, symbols and
executables that each package loads or executes at run time; it is used as ground truth when
inferring syscalls. The repository ships these files, so regenerating them is optional. To
regenerate them for a package (example: `apache`):

```bash
# 1. Build the package and collect its binaries (done by the Docker build)
cd testsuite && ./build_all.sh no apache && ./collect_binary.sh && cd ..

# 2. Create instrumented copies of the modules that call dlopen/dlsym/execve
python3 handle_dyn_load.py safer apache O2 stripped

# 3. Start from empty logs (the instrumentation appends to these files)
rm -rf /tmp/safer_profile_data && mkdir -p /tmp/safer_profile_data

# 4. Run the package test suite with the instrumented copies in place of the originals:
#    executables are taken from the directory passed to test.sh; shared objects are loaded
#    from the package test prefix (e.g. testsuite/apache/test_install/modules/), so copy the
#    instrumented .so files from testsuite/testlibs/apache/ over the files of the same name there.
cd testsuite && ./test.sh apache <dir-with-instrumented-executables> && cd ..

# 5. Store the logs and normalize them
mkdir -p testsuite/testdata/libsdata/apache
cp /tmp/safer_profile_data/* testsuite/testdata/libsdata/apache/
python3 fix_libsdata.py
```

`fix_libsdata.py` deduplicates the entries, reduces logged `execve` command lines to their
executables, and resolves paths against the current checkout (the Docker build runs it
automatically). Before committing regenerated files, replace the absolute checkout prefix
with paths relative to `testsuite/` so they work on any machine.

## Flags and Environment Variables

| Flag / Variable | Effect |
|----------------|--------|
| `-v`, `--verbose` | Enable detailed logging (dependency resolution, call graph iterations, etc.) |
| `IDA_PATH` | Path to IDA Pro `idat` binary (default: `idat` on `PATH`) |
| `BNINJA_PATH` | Binary Ninja install directory; its `python/` subdirectory is added to `sys.path` (default: `~/binaryninja`) |
| `GHIDRA_PATH` | Path to Ghidra `analyzeHeadless` |
| `BA_LOG_LEVEL` | Logging level: DEBUG, INFO, WARNING (default: WARNING) |
| `BINARY_ANALYSIS_TMP` | Temp directory for tool workspaces (default: system tmp) |

## Architecture

```
SPECTRA/
├── install.sh              # One-command setup
├── config.py               # Central configuration (paths, tool settings)
├── errors.py               # Logging, exceptions, progress bar
├── syscall_table.py        # Syscall number → name mapping (x86-64)
├── pkg_utils.py            # Shared utilities for package scripts
├── analysistool.py         # ABC base class + tool registry
├── gen_syscall.py          # Main entry: single-binary analysis
├── gen_pkg_syscalls.py     # Package-level analysis
├── instrument_and_test_pkg.py  # Instrumentation + testing
├── compare_with_gt.py      # Ground truth comparison
├── harden.py               # Binary hardening
├── handle_dyn_load.py      # Dynamic loading analysis
├── safer.py                # All SAFER variants (SaferBase + 4 subclasses)
├── angrext.py              # Angr backend
├── ghidra.py               # Ghidra backend
├── ida.py                  # IDA backend
├── bninja.py               # Binary Ninja backend
├── graph/                  # Core data model + analysis
│   ├── __init__.py         # Re-exports (backward compat)
│   ├── models.py           # CallSite, Function, Module, etc.
│   ├── program.py          # Program class (call graph, syscall extraction)
│   └── utils.py            # Helpers
├── bin_analysis_tools/     # backend tool sources
│   ├── safer/              # SAFER source + install.sh
│   ├── ghidra_projects/    # Ghidra install + scripts
│   ├── angr/               # Angr integration
│   ├── ida/                # IDA scripts
│   └── binary_ninja/       # Binary Ninja integration
├── testsuite/              # Test packages, build/test scripts
│   ├── build.sh / build_all.sh
│   ├── test.sh / test_all.sh
│   ├── buildscripts/       # Per-package build scripts
│   ├── testscripts/        # Per-package test scripts
│   └── testdata/           # Results, ground truth, caches
└── requirements.txt        # Python dependencies
```

### Key Design Patterns

**Tool Registry:** Each backend registers itself via `@register_tool("name")` decorator. Adding a new tool requires only a class + decorator, not changes to `gen_syscall.py`.

**SAFER Variants:** Single `SaferBase` class with a `SAFER_VARIANTS` config dict. Four thin subclasses for registration. All share init/invoke/instrument logic.

**Configuration:** All paths resolve from `config.BASE_DIR` (the directory containing `config.py`). No hardcoded absolute paths in tool code.

**Logging:** Off by default. Progress bars always show. Use `-v` for detailed output. Exceptions (`ToolExecutionError`, `BinaryAnalysisError`) replace `sys.exit()` in library code.


## License

SPECTRA is released under the [MIT License](LICENSE).

Third-party components keep their own licenses and are not covered by the MIT License:
the git submodules under `testsuite/` (the evaluation packages, e.g. MySQL and ProFTPD
under GPL-2.0, BIND under MPL-2.0, Redis under RSALv2/SSPLv1/AGPLv3), the SAFER submodule
under `bin_analysis_tools/safer` (Apache-2.0), and the Python dependencies installed from
`requirements.txt` (e.g. pyvex, BSD-2-Clause AND GPL-2.0-only). The repository does not
bundle third-party binaries; the evaluation packages are built from source.
