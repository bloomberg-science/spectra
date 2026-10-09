# Artifact Evaluation: Applying System Call Filtering to Real-World Binaries

## Artifact Description

This artifact accompanies the ISSTA 2026 experience paper "Applying System Call Filtering to Real-World Binaries." It provides SPECTRA (**S**yscall **P**olicy **E**xtraction with **C**onfigurable **T**ool **R**efinement and **A**nalysis), a modular framework for inferring system call sets from binaries using multiple off-the-shelf binary analysis tools (Ghidra, Angr, SAFER), along with control-flow refinement techniques (Sysfilter-style context-sensitive refinement, data-section splitting, escape analysis, function signature matching, and global constant propagation).

The artifact supports reproduction of all four research questions:

- Syscall counts across tools, optimization levels, and strip configurations (Table 1)
- Ground-truth comparison via seccomp-BPF enforcement (Table 2)
- Incremental impact of refinement techniques (Table 3, Table 4)

**Type:** Software artifact (framework + evaluation infrastructure)

**Delivery format:** We provide the source repository and a Dockerfile. Evaluators build the Docker image locally, which downloads all dependencies, compiles the evaluation packages, and produces a self-contained environment.

**Commercial tools:** Although the paper evaluates and our framework supports commercial tools (IDA Pro, Binary Ninja), we are unable to distribute them due to licensing restrictions. All experiments can be fully reproduced using the included open-source tools (Angr, Ghidra, SAFER).

**Host requirements:** x86-64 Linux with Docker installed. The built image is approximately 15 GB. A machine with at least 32 GB RAM, 100 GB free disk space, and a stable internet connection is recommended.

---

## Part I: Getting Started Guide (< 30 minutes)

### 1. Prerequisites

- Docker (version 20.10+)
- x86-64 Linux host (tested on Ubuntu 22.04 LTS)
- Stable internet connection (the build downloads packages and dependencies)
- At least 100 GB free disk space

### 2. Building the Docker Image

**Proxy configuration:** If building behind a corporate proxy, uncomment and update the proxy settings near the top of the `Dockerfile` before starting the build. Set `HTTP_PROXY`, `HTTPS_PROXY`, and `NO_PROXY` to appropriate values. If your proxy performs SSL interception, also uncomment the CA certificate lines and place your CA certificates in the `certs/` directory.

```bash
# Clone the repository together with all package submodules.
# (If already cloned without submodules, run: git submodule update --init --recursive)
git clone --recurse-submodules https://github.com/bloomberg-science/spectra.git
cd spectra

# Build the Docker image from the provided Dockerfile.
# Expected build time: approximately 9 hours for O0, O1 and O2 (about 3 hours per level;
# varies with network speed and CPU cores). The build downloads all dependencies,
# compiles 11 evaluation packages from source, and installs analysis tools.
docker build --network=host -t spectra .

# Faster alternative: build only O2 (sufficient for the default experiments)
docker build --network=host --build-arg OPT_LEVELS=O2 -t spectra .
```

The Dockerfile performs the following steps automatically:
1. Installs system dependencies (compilers, libraries, Python, Java)
2. Installs cmake 3.28 (required by BlazingMQ; Ubuntu 22.04 ships 3.22)
3. Copies the cloned SPECTRA repository (including package submodules) into the image
4. Runs `install.sh` (sets up Python venv, SAFER, Ghidra)
5. Builds all 11 evaluation packages from source at optimization levels O0, O1 and O2 (full debug and symbols-only), then collects the stripped, symbols-only and full-debug binaries into `testsuite/subset_binaries/gcc/`

The build takes around 9 hours to complete (about 3 hours with `OPT_LEVELS=O2`). If the build succeeds, the final output will show:
```
All builds completed successfully!
```

### 3. Starting the Container

```bash
docker run --cap-add=NET_ADMIN -dit spectra
docker exec -it <docker_id> /bin/bash
# To obtain docker_id do "docker ps -a" to get the ID of running docker container
```
### 4. Smoke Test

