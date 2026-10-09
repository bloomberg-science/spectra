# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import os
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TESTSUITE_DIR = os.path.join(BASE_DIR, "testsuite")
TESTDATA_DIR = os.path.join(TESTSUITE_DIR, "testdata")
CACHE_DIR = os.path.join(TESTDATA_DIR, "external_libs")
GT_DIR = os.path.join(TESTDATA_DIR, "gt")
LIBSDATA_DIR = os.path.join(TESTDATA_DIR, "libsdata")

BINARIES_DIR = os.path.join(TESTSUITE_DIR, "subset_binaries", "gcc")
TESTLIBS_DIR = os.path.join(TESTSUITE_DIR, "testlibs")

TMP_DIR = os.environ.get("BINARY_ANALYSIS_TMP", tempfile.gettempdir())

TOOL_PATHS = {
    "ida": os.environ.get("IDA_PATH", "idat"),
    "ida_scripts": os.environ.get("IDA_SCRIPTS", os.path.join(BASE_DIR, "bin_analysis_tools", "ida")),
    "ghidra": os.environ.get("GHIDRA_PATH", os.path.join(BASE_DIR, "bin_analysis_tools", "ghidra_projects", "ghidra", "support", "analyzeHeadless")),
    "ghidra_scripts": os.environ.get("GHIDRA_SCRIPTS", os.path.join(BASE_DIR, "bin_analysis_tools", "ghidra_projects")),
    "safer_src": os.path.join(BASE_DIR, "bin_analysis_tools", "safer", "apps"),
}

LOADER_PATH = os.environ.get("LOADER_PATH", "/lib64/ld-linux-x86-64.so.2")

PACKAGES = [
    "apache", "bind", "bmq", "comdb2",
    "lighttpd", "memcached", "mysql", "nginx",
    "postgresql", "proftpd", "redis",
]
