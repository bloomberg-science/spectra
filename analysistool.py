# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import json
import os
import subprocess
import sys
from graph import Program, Module, Function, CallSite, IndCFExpr
from abc import ABC, abstractmethod
import config

TOOL_REGISTRY = {}


def register_tool(name, prog_flags=None):
    """Decorator to register a tool class by name.

    prog_flags: dict of Program attributes to set when this tool is used
                (e.g. {"enhancements": True, "context": True})
    """
    def decorator(cls):
        TOOL_REGISTRY[name] = {"cls": cls, "prog_flags": prog_flags or {}}
        return cls
    return decorator


def create_tool(name, **kwargs):
    """Instantiate a registered tool by name. Passes kwargs that the constructor accepts."""
    if name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {name}. Available: {list(TOOL_REGISTRY.keys())}")
    cls = TOOL_REGISTRY[name]["cls"]
    import inspect
    sig = inspect.signature(cls.__init__)
    valid_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return cls(**valid_kwargs)


def get_tool_prog_flags(name):
    """Get Program flags associated with a tool."""
    if name in TOOL_REGISTRY:
        return TOOL_REGISTRY[name]["prog_flags"]
    return {}


def available_tools():
    """Return list of registered tool names."""
    return list(TOOL_REGISTRY.keys())


class AnalysisTool(ABC):

    def __init__(self):
        self.name = "unknown"
        self.runid = "none"

    @abstractmethod
    def invoke(self, bin_path, main):
        pass

    def json_to_function(self, json_fn, module_path):
        name = json_fn["name"]
        addr = json_fn["address"] 
        syscall_list = json_fn["syscall"]
        at = json_fn["address_taken"]
        main = False
        if "main" in json_fn:
            main = json_fn["main"]
        call_site_json = []
        call_site_list = []
        if "call_sites" in json_fn:
            call_site_json = json_fn["call_sites"]
        else:
            tgt_list = json_fn["call_targets"] 
            cs = CallSite(
                0,
                json_fn["address"],
                False,
                tgt_list,
                None,
                False,
                None,
                None,
                module_path
            )
            call_site_list.append(cs)
            plt_targets = json_fn["plt_targets"]
            for t in plt_targets:
                cs2 = CallSite(
                    0,
                    json_fn["address"],
                    False,
                    [],
                    t,
                    False,
                    None,
                    None,
                    module_path
                )
                call_site_list.append(cs2)

            if json_fn["unresolved_icf"]:
                icf_details = IndCFExpr("unknown", "unknown")
                cs3 = CallSite(
                    0,
                    json_fn["address"],
                    False,
                    [],
                    None,
                    True,
                    None,
                    icf_details,
                    module_path
                )
                call_site_list.append(cs3)

        args_use = {}
        returns_val = False
        if "args_use" in json_fn:
            args_use = json_fn["args_use"]
            returns_val = json_fn["return_val"]
        else:
            args_use = {
                "r8": "U",
                "r9": "U",
                "rcx": "U",
                "rdi": "U",
                "rdx": "U",
                "rsi": "U"
            }
        at_set = []
        if "at_list" in json_fn:
            at_set = json_fn["at_list"]


        for call_site in call_site_json:
            site = call_site["site"]
            args = call_site["args"]
            expects_ret = call_site["expects_ret"]
            targets = call_site["targets"]
            plt_target = call_site["plt_target"]
            if plt_target is not None and len(plt_target) <= 0:
                plt_target = None
            unresolved_icf = call_site["unresolved_icf"]

            icf_expr = None

            if unresolved_icf:
                icf_json = call_site["icf_details"];
                #print("[+] Unresolved icf ", icf_json)
                acc_type = icf_json[0]["type"]
                reg = icf_json[0]["reg_val"]

                icf_expr = IndCFExpr(acc_type, reg)

            cs = CallSite (
                site, 
                addr, 
                expects_ret, 
                targets, 
                plt_target, 
                unresolved_icf, 
                args, 
                icf_expr, 
                module_path
            )
            call_site_list.append(cs)


        f = Function (
            name,
            addr,
            syscall_list,
            returns_val,
            at,
            call_site_list,
            args_use,
            at_set,
            module_path,
            main
        )

        return f

    def extract(self, bin_path, main=False):
        if main == False:
            bin_name = os.path.basename(bin_path)
            json_dir = os.path.join(config.CACHE_DIR, self.name)
            os.makedirs(json_dir, exist_ok=True)
            json_dir = json_dir + "/" + self.runid
            os.makedirs(json_dir, exist_ok=True)
            json_file = json_dir + "/" + bin_name + ".json"
            cached=False
            mod = Module(bin_path)
            if os.path.exists(json_file):
                json_functions = []


                with open(json_file, "r") as f:
                    json_functions = json.load(f)
                
                ctr = 0
                for f in json_functions:
                    if ctr == 0:
                        mod_path = f["module"]
                        if mod_path == bin_path:
                            cached=True
                        else:
                            break
                    else:
                        fn = self.json_to_function(f, bin_path)
                        mod.add_function(fn)
                    ctr += 1

            if cached == False:
                os.makedirs(os.path.join(config.CACHE_DIR, self.name), exist_ok=True)
                mod = self.invoke(bin_path, main)
                mod.export_to_json(json_file)
            return mod
        else:
            mod = self.invoke(bin_path, main)
            return mod

        return None