Inside the container, verify the framework is operational:

```bash
# Activate the Python environment
source /app/analysisenv/bin/activate

# Run a single-binary syscall inference with SAFER on /bin/ls
python3 gen_syscall.py safer_enhanced /bin/ls
```

**Expected output:** A list of inferred system call numbers printed to stdout, confirming that SAFER disassembly, function recovery, and syscall extraction all work correctly.

```bash
# Verify Ghidra backend
python3 gen_syscall.py ghidra /bin/ls

# Verify Angr backend
python3 gen_syscall.py angr /bin/ls
```
Each command should produce a syscall list.

### 5. Quick End-to-End Test (Single Package)

```bash
cd /app

# Run syscall inference on nginx using SAFER.
python3 gen_pkg_syscalls.py safer_enhanced O2 stripped nginx

This should complete in 15-20 minutes

# Compare with ground truth
python3 compare_with_gt.py safer_enhanced nginx O2 stripped
```
This will show the missing system calls -- the ones present in the groundtruth data but the analysis failed to infer.

---

## Part II: Step-by-Step Reproduction Instructions

### Experiment 1: Reproducing Table 1

Table 1 reports syscall counts across analysis tools, optimization levels (`O0`, `O1`, `O2`), and binary configurations (`stripped`, `fulldbg`, and `symonly`).

By default, the evaluation scripts run on a reduced subset of packages:

```text
nginx apache redis lighttpd memcached proftpd bind comdb2
```

The heavyweight packages, namely `mysql`, `postgresql`, and `bmq`, are excluded from the default evaluation list because they require substantially more resources. In our setup, these packages may require more than 30 GB of RAM and can take multiple hours to complete. `mysql` alone takes approximately 8 hours. These packages can still be evaluated separately by explicitly passing them to the script.

#### Running syscall inference

`run_all_pkgs.sh` accepts an analysis tool, an optional optimization level, an optional binary configuration, and an optional list of packages:

```text
Usage: ./run_all_pkgs.sh <tool> [opt] [config] [packages...]

  tool:     angr | ghidra | safer | safer_reloc | safer_enhanced | safer_sysfilter
  opt:      O0 | O1 | O2
            default: O2
  config:   stripped | fulldbg | symonly
            default: stripped
  packages: space-separated package list
            default: nginx apache redis lighttpd memcached proftpd bind comdb2
```

Example commands:

```bash
cd /app
source /app/analysisenv/bin/activate

# Stripped binaries at O2, using the default package subset
./run_all_pkgs.sh safer
./run_all_pkgs.sh ghidra
./run_all_pkgs.sh angr

# Full-debug binaries at O0
./run_all_pkgs.sh safer O0 fulldbg

# Explicitly run a specific subset of packages
./run_all_pkgs.sh safer O2 stripped nginx apache redis

# Run heavyweight packages separately, if sufficient resources are available
./run_all_pkgs.sh safer O2 stripped postgresql bmq
```

Other optimization levels and binary configurations can be evaluated by changing the `opt` and `config` arguments.

Results are written to:

```text
eval_results/<tool>_<opt>_<config>_<timestamp>/
```

Each result directory contains per-package logs and a `summary.csv` file.

#### SAFER with relocation support

The SAFER-R column can be reproduced using the `safer_reloc` tool option:

```bash
./run_all_pkgs.sh safer_reloc O2 stripped
```

#### Parallel execution guidance

Different analysis tools can be evaluated in parallel. For example, the following tool runs may be started concurrently:

```bash
./run_all_pkgs.sh safer O2 stripped
./run_all_pkgs.sh angr O2 stripped
./run_all_pkgs.sh ghidra O2 stripped
./run_all_pkgs.sh safer_reloc O2 stripped
```

