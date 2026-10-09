# Testing Guide - Automated Test Execution with Coverage

## Overview

The testsuite now includes automated test execution scripts that run tests for packages and automatically collect coverage data when testing coverage-instrumented builds.

---

## Available Scripts

### 1. `test.sh` - Single Package Testing

Runs tests for a single package.

**Usage:**
```bash
./test.sh <package> <binary_path>
```

**Example:**
```bash
./test.sh nginx /app/testsuite/gcc-coverage/O2/fulldbg/nginx/sbin
```

---

### 2. `test_all.sh` - Multi-Package Testing ⭐ NEW

Runs tests for all packages (or a specified subset).

**Usage:**
```bash
./test_all.sh [bin_base_path] [package1 package2 ...]
```

**Examples:**
```bash
# Test all packages (standard builds at O2/fulldbg)
./test_all.sh

# Test all packages (coverage builds at O2/fulldbg)
./test_all.sh gcc-coverage/O2/fulldbg

# Test specific packages (standard builds)
./test_all.sh gcc/O2/fulldbg nginx redis postgresql

# Test specific packages (coverage builds)
./test_all.sh gcc-coverage/O2/fulldbg nginx redis
```

---

## Complete Workflows

### Workflow 1: Test Standard Builds

```bash
cd /app/testsuite

# Build packages
./build_all.sh

# Test all packages
./test_all.sh gcc/O2/fulldbg
```

---

### Workflow 2: Test Coverage Builds (with Coverage Collection)

```bash
cd /app/testsuite

# Build packages with coverage
./build_all.sh coverage

# Test all packages (coverage auto-collected)
./test_all.sh gcc-coverage/O2/fulldbg
```

**Output:**
```
=========================================
TEST ALL PACKAGES
=========================================
Binary base path: /app/testsuite/gcc-coverage/O2/fulldbg
Packages to test: nginx apache redis postgresql memcached proftpd lighttpd bind comdb2 mysql
Total: 10 packages
=========================================

=========================================
Testing: nginx
=========================================
Running tests...
Passed:  150
Failed:  0
Skipped: 5

Coverage build detected! Collecting coverage data...
[Coverage collection...]

✅ SUCCESS: nginx tests passed

=========================================
Testing: redis
=========================================
...

=========================================
TEST SUMMARY
=========================================
Total time: 245 seconds

✅ Successful (10):
  - nginx
  - redis
  - postgresql
  ...

❌ Failed (0):
  (none)

=========================================
COVERAGE REPORTS GENERATED
=========================================

📊 nginx:
   HTML: /app/testsuite/nginx/coverage_20260325_143052/html/index.html
   Coverage: 78.5%

📊 redis:
   HTML: /app/testsuite/redis/coverage_20260325_143100/html/index.html
   Coverage: 82.3%

...

=========================================
✅ All tests passed successfully!
```

---

### Workflow 3: Test Specific Packages

```bash
# Build only what you need
./build_all.sh coverage nginx redis postgresql

# Test only those packages
./test_all.sh gcc-coverage/O2/fulldbg nginx redis postgresql
```

---

### Workflow 4: Test Different Optimization Levels

```bash
# Test O0 builds
./test_all.sh gcc-coverage/O0/fulldbg

# Test O2 builds
./test_all.sh gcc-coverage/O2/fulldbg

# Test O3 builds
./test_all.sh gcc-coverage/O3/fulldbg

# Compare coverage across optimization levels
```

---

## Output Structure

### Test Results

Displayed in terminal during test execution:
- Test pass/fail/skip counts
- Coverage detection status
- Coverage report locations
- Summary of all packages

### Coverage Reports

For coverage builds, each package creates:

```
/app/testsuite/<package>/
└── coverage_YYYYMMDD_HHMMSS/
    ├── coverage.info              # Raw coverage data
    ├── coverage_filtered.info     # Filtered coverage
    ├── lcov_capture.log          # lcov logs
    ├── genhtml.log               # HTML generation logs
    └── html/
        └── index.html            # Main coverage report
```

---

## Package Binary Paths

Different packages have binaries in different locations:

| Package | Binary Location |
|---------|----------------|
| nginx | `<base>/nginx/sbin/` |
| apache | `<base>/apache/bin/` |
| postgresql | `<base>/postgresql/bin/` |
| mysql | `<base>/mysql/bin/` |
| redis | `<base>/redis/bin/` |
| memcached | `<base>/memcached/bin/` |
| proftpd | `<base>/proftpd/bin/` |
| lighttpd | `<base>/lighttpd/bin/` |
| bind | `<base>/bind/bin/` |
| comdb2 | `<base>/comdb2/bin/` |

**Note:** `test_all.sh` automatically determines the correct path for each package.

---

## Features

### ✅ Automatic Path Detection

`test_all.sh` automatically:
- Detects correct binary paths for each package
- Handles different directory structures
- Skips packages that aren't built

### ✅ Coverage Auto-Collection

When testing coverage builds:
- Automatically detects `.gcno` files
- Runs `lcov` to capture coverage
- Generates HTML reports
- Shows coverage percentages in summary

### ✅ Failure Resilience

