# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import json
import os
import subprocess
import csv
import shutil
from graph import Program, Module, Function
from analysistool import AnalysisTool, register_tool
from errors import logger, ToolExecutionError
import config


SAFER_VARIANTS = {
    "safer": {"src_dir": "safer_default", "has_instrument": True},
    "safer_enhanced": {"src_dir": "syscallpolicy", "has_instrument": True},
    "safer_reloc": {"src_dir": "safer_reloc", "has_instrument": True},
    "safer_sysfilter": {"src_dir": "sysfilter", "has_instrument": False},
}


class SaferBase(AnalysisTool):
    """Unified SAFER tool implementation. All variants share this class."""

    def __init__(self, variant="safer", inst_type="default_instrument", run_id="none"):
        super().__init__()
        self.variant = variant
        self.safer_path = config.TOOL_PATHS["safer_src"]

        cfg = SAFER_VARIANTS[variant]
        src_dir = cfg["src_dir"]

        self.safer_syscall_gen_parent_dir = self.safer_path + "/" + src_dir
        self.runid = run_id
        self.safer_syscall_gen_dir = self.safer_path + "/" + src_dir + "_" + self.runid
        os.makedirs(self.safer_syscall_gen_dir, exist_ok=True)

        try:
            for name in os.listdir(self.safer_syscall_gen_parent_dir):
                src_path = os.path.join(self.safer_syscall_gen_parent_dir, name)
                dst_path = os.path.join(self.safer_syscall_gen_dir, name)
                if os.path.isdir(src_path):
                    shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(src_path, dst_path)
        except Exception as e:
            raise ToolExecutionError(f"SAFER ({variant}) -- creating run directory failed: {e}") from e

        try:
            subprocess.run(
                ["make", "-j16"],
                cwd=self.safer_syscall_gen_dir,
                capture_output=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"SAFER ({variant}) -- make failed (return code: {e.returncode})")

        self.safer_syscall_gen = self.safer_syscall_gen_dir + "/run"
        self.call_graph_json = self.safer_syscall_gen_dir + "/tmp/cfg/callgraph.json"

        if cfg["has_instrument"]:
            self.safer_inst = self.safer_path + "/" + inst_type + "/run"

        self.name = variant

    def instrument(self, binary_path, syscall_list):
        if not SAFER_VARIANTS[self.variant]["has_instrument"]:
            raise ToolExecutionError(f"SAFER ({self.variant}) does not support instrumentation")

        logger.info(f"Instrumenting binary: {binary_path}")

        with open(self.safer_path + "/default_instrument/syscalls.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(syscall_list)

        try:
            subprocess.run([self.safer_inst, binary_path], capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            raise ToolExecutionError(f"SAFER ({self.variant}) instrumentation failed on {binary_path}") from e

        return binary_path + "_2"

    def invoke(self, binary_path, main):
        logger.info(f"Extracting module: {binary_path}")
        try:
            subprocess.run([self.safer_syscall_gen, binary_path], capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            raise ToolExecutionError(f"SAFER ({self.variant}) analysis failed on {binary_path}") from e

        json_functions = []

        with open(self.call_graph_json, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    json_functions.append(json.loads(line))

        mod = Module(binary_path)

        for f in json_functions:
            fn = self.json_to_function(f, binary_path)
            mod.add_function(fn)
        mod.main = main
        return mod


@register_tool("safer")
class Safer(SaferBase):
    def __init__(self, inst_type="default_instrument", run_id="none"):
        super().__init__(variant="safer", inst_type=inst_type, run_id=run_id)


@register_tool("safer_split_escape", prog_flags={
    "enhancements": True, "context": True,
})
class SaferSplitEscape(SaferBase):
    def __init__(self, run_id="none"):
        super().__init__(variant="safer_enhanced", run_id=run_id)


@register_tool("safer_argmatch", prog_flags={
    "enhancements": True, "context": True,
    "sig_match": True, "type_match": True,
})
class SaferArgMatch(SaferBase):
    def __init__(self, run_id="none"):
        super().__init__(variant="safer_enhanced", run_id=run_id)


@register_tool("safer_enhanced", prog_flags={
    "enhancements": True, "context": True,
    "const_prop": True, "sig_match": True, "type_match": True,
})
class SaferEnhanced(SaferBase):
    def __init__(self, run_id="none"):
        super().__init__(variant="safer_enhanced", run_id=run_id)


@register_tool("safer_reloc")
class SaferReloc(SaferBase):
    def __init__(self, inst_type="default_instrument", run_id="none"):
        super().__init__(variant="safer_reloc", inst_type=inst_type, run_id=run_id)


@register_tool("safer_sysfilter", prog_flags={"enhancements": True, "context": True})
class SaferSysfilter(SaferBase):
    def __init__(self, run_id="none"):
        super().__init__(variant="safer_sysfilter", run_id=run_id)