However, we recommend evaluating different optimization levels and binary configurations sequentially to avoid excessive resource contention. For example, first evaluate `O2, stripped`, then proceed to `O2, fulldbg`, followed by the remaining configurations.

#### Estimated runtime

Reproducing Table 1 across all tools and configurations on the reduced default subset of 8 packages takes approximately **10–12 hours** in our setup.
Since, the results are mostly identical across all configurations, we recommend evaluating only the default configuration (`O2, stripped`). This will complete in 2-3 hours.

#### Expected variations

Some variation in the newly observed syscall counts is expected. We attribute these differences primarily to two factors: recent changes to the evaluation framework and differences in the execution environment, such as updates to third-party libraries.

For example, we recently added a best-effort mechanism for handling dynamically opened or dynamically executed modules. This change increased the number of inferred syscalls for Apache when using `safer_reloc` to 192. At the same time, it reduced the number of missed syscalls for Apache in Table 4 from 6 to 1.

For `bind`, we observed a minor reduction in the number of inferred syscalls when using `safer_reloc`, from 152 to 150. We manually verified that the inferred syscall list remains complete. Similarly, for `proftpd`, we observed a small increase in the number of inferred syscalls with `safer_reloc`, from 139 to 141. We attribute these minor differences to environmental changes.

---

### Experiment 2: Reproducing Table 2

Table 2 evaluates soundness by enforcing the inferred syscall filters at runtime using seccomp-BPF and then running each application's test suite.

Experiment 1 must be completed before running this experiment because Experiment 2 uses the syscall inference results generated in Experiment 1.

#### Ground truth

Pre-generated ground-truth syscall sets are provided as part of the artifact. These ground-truth sets were generated using the process described in Section 7.2.2 of the submitted paper.

#### Comparing against ground truth

The ground-truth data may be incomplete because it is generated by running application test suites, and these test suites may not cover all execution paths. This limitation is discussed in the submitted paper.

Therefore, we use the ground truth only to report false negatives, that is, syscalls that an analysis tool fails to infer. We do not report false positives because a syscall inferred by a tool but absent from the ground truth may still be valid on an execution path not covered by the test suite.

To compare inferred syscall sets against the provided ground truth, run:

```bash
cd /app

# Compare inferred syscalls against ground truth for a given tool and package
python3 compare_with_gt.py $tool $pkg
```

where:

```text
$tool = angr | ghidra | safer | safer_reloc | safer_enhanced | safer_sysfilter
$pkg  = target package, for example nginx, apache, redis, etc.
```

**Expected result:** The script prints the list of missing syscalls for the specified package and analysis tool. The missing syscall counts should match the corresponding counts reported in Table 2.

**Expected variations:** We see lighttpd and comdb2 missing 2 syscalls instead of one for safer_reloc analysis. We attribute these to environmental changes and we have verfied that these are definitely coming from missed dynamically opened/executed modules. For example, in case of lighttpd, both the missing syscalls are from perl.

#### Running test suites with seccomp enforcement

For each tool's inferred syscall set, the framework instruments the target binary's `main` function to install a seccomp-BPF filter before execution. It then runs the application's test suite under the enforced syscall policy.

The test results from the instrumented binary are compared against the results from the default, uninstrumented binary.

First, run the test suite on the standard uninstrumented binary:

```bash
cd /app/testsuite

# Run the test suite for a standard, uninstrumented binary
./test.sh $pkg $binary_path

# Example:
./test.sh nginx /app/testsuite/subset_binaries/gcc/O2/stripped/nginx
```

Then, run the test suite on the instrumented binary:

```bash
cd /app

# Instrument the binary using the inferred syscall set and run the test suite
python instrument_and_test_pkg.py $analysis_tool_used $opt $conf $pkg
```

where:

```text
$analysis_tool_used = tool used to infer syscalls for the target package in Experiment 1
$opt                = O0 | O1 | O2
$conf               = stripped | fulldbg
$pkg                = target package, for example nginx, apache, redis, etc.
```

