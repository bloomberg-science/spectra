# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import json
import os
import subprocess
from graph import Program, Module, Function
from analysistool import AnalysisTool, register_tool
from errors import logger, ToolExecutionError
import config

@register_tool("ghidra")
class Ghidra(AnalysisTool):
    def __init__(self):
        super().__init__()
        self.ghidra_path = config.TOOL_PATHS["ghidra"]
        self.script_path = config.TOOL_PATHS["ghidra_scripts"]
        self.script = "extract_syscall.py"
        self.name = "ghidra"

    def invoke(self, binary_path, main):
        print("[+] extracting module: ", binary_path)

        tmp_dir = os.path.join(config.TMP_DIR, "ghidra_" + self.runid)
        os.makedirs(tmp_dir, exist_ok=True)

        if os.path.exists(tmp_dir + "/functions.json"):
            cmd = [
                "rm",
                tmp_dir + "/functions.json"
            ]
            result = subprocess.run(cmd, capture_output=True, check=True)
        cmd = [
            self.ghidra_path,
            tmp_dir,
            "tmp_proj_" + self.runid,
            "-scriptPath", self.script_path,
            "-postScript", self.script, tmp_dir,
            "-deleteProject",
            "-import", binary_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            raise ToolExecutionError(f"Ghidra failed to run on {binary_path}") from e

        json_functions = []

        if os.path.exists(tmp_dir + "/functions.json"):

            with open(tmp_dir + "/functions.json", "r") as f:
                json_functions = json.load(f)

            mod = Module(binary_path)

            for f in json_functions:
                fn = self.json_to_function(f, binary_path)
                mod.add_function(fn)

            mod.main = main
            return mod
        else:
            raise ToolExecutionError(f"Ghidra produced no output for {binary_path}")
