# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import json
import os
import subprocess
import sys
from bin_analysis_tools.angr.extract_syscall import analyze_binary
from graph import Program, Module, Function, CallSite, IndCFExpr
from analysistool import AnalysisTool, register_tool


@register_tool("angr")
class AngrTool(AnalysisTool):
    def __init__(self):
        super().__init__()
        self.name = "angr"


    def invoke(self, binary_path, main):

        fn_info = analyze_binary(binary_path)
        mod = Module(binary_path)

        for info in fn_info:
            call_site_list = []

            tgt_list = info["call_targets"] 
            cs = CallSite(
                0,
                info["address"],
                False,
                tgt_list,
                None,
                False,
                None,
                None,
                binary_path
            )
            call_site_list.append(cs)
            plt_targets = info["plt_targets"]
            for t in plt_targets:
                cs2 = CallSite(
                    0,
                    info["address"],
                    False,
                    [],
                    t,
                    False,
                    None,
                    None,
                    binary_path
                )
                call_site_list.append(cs2)

            if info["unresolved_icf"]:
                icf_details = IndCFExpr("unknown", "unknown")
                cs3 = CallSite(
                    0,
                    info["address"],
                    False,
                    [],
                    None,
                    True,
                    None,
                    icf_details,
                    binary_path
                )
                call_site_list.append(cs3)


            args_use = {
                "r8": "U",
                "r9": "U",
                "rcx": "U",
                "rdi": "U",
                "rdx": "U",
                "rsi": "U"
            }

            fn = Function (
                info["name"], 
                info["address"], 
                info["syscall_list"],
                False,
                info["address_taken"],
                call_site_list,
                args_use,
                [],
                binary_path,
                False
            )

            mod.add_function(fn)
        mod.main = main
        return mod