Because syscall inference results do not vary across binary configurations in our evaluation, we recommend running this experiment for a single representative configuration, such as `O2, stripped`.

#### Expected results

For packages with zero missing syscalls, the test pass/fail counts should match between the standard uninstrumented binary and the instrumented binary.

For packages with one or more missing syscalls, the pass/fail counts for the instrumented binary may differ from the uninstrumented run. This is expected because the seccomp-BPF filter blocks syscalls that were not inferred by the analysis tool.

In Table 2 of the paper, entries marked with `*` indicate cases where the missing syscalls are due exclusively to unhandled dynamically loaded or dynamically executed modules. We manually verified these cases. Therefore, these entries are reported as `100%*`.

---

### Experiment 3: Reproducing Table 3

Table 3 shows the cumulative impact of control-flow refinement techniques on syscall counts and average indirect call-flow targets (AICT). Each column adds one technique on top of all preceding ones.

All of the below variations are implemented using SAFER. 
**Please test each of the variation one after another. Due to concurrency issues arising in SAFER, we recommend not to run all the variations in parallel.**

Each column maps to a dedicated tool variant:

| Table 3 Column | Tool variant | Refinements active |
|---|---|---|
| Sysfilter | `safer_sysfilter` | Context-sensitive AT-set refinement (see note below) |
| + Split+Escape | `safer_split_escape` | + data-section splitting + escape analysis |
| + ArgCnt+ArgType | `safer_argmatch` | + argument count, return-value, and type matching |
| + ConstProp | `safer_enhanced` | + inter-procedural constant propagation |

**Note on Sysfilter:** The `safer_sysfilter` tool variant is our reimplementation of the Sysfilter algorithm on top of the SAFER disassembly backend. We replicated the exact algorithm described in the Sysfilter paper. Since the original Sysfilter tool has strict platform dependencies (Ubuntu 18.04) and is not compatible with our evaluation environment, we did not use it directly.

Both syscall counts (Sys) and AICT are reported per binary and averaged per package. Each tool variant prints `AICT: X.XX` per binary and the runner records `avg_aict` in the summary CSV.

```bash
cd /app
source /app/analysisenv/bin/activate

# Run all four refinement stages for all packages
for tool in safer_sysfilter safer_split_escape safer_argmatch safer_enhanced; do
  ./run_all_pkgs.sh $tool O2 stripped
done
```

Results land in `eval_results/<tool>_O2_stripped_<timestamp>/summary.csv` with columns `total_syscalls` and `avg_aict` for each package.

To view per-binary syscall counts and AICT for a specific stage:

```bash
python3 extract_eval_data.py safer_sysfilter nginx O2 stripped
python3 extract_eval_data.py safer_split_escape nginx O2 stripped
python3 extract_eval_data.py safer_argmatch nginx O2 stripped
python3 extract_eval_data.py safer_enhanced nginx O2 stripped
```

**Expected:** Syscall counts and AICT values matching Table 3.

#### Expected variations

Here also we observe variations due to reasons mentioned before. Apache sees increase in system call count due to our recent change for handling dynamically opened modules. Bind and proftpd also see slight variations due to library version differences.

**Estimated time:** ~5-6 hours for all four stages across all packages.

---

### Experiment 4: Reproducing Table 4

#### Table 4: Soundness of Sysfilter + all refinements

The steps mentioned before for Table 2 can be followed here as well. Example below:

```bash
cd /app/testsuite

# Run the test suite for a standard, uninstrumented binary
./test.sh $pkg $binary_path

# Example:
./test.sh nginx /app/testsuite/subset_binaries/gcc/O2/stripped/nginx
```

Then, run the test suite on the instrumented binary:

```bash
cd /app

# Instrument the binary using the inferred syscall set and run the test suite
python instrument_and_test_pkg.py $analysis_tool_used $opt $conf $pkg
```
```text
$analysis_tool_used = safer_sysfilter/safer_enhanced
$opt                = O0 | O1 | O2
$conf               = stripped | fulldbg
$pkg                = target package, for example nginx, apache, redis, etc.
```