- Continues testing even if one package fails
- Tracks successful, failed, and skipped packages
- Shows comprehensive summary at the end

### ✅ Timestamped Reports

- Each test run creates new coverage directory
- Easy to track coverage over time
- No overwriting of previous data

---

## Exit Codes

Both `test.sh` and `test_all.sh` return:
- **0** - All tests passed
- **1** - One or more tests failed

Use in scripts:
```bash
if ./test_all.sh gcc-coverage/O2/fulldbg; then
    echo "All tests passed!"
else
    echo "Some tests failed - check summary above"
    exit 1
fi
```

---

## Advanced Usage

### Test and Compare Optimization Levels

```bash
#!/bin/bash
# Compare coverage across different optimization levels

for opt in O0 O2 O3; do
    echo "Testing ${opt}..."
    ./test_all.sh gcc-coverage/${opt}/fulldbg nginx

    # Rename coverage report for comparison
    mv /app/testsuite/nginx/coverage_* /app/testsuite/nginx/coverage_${opt}
done

# Compare
lcov --diff .../coverage_O0/coverage_filtered.info \
     .../coverage_O2/coverage_filtered.info \
     -o diff_O0_O2.info
```

---

### Run Tests in Background

```bash
# Run long test suite in background
nohup ./test_all.sh gcc-coverage/O2/fulldbg > test_all.log 2>&1 &

# Monitor progress
tail -f test_all.log | grep -E "Testing:|SUCCESS|FAILED"
```

---

### Extract Test Results

```bash
# Run tests and extract summary
./test_all.sh gcc-coverage/O2/fulldbg | tee test_results.txt

# Extract pass/fail counts
grep "Passed:" test_results.txt
grep "Failed:" test_results.txt

# Extract coverage percentages
grep "Coverage:" test_results.txt
```

---

## Integration with CI/CD

### GitLab CI Example

```yaml
test-all-packages:
  stage: test
  script:
    - cd testsuite
    # Build with coverage
    - ./build_all.sh coverage
    # Run all tests
    - ./test_all.sh gcc-coverage/O2/fulldbg
  artifacts:
    paths:
      - testsuite/*/coverage_*/html/
    reports:
      coverage_report:
        coverage_format: cobertura
        path: testsuite/*/coverage_*/coverage.xml
  allow_failure: false

test-critical-packages:
  stage: test
  script:
    - cd testsuite
    - ./build_all.sh coverage nginx redis postgresql
    - ./test_all.sh gcc-coverage/O2/fulldbg nginx redis postgresql
  allow_failure: false
```

---

## Troubleshooting

### Issue: "Binary path not found"

**Cause:** Package not built yet

**Solution:**
```bash
# Build the package first
./build.sh <package> [coverage]

# Then test
./test.sh <package> <binary_path>
```

---

### Issue: "Test script not found"

**Cause:** Package doesn't have a test script

**Solution:** Check available test scripts:
```bash
ls testscripts/*/test.sh
```

---

### Issue: All packages skipped

**Cause:** Binary base path is incorrect

**Solution:**
```bash
# Check where binaries are located
ls -d gcc*/O2/fulldbg/*/

# Use correct path
./test_all.sh gcc/O2/fulldbg
```

---

### Issue: Coverage not collected

**Cause:** Testing standard build (not coverage build)

**Solution:**
```bash
# Build with coverage
./build_all.sh coverage

# Test coverage builds
./test_all.sh gcc-coverage/O2/fulldbg
```

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `./test.sh <pkg> <bin_path>` | Test single package |
| `./test_all.sh` | Test all packages (default path) |
| `./test_all.sh gcc-coverage/O2/fulldbg` | Test coverage builds |
| `./test_all.sh gcc/O2/fulldbg nginx redis` | Test specific packages |

---

## Workflow Summary

### Complete Build & Test Pipeline

```bash
#!/bin/bash
# Complete pipeline: build, test, coverage

cd /app/testsuite

# 1. Build all packages with coverage
echo "Building packages..."
./build_all.sh coverage

# 2. Run all tests (coverage auto-collected)
echo "Running tests..."
./test_all.sh gcc-coverage/O2/fulldbg

# 3. Summary is shown automatically

# 4. View coverage reports
echo ""
echo "Coverage reports available at:"
ls -d */coverage_*/html/index.html
```

---

## Expected Timeline

**For full test suite (all 10 packages):**

| Package | Approx Test Time |
|---------|------------------|
| nginx | ~2 minutes |
| apache | ~5 minutes |
| redis | ~10 minutes |
| postgresql | ~15 minutes |
| mysql | ~20 minutes |
| memcached | ~1 minute |
| proftpd | ~2 minutes |
| lighttpd | ~3 minutes |
| bind | ~8 minutes |
| comdb2 | ~10 minutes |

**Total:** ~1-2 hours for full suite

**With coverage collection:** Add ~20% time overhead

---

## See Also

- `BUILD_WITH_COVERAGE.md` - How to build with coverage
- `testscripts/COVERAGE_COLLECTION.md` - Coverage collection details
- `build_all.sh` - Build all packages
- `BUILD_ALL_USAGE.md` - Build automation guide
