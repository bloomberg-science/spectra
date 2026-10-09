# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import queue
import sys
import time
from typing import List
from errors import logger, BinaryAnalysisError, ProgressBar
from graph.models import Callee, Function, Module, MemRange
from graph.utils import remove_suffix, split_commas_or_string
import config


class Program:

    def __init__(self, name):
        self.name = name
        self.module_list = []
        self.dlsym_fns = set()
        self.execve_bins = set()

        self.edges = 0
        self.prev_edges = 0

        self.fn_set = set()
        self.enhancements = False
        self.const_prop = False
        self.context = False
        self.sig_match = False
        self.type_match = False

        self.context_at = []
        self.recent_context_at = []

        self.aict = 0.0

        self.gt_syscall_list = set()

        self.all_at_cache = {}

    def add_module(self, mod: Module, main: bool):
        logger.debug(f"Added module: {mod.module_path} main={main}")
        mod.main = main
        self.module_list.append(mod)

    def main_module(self) -> Module:
        for mod in self.module_list:
            if mod.main:
                return mod
        return None

    def get_module(self, mod_path):
        for mod in self.module_list:
            if mod.module_path == mod_path:
                return mod
        return None

    def fn_to_module(self, fn: Function) -> Module:
        for mod in self.module_list:
            if fn.module_name == mod.module_path and fn.addr in mod.function_map:
                return mod
        return None

    def is_int(self, sym: str):
        try:
            x = int(sym)
            return x
        except ValueError:
            return None

    def resolve_plt_call(self, sym: str, cur_mod: Module) -> Module:
        addrs = self.is_int(sym)
        if addrs is not None and addrs in cur_mod.function_map:
            cur_mod.symbol_map[sym] = addrs
            return None
        for mod in self.module_list:
            fn = mod.find_symbol(sym)
            if fn is not None:
                return mod
        return None

    def callee_caller_type_match(self, callee_fn, cs):
        if cs.args_passed_cnt >= callee_fn.args_used_cnt:
            if cs.expects_ret and callee_fn.returns_val == False:
                return False
            if self.type_match:
                for r, use in callee_fn.args_use.items():
                    if use == "pointer" and cs.args_reg_state[r] == "integer":
                        return False
            return True
        return False

    def populate_call_edges_fn(self, fn):
        edge_count = len(fn.child_fns)
        for cs in fn.call_site_list:
            for c in cs.unprocessed_targets:
                t = c.addr
                if t == 0:
                    continue
                t_mod = self.get_module(c.module)
                if t_mod is not None:
                    t_fn = t_mod.get_fn(t)
                    if t_fn is None:
                        logger.debug(f"Could not find call target: {hex(t)} in module: {c.module}")
                    else:
                        t_fn.add_parent(fn)
                        fn.add_child(t_fn)
                        cs.resolved_targets.append(t_fn)
            cs.unprocessed_targets = []
            plt = cs.unresolved_plt
            if plt is not None:
                mod = self.get_module(fn.module_name)
                plt_mod = self.resolve_plt_call(plt, mod)
                if plt_mod is None:
                    plt_fn = mod.find_symbol(plt)
                    if plt_fn is not None:
                        plt_fn.add_parent(fn)
                        fn.add_child(plt_fn)
                        cs.resolved_targets.append(plt_fn)
                else:
                    plt_fn = plt_mod.find_symbol(plt)
                    logger.debug(f"PLT target: {fn.module_name} {fn.name} {hex(cs.site)} --> {plt_fn.name}")
                    plt_fn.add_parent(fn)
                    fn.add_child(plt_fn)
                    cs.resolved_targets.append(plt_fn)

                cs.unresolved_plt = None

            if cs.link_at:
                if fn.all_at_linked:
                    continue
                at_fns = []
                if self.enhancements == False:
                    fn.all_at_linked = True
                    at_fns = self.all_address_taken_fns(fn, False)
                elif self.context == False:
                    if self.sig_match == False or cs.args_passed_cnt_changed:
                        at_fns = self.all_address_taken_fns(fn, False)
                elif self.context:
                    if cs.linking_first_time:
                        at_fns = self.all_address_taken_fns(fn, self.context)
                        cs.linking_first_time = False
                    elif self.sig_match and cs.args_passed_cnt_changed:
                        at_fns = self.all_address_taken_fns(fn, self.context)
                    else:
                        at_fns = self.recent_context_at
                linked_at_cnt = 0
                logger.debug(f"--------Linking AT {hex(cs.site)} {fn.name} {fn.module_name}")
                for t_fn in at_fns:
                    if self.sig_match:
                        if self.callee_caller_type_match(t_fn, cs):
                            linked_at_cnt += 1
                            t_fn.add_parent(fn)
                            fn.add_child(t_fn)
                    else:
                        linked_at_cnt += 1
                        t_fn.add_parent(fn)
                        fn.add_child(t_fn)
                logger.debug(f"--------AT Linked {linked_at_cnt}/{len(at_fns)}")
                if self.context == False and self.sig_match == False:
                    fn.all_at_linked = True
                cs.args_passed_cnt_changed = False

        new_edge_count = len(fn.child_fns)
        self.edges += (new_edge_count - edge_count)

    def right_caller(self, callee, call_site):
        for fn in call_site.resolved_targets:
            if fn.addr == callee.addr and fn.module_name == callee.module_name:
                return True
        if call_site.link_at and callee.address_taken:
            if self.sig_match:
                if self.callee_caller_type_match(callee, call_site):
                    return True
                else:
                    return False
            else:
                return True
        return False

    def get_parent_modules(self, addr):
        mod_list = []
        for mod in self.module_list:
            if mod.within_mem_range(addr) and mod.code_ptr(addr):
                mod_list.append(mod.module_path)
        return mod_list

    def get_reg_val_from_parent(self, reg, fn, depth=0):
        vals = []
        if depth >= 3:
            return vals
        depth += 1
        gpr = ["rdi", "rsi", "rcx", "rdx", "r8", "r9"]
        for p in fn.parent_fns:
            for cs in p.call_site_list:
                if self.right_caller(fn, cs):
                    if reg in cs.args_reg_state:
                        v = cs.args_reg_state[reg]
                        if v == "unknown" or "var" in v or v == "integer":
                            return ["unknown"]
                        elif v in gpr:
                            p_val = self.get_reg_val_from_parent(v, p, depth)
                            vals.extend(p_val)
                        else:
                            words = split_commas_or_string(v)
                            for w in words:
                                x = self.is_int(w)
                                if x is not None:
                                    mod_list = self.get_parent_modules(x)
                                    if len(mod_list) <= 0:
                                        return ["unknown"]
                                    for m in mod_list:
                                        c = Callee(x, m)
                                        vals.append(c)
                                else:
                                    return ["unknown"]
                    else:
                        logger.debug(f"Reg {reg} not in arg list of caller {hex(cs.site)} --> {hex(fn.addr)}")
        return vals

    def const_prop_ind_cf_resolution(self, fn):
        for cs in fn.call_site_list:
            if cs.link_at:
                continue
            if cs.unresolved_icf:
                if self.const_prop == False:
                    cs.link_at = True
                if cs.link_at == False and cs.ind_cf_expr.access_type == "register":
                    if cs.ind_cf_expr.reg == "unknown":
                        cs.link_at = True
                    else:
                        vals = self.get_reg_val_from_parent(cs.ind_cf_expr.reg, fn)
                        if len(vals) > 0 and "unknown" in vals:
                            cs.link_at = True
                        else:
                            for v in vals:
                                if cs.target_exists(v) == False:
                                    logger.debug(f"const prop target {fn.module_name} {hex(cs.site)} --> {hex(v.addr)}")
                                    cs.add_unprocessed_target(v)
                else:
                    cs.link_at = True
                if cs.link_at:
                    cs.linking_first_time = True

    def link_at_to_ind(self, fn):
        self.const_prop_ind_cf_resolution(fn)
        for cs in fn.call_site_list:
            if cs.unresolved_icf:
                if cs.link_at:
                    if "libc_start_main" not in fn.name and "cxa_finalize" not in fn.name:
                        if self.sig_match and cs.args_passed_cnt < 6:
                            self.populate_args_passing_fn(fn)
        return

    def all_address_taken_fns(self, cur_fn, context=False):
        at = []
        if context:
            return self.context_at
        else:
            mod = self.get_module(cur_fn.module_name)
            for d in mod.deps:
                d_mod = self.get_module(d)
                if d_mod is not None:
                    at.extend(d_mod.all_address_taken_fns())
        return at

    def reset(self):
        for mod in self.module_list:
            for addr, fn in mod.function_map.items():
                fn.processed = False

    def populate_args_usage_fn(self, fn):
        if fn.args_used_cnt >= 0:
            return
        reg_list = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]
        fn.args_used_cnt = 0
        ctr = 1
        for r in reg_list:
            if r in fn.args_use and fn.args_use[r] != "W" and fn.args_use[r] != "U":
                fn.args_used_cnt = ctr
            ctr += 1

    def reg_val_type(self, reg_val, module_name):
        split_words = split_commas_or_string(reg_val)
        all_ints = True
        all_pointers = True
        for w in split_words:
            x = self.is_int(w)
            if x is None:
                all_ints = False
            else:
                mod = self.get_module(module_name)
                if mod.within_mem_range(x) == False:
                    all_pointers = False

        if all_ints:
            if all_pointers:
                return "pointer"
            return "integer"

        return reg_val

    def populate_args_passing_fn(self, fn, checked=None):
        if checked is None:
            checked = set()

        if fn in checked:
            return

        checked.add(fn)

        if len(fn.call_site_list) <= 0:
            logger.debug(f"No call site in fn {hex(fn.addr)} module: {fn.module_name}")
            return

        reg_list = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]

        def update_args_cnt(cs):
            prev_cnt = cs.args_passed_cnt
            if cs.args_passed_cnt == -1:
                cs.args_passed_cnt = 0
                for reg, val in cs.args_reg_state.items():
                    if self.reg_val_type(val, fn.module_name) == "integer":
                        cs.args_reg_state[reg] = "integer"

            ind = 1
            for reg in reg_list:
                if cs.args_reg_state[reg] != reg:
                    if ind > cs.args_passed_cnt:
                        cs.args_passed_cnt = ind
                else:
                    break
                ind += 1

            if cs.args_passed_cnt > prev_cnt:
                cs.args_passed_cnt_changed = True

        if fn.call_site_list[0].args_passed_cnt < 0:
            for cs in fn.call_site_list:
                update_args_cnt(cs)

        all_cleared = True
        for cs in fn.call_site_list:
            if cs.args_passed_cnt < 6:
                all_cleared = False
        if all_cleared:
            return

        parents = fn.parent_fns
        for p in parents:
            if p.addr != fn.addr:
                self.populate_args_passing_fn(fn, checked)

        direct_caller_found = False
        inferred_reg_stat = {}

        def merge_reg_stat(reg, val):
            if val == reg:
                return
            if reg not in inferred_reg_stat:
                inferred_reg_stat[reg] = val
                return
            if inferred_reg_stat[reg] == "unknown":
                return
            if "var" in val or val in reg_list or inferred_reg_stat[reg] == "unknown":
                inferred_reg_stat[reg] = "unknown"
                return
            if self.is_int(val) or ',' in val:
                if reg not in inferred_reg_stat:
                    inferred_reg_stat[reg] = val
                elif inferred_reg_stat[reg] == "integer":
                    inferred_reg_stat[reg] = "unknown"
                elif inferred_reg_stat[reg] == "pointer":
                    inferred_reg_stat[reg] = "pointer"
                else:
                    inferred_reg_stat[reg] = inferred_reg_stat[reg] + "," + val
                return
            if val == "integer":
                if reg not in inferred_reg_stat:
                    inferred_reg_stat[reg] = val
                elif inferred_reg_stat[reg] == "integer":
                    inferred_reg_stat[reg] = "integer"
                else:
                    inferred_reg_stat[reg] = "unknown"
                return
            if val == "pointer":
                if reg not in inferred_reg_stat:
                    inferred_reg_stat[reg] = val
                elif inferred_reg_stat[reg] == "integer":
                    inferred_reg_stat[reg] = "unknown"
                else:
                    inferred_reg_stat[reg] = "pointer"
            return

        for p in parents:
            for p_cs in p.call_site_list:
                if self.right_caller(fn, p_cs):
                    direct_caller_found = True
                    for reg, stat in p_cs.args_reg_state.items():
                        merge_reg_stat(reg, stat)

        if direct_caller_found:
            for cs in fn.call_site_list:
                for reg, val in cs.args_reg_state.items():
                    if reg in inferred_reg_stat:
                        if val == reg:
                            cs.args_reg_state[reg] = inferred_reg_stat[reg]
                        elif "var" in val:
                            source_reg = remove_suffix(reg, "_var")
                            cs.args_reg_state[reg] = inferred_reg_stat[source_reg]
                        elif val in reg_list:
                            cs.args_reg_state[reg] = inferred_reg_stat[reg]
                update_args_cnt(cs)

    def populate_args_usage(self):
        for mod in self.module_list:
            for addr, fn in mod.function_map.items():
                self.populate_args_usage_fn(fn)
                if fn.address_taken:
                    mod.at.append(fn)

    def add_context_at(self, fn):
        mod = self.get_module(fn.module_name)
        for addr in fn.at_set:
            if addr in mod.context_at_added:
                continue
            mod.context_at_added.add(addr)
            at_fn = mod.get_fn(addr)
            if at_fn is None:
                logger.debug(f"Could not find AT fn {hex(addr)} in module {fn.module_name}")
            elif at_fn.address_taken:
                self.context_at.append(at_fn)
                self.recent_context_at.append(at_fn)

    def traverse_dcg(self, fn_list):
        for fn in fn_list:
            q = queue.Queue()
            q.put(fn)
            while q.empty() == False:
                cur_fn = q.get()
                if cur_fn.processed:
                    continue
                cur_fn.processed = True
                if cur_fn not in self.fn_set:
                    self.fn_set.add(cur_fn)
                self.add_context_at(cur_fn)
                self.populate_call_edges_fn(cur_fn)
                targets = self.reachable_fns(cur_fn)
                for tgt_fn in targets:
                    if tgt_fn.processed == False:
                        q.put(tgt_fn)

    def resolve_ind(self):
        new_fn_set = set()
        for fn in self.fn_set:
            logger.debug(f"Creating indirect edges for function: {hex(fn.addr)} {fn.module_name}")
            self.const_prop_ind_cf_resolution(fn)
            self.link_at_to_ind(fn)
            self.populate_call_edges_fn(fn)

            child_fns = fn.child_fns
            for c in child_fns:
                if c not in self.fn_set and c not in new_fn_set:
                    new_fn_set.add(c)
            logger.debug("Indirect edges created")

        return list(new_fn_set)

    def link_left_over_icfs(self):
        for mod in self.module_list:
            for addr, fn in mod.function_map.items():
                for cs in fn.call_site_list:
                    if cs.unresolved_icf and cs.link_at == False and len(cs.resolved_targets) < 0:
                        logger.debug(f"Unresolved leftover icf: {mod.module_path} {hex(cs.site)}")
                        at_fns = self.all_address_taken_fns(fn, self.context)
                        cs.link_at = True
                        if fn.all_at_linked:
                            continue
                        for t_fn in at_fns:
                            if self.sig_match:
                                if self.callee_caller_type_match(t_fn, cs):
                                    t_fn.add_parent(fn)
                                    fn.add_child(t_fn)
                            else:
                                t_fn.add_parent(fn)
                                fn.add_child(t_fn)

    def build_call_graph(self, fn_list):
        self.populate_args_usage()
        iter = 1
        start = time.time()
        while True:
            sys.stderr.write(f"\r  Building call graph: iter {iter} | edges {self.edges} | fns {len(self.fn_set)}   ")
            sys.stderr.flush()
            logger.debug(f"Iteration: {iter} new edge: {self.edges}")
            iter += 1
            self.recent_context_at = []
            if len(fn_list) > 0:
                self.traverse_dcg(fn_list)
            fn_list = self.resolve_ind()
            if self.edges == self.prev_edges:
                break
            else:
                self.prev_edges = self.edges
            logger.debug(f"Iteration complete. Next set of fns: {len(fn_list)}")

        elapsed = time.time() - start
        sys.stderr.write(f"\r  Building call graph: {iter-1} iterations, {self.edges} edges, {len(self.fn_set)} fns in {elapsed:.1f}s\n")
        sys.stderr.flush()
        self.link_left_over_icfs()

    def reachable_fns(self, fn):
        targets = set()
        for c in fn.child_fns:
            targets.add(c)
        return targets

    def mods_with_plt_target(self, target_name):
        self.populate_args_usage()
        mod = self.main_module()
        if mod is None or not mod.function_map:
            raise BinaryAnalysisError("No main module found")
        main_fn = mod.main_fn()
        fn_list = []
        if len(main_fn) > 0:
            fn_list = main_fn
        else:
            for addr, fn in mod.function_map.items():
                if fn.address_taken or fn.main:
                    fn_list.append(fn)
        self.build_call_graph(fn_list)
        self.reset()
        q = queue.Queue()
        module_set = set()

        for f in fn_list:
            q.put(f)

        while q.empty() == False:
            fn = q.get()
            if fn.processed:
                continue
            fn.processed = True
            if fn.has_plt_target(target_name):
                module_set.add(fn.module_name)
            targets = self.reachable_fns(fn)
            for tgt_fn in targets:
                if tgt_fn.processed == False:
                    q.put(tgt_fn)

        return module_set

    def syscalls(self):
        self.populate_args_usage()
        mod = self.main_module()
        if mod is None or not mod.function_map:
            raise BinaryAnalysisError("No main module found")
        main_fn = mod.main_fn()
        fn_list = []
        if len(main_fn) > 0:
            fn_list = main_fn
        else:
            for addr, fn in mod.function_map.items():
                if fn.address_taken or fn.main:
                    fn_list.append(fn)

        for fn_name in self.dlsym_fns:
            for mod in self.module_list:
                fn = mod.find_symbol(fn_name)
                if fn is not None:
                    fn_list.append(fn)

        for execve_path in self.execve_bins:
            execve_mod = self.get_module(execve_path)
            if execve_mod is not None:
                execve_main = execve_mod.main_fn()
                for fn in execve_main:
                    logger.info(f"Adding execve entry point: {fn.name} from {execve_path}")
                    fn_list.append(fn)

        loader_mod = self.get_module(config.LOADER_PATH)
        if loader_mod is not None:
            loader_entries = loader_mod.at
            for e in loader_entries:
                logger.debug(f"Adding loader fn to root entry: {e.name}")
                fn_list.append(e)
            loader_main = loader_mod.main_fn()
            for e in loader_main:
                logger.debug(f"Adding loader fn to root entry: {e.name}")
                fn_list.append(e)
        else:
            logger.debug("Could not find loader module")

        self.build_call_graph(fn_list)
        self.reset()
        q = queue.Queue()
        syscall_list = set()

        for f in fn_list:
            q.put(f)

        total_fns = len(self.fn_set)
        progress = ProgressBar(total_fns, desc="Collecting syscalls") if total_fns > 0 else None
        visited = 0
        while q.empty() == False:
            fn = q.get()
            if fn.processed:
                continue
            fn.processed = True
            visited += 1
            if progress:
                progress.update(fn.name)
            logger.debug(f"Reachable fn syscall: {fn.name} -> {fn.syscall_list}")
            for s in fn.syscall_list:
                syscall_list.add(s)

            targets = self.reachable_fns(fn)
            for tgt_fn in targets:
                if tgt_fn.processed == False:
                    q.put(tgt_fn)

        if progress:
            progress.finish()
        self.call_graph_stats()

        module_wise_syscalls = {}
        mod = self.main_module()
        main_mod_syscalls = self.module_wise_syscall_stats(syscall_list, mod)
        module_wise_syscalls[mod.module_path] = main_mod_syscalls

        main_fn = mod.main_fn()
        main_fn_syscall_list = self.module_wise_syscall_stats(syscall_list, mod, main_fn)

        other_ats_in_main_mod = []
        all_main_mod_ats = mod.at
        for t in all_main_mod_ats:
            if t.main == False:
                other_ats_in_main_mod.append(t)

        other_at_syscall_list = self.module_wise_syscall_stats(syscall_list, mod, other_ats_in_main_mod)
        other_at_syscall_list_uniq = []

        for s in other_at_syscall_list:
            if s not in main_fn_syscall_list:
                other_at_syscall_list_uniq.append(s)

        for m in self.module_list:
            if m.main == False:
                m_syscalls = self.module_wise_syscall_stats(syscall_list, m)
                unique_syscalls = set()
                for s in m_syscalls:
                    if s not in main_mod_syscalls:
                        unique_syscalls.add(s)
                module_wise_syscalls[m.module_path] = unique_syscalls

        logger.debug("-----------------Module wise syscalls")
        logger.debug(f"GT syscalls: {self.gt_syscall_list}")
        for m, s in module_wise_syscalls.items():
            logger.debug(f"{m} {s}")
            if m == mod.module_path:
                logger.debug(f"+++[From main] {main_fn_syscall_list}")
                logger.debug(f"+++[From other AT] {other_at_syscall_list_uniq}")

        return syscall_list

    def directly_reachable_fns(self, fn):
        res = set()
        for cs in fn.call_site_list:
            for t_fn in cs.resolved_targets:
                res.add(t_fn)
        return res

    def module_wise_syscall_stats(self, syscall_list, mod, root_fns=[]):
        all_at = mod.at
        if len(root_fns) > 0:
            all_at = root_fns
        self.reset()
        q = queue.Queue()

        for t in all_at:
            q.put(t)

        self.reset()
        mod_syscalls = set()
        while q.empty() == False:
            fn = q.get()
            if fn is None or fn.processed:
                continue
            fn.processed = True
            for s in fn.syscall_list:
                if s in syscall_list and s not in self.gt_syscall_list:
                    mod_syscalls.add(s)

            targets = self.directly_reachable_fns(fn)
            for tgt_fn in targets:
                if tgt_fn.processed == False and tgt_fn in self.fn_set:
                    q.put(tgt_fn)

        return mod_syscalls

    def call_graph_stats(self):
        mod_icf_cnt = {}
        mod_icf_tgt_cnt = {}
        over_all_icf_cnt = 0
        over_all_icf_tgt_cnt = 0
        resolved_icfs = 0

        all_at_cnt = 0

        for mod in self.module_list:
            for addr, fn in mod.function_map.items():
                if fn.address_taken:
                    all_at_cnt += 1

        bkt_map = {}
        bkt = 10
        bkt_sz = 100 / bkt

        ctr = bkt_sz
        while ctr <= 100:
            bkt_map[ctr] = 0
            ctr += bkt_sz

        self.reset()
        q = queue.Queue()
        mod = self.main_module()
        if mod is None or not mod.function_map:
            raise BinaryAnalysisError("No main module found")
        main_fn = mod.main_fn()
        fn_list = []
        if len(main_fn) > 0:
            fn_list = main_fn
        else:
            for addr, fn in mod.function_map.items():
                if fn.address_taken:
                    fn_list.append(fn)

        for fn_name in self.dlsym_fns:
            for mod in self.module_list:
                fn = mod.find_symbol(fn_name)
                if fn is not None:
                    fn_list.append(fn)

        for f in fn_list:
            q.put(f)

        while q.empty() == False:
            fn = q.get()
            if fn.processed:
                continue
            fn.processed = True

            targets = self.reachable_fns(fn)

            for cs in fn.call_site_list:
                if cs.unresolved_icf:
                    over_all_icf_cnt += 1
                    if fn.module_name in mod_icf_cnt:
                        mod_icf_cnt[fn.module_name] += 1
                    else:
                        mod_icf_cnt[fn.module_name] = 1
                    tgt_cnt = 0
                    if cs.link_at:
                        if self.enhancements == False:
                            tgt_cnt = all_at_cnt
                        else:
                            for t in targets:
                                if t.address_taken:
                                    if self.sig_match:
                                        if self.callee_caller_type_match(t, cs):
                                            tgt_cnt += 1
                                    else:
                                        tgt_cnt += 1
                    else:
                        tgt_cnt = len(cs.resolved_targets)
                    over_all_icf_tgt_cnt += tgt_cnt
                    if fn.module_name in mod_icf_tgt_cnt:
                        mod_icf_tgt_cnt[fn.module_name] += tgt_cnt
                    else:
                        mod_icf_tgt_cnt[fn.module_name] = tgt_cnt

                    pct = tgt_cnt / all_at_cnt * 100 if all_at_cnt > 0 else 0

                    logger.debug(f"---------ICF Node-------")
                    logger.debug(f"\tFunction {hex(fn.addr)} module {fn.module_name}")
                    logger.debug(f"\tCall site {hex(cs.site)} --> linked to {tgt_cnt} ({pct:.1f}%) AT functions | link_at {cs.link_at} unresolved {cs.unresolved_icf}")
                    ctr = bkt_sz
                    while ctr <= 100:
                        if pct <= ctr:
                            bkt_map[ctr] += 1
                            break
                        ctr += bkt_sz

            for tgt_fn in targets:
                if tgt_fn.processed == False:
                    q.put(tgt_fn)

            for cs in fn.call_site_list:
                if cs.unresolved_icf and cs.link_at == False:
                    resolved_icfs += 1
                    logger.debug(f"Resolved icf: {hex(cs.site)} fn {hex(fn.addr)} {fn.module_name}")

        logger.debug(f"Total nodes: {over_all_icf_cnt}")
        logger.debug(f"Total edges: {over_all_icf_tgt_cnt}")
        if over_all_icf_cnt > 0:
            aict = over_all_icf_tgt_cnt / over_all_icf_cnt
            self.aict = aict
            logger.debug(f"AICT: {aict}")
            logger.debug(f"Resolved ICFs: {resolved_icfs}")
            logger.debug("AICT per module:")
            for m, icf in mod_icf_cnt.items():
                m_aict = mod_icf_tgt_cnt[m] / icf
                logger.debug(f"\t{m} -- {m_aict}")

            logger.debug("Bucket data:")
            for b, val in bkt_map.items():
                logger.debug(f"\tLinked to {b - bkt_sz}-{b}% AT {val}")

    def call_graph(self):
        pass
