# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import json
import os
import subprocess
from graph import Program, Module, Function
from analysistool import AnalysisTool, register_tool
from errors import logger, ToolExecutionError
import config

@register_tool("ida")
class IDA(AnalysisTool):
    def __init__(self):
        super().__init__()
        self.ida_path = config.TOOL_PATHS["ida"]
        self.script_path = config.TOOL_PATHS["ida_scripts"]
        self.script = "extract_cfg.py"
        self.name = "IDA"

    def invoke(self, binary_path, main):
        print("[+] extracting module: ", binary_path)
        mod = Module(binary_path)
        prog_name = os.path.basename(binary_path)

        tmp_path = os.path.join(config.TMP_DIR, "ida_" + self.runid)
        os.makedirs(tmp_path, exist_ok=True)

        tmp_prog_path = tmp_path + "/" + prog_name
        
        cmd = [
            "cp",
            binary_path,
            tmp_prog_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            raise ToolExecutionError(f"IDA -- copy to tmp path failed for {binary_path}") from e

        error_log = tmp_path + "/ida_error.log"
        if os.path.exists(error_log):
            os.remove(error_log)

        cmd = [
            self.ida_path,
            "-a-",
            "-A",
            "-c",
            "-S" + self.script_path + "/" + self.script,
            tmp_prog_path
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, check=True)
            if os.path.exists(error_log):
                raise ToolExecutionError(f"IDA produced error log for {binary_path}")
        except subprocess.CalledProcessError as e:
            raise ToolExecutionError(f"IDA failed to run on {binary_path}") from e

        json_functions = []
        ida_functions = []

        with open(tmp_prog_path + ".json", "r") as f:
            #ida_functions = json.load(f)
            json_functions = json.load(f)

        #known_funcs = []
        #for fn in ida_functions:
        #    known_funcs.append(fn["address"])
        #
        #fn_info = analyze_binary(binary_path, known_funcs)

        #for ida_fn in ida_functions:
        #    json_fn = ida_fn
        #    found = False
        #    for angr_fn in fn_info:
        #        if angr_fn["address"] == ida_fn["address"]:
        #            json_fn["syscall"] = list(angr_fn["syscall_list"])
        #            found = True
        #            break
        #    if found == False:
        #        print("[+] Angr could not find function: ", ida_fn["name"], " - ", hex(ida_fn["address"]))
        #    json_functions.append(json_fn)
        

        for f in json_functions:
            fn = self.json_to_function(f, binary_path)
            mod.add_function(fn)

        mod.main = main
        return mod