#### Expected results
Here also, we expect to see similar results and variations as mentioned for table 2.

---

### Additional Experiments

#### Running on custom binaries

The framework supports analyzing arbitrary ELF binaries:

```bash
source /app/analysisenv/bin/activate

# Analyze a single binary
python3 gen_syscall.py safer /path/to/binary

# Analyze with a specific tool
python3 gen_syscall.py ghidra /path/to/binary
python3 gen_syscall.py angr /path/to/binary
```

#### Hardening a binary

`harden.py` provides an end-to-end workflow for hardening a binary: it infers the syscall policy using a specified analysis tool, then instruments the binary with a seccomp-BPF filter that enforces the inferred policy at runtime.

```bash
source /app/analysisenv/bin/activate

# Harden a binary using SAFER with all refinements for policy generation
python3 harden.py safer_enhanced /path/to/binary

# Harden using Angr for policy generation
python3 harden.py angr /path/to/binary
```

The hardened binary is written to `/app/hardened_binaries/`. When executed, it installs the seccomp-BPF filter before entering `main`, blocking any syscall not in the inferred set.

#### Available analysis tools

| Tool ID | Description |
|---------|-------------|
| `safer` | SAFER (baseline heuristic AT identification) |
| `safer_reloc` | SAFER with relocation-based AT filtering |
| `safer_sysfilter` | SAFER with Sysfilter-style context-sensitive refinement |
| `safer_enhanced` | SAFER with all refinements (split + escape + signature + constprop) |
| `ghidra` | Ghidra headless analysis |
| `angr` | angr symbolic execution framework |
| `ida` | IDA Pro (requires license; set `IDA_PATH`) |
| `bninja` | Binary Ninja (requires license; set `BNINJA_PATH`) |

#### Framework code layout

```
/app/
├── gen_syscall.py            # Core: single-binary syscall inference
├── gen_pkg_syscalls.py       # Package-level analysis (all binaries in a package)
├── run_all_pkgs.sh           # Batch runner for all packages with a given tool
├── compare_with_gt.py        # Compare inferred syscalls against ground truth
├── extract_eval_data.py      # Display evaluation results as tables
├── config.py                 # Centralized path configuration
├── pkg_utils.py              # Shared utilities (ELF parsing, path resolution)
├── errors.py                 # Logging and progress bar
├── syscall_table.py          # Syscall number-to-name mapping
├── graph/                    # Call graph data model
│   ├── models.py             # Function, Module, Program classes
│   ├── program.py            # Global call graph construction + syscall set generation
│   └── utils.py              # Graph utilities
├── analysistool.py           # Tool registry (@register_tool decorator)
├── safer.py                  # SAFER backend (+ reloc, sysfilter, enhanced variants)
├── angrext.py                # Angr backend
├── ghidra.py                 # Ghidra backend
├── ida.py                    # IDA Pro backend
├── bninja.py                 # Binary Ninja backend
├── bin_analysis_tools/       # Tool installation scripts and helpers
│   ├── safer/                # SAFER source (git submodule)
│   ├── ghidra_projects/      # Ghidra scripts + installer
│   └── angr/, ida/           # Backend-specific scripts
├── testsuite/                # Evaluation infrastructure
│   ├── buildscripts/         # Per-package build scripts
│   ├── testscripts/          # Per-package test scripts
│   ├── testdata/gt/          # Ground-truth syscall sets
│   ├── testdata/libsdata/    # Dynamic loader metadata (dlopen/dlsym/execve)
│   ├── build_all.sh          # Build all packages
│   ├── test_all.sh           # Run all test suites
│   └── collect_binary.sh     # Extract ELF binaries from build trees
└── design_docs/              # Architecture and algorithm documentation
```
