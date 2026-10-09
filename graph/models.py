# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import json
import os
from typing import List
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from errors import logger


class Callee:
    def __init__(self, addr, module_path):
        self.addr = addr
        self.module = module_path


class IndCFExpr:
    def __init__(self, access_type, reg):
        self.access_type = access_type
        self.reg = reg


class CallSite:
    def __init__(
            self,
            site,
            fn_addr,
            expects_ret,
            targets,
            plt_target,
            unresolved_icf,
            args_reg_state,
            ind_cf_expr,
            module_path
        ):
        self.site = site
        self.fn_addr = fn_addr
        self.expects_ret = expects_ret
        self.targets = targets
        self.plt_target = plt_target
        self.unresolved_icf = unresolved_icf
        self.args_reg_state = args_reg_state
        self.ind_cf_expr = ind_cf_expr
        self.resolved_plt = {}
        self.link_at = False
        self.all_at_linked = False
        self.unresolved_plt = plt_target
        self.unprocessed_targets = []
        self.resolved_targets = []
        self.args_passed_cnt = -1
        self.args_passed_cnt_changed = False
        self.linking_first_time = False

        for t in self.targets:
            callee = Callee(t, module_path)
            self.unprocessed_targets.append(callee)

    def target_exists(self, tgt):
        for t_fn in self.resolved_targets:
            if t_fn.addr == tgt.addr and t_fn.module_name == tgt.module:
                return True
        return False

    def add_unprocessed_target(self, c):
        for t in self.unprocessed_targets:
            if c.addr == t.addr and c.module == t.module:
                return
        self.unprocessed_targets.append(c)


class Function:
    def __init__(
            self,
            name, addr,
            syscall_list, returns_val,
            address_taken, call_site_list,
            args_use, at_set, module_path, main=False
        ):
        self.name = name
        self.addr = addr
        self.syscall_list = syscall_list
        self.address_taken = address_taken
        self.resolved_plts = {}
        self.processed = False
        self.module_name = module_path
        self.call_site_list = call_site_list
        self.main = main
        self.parent_fns = set()
        self.child_fns = set()
        self.link_all_at = False
        self.all_at_linked = False
        self.args_use = args_use
        self.args_used_cnt = -1
        self.returns_val = returns_val
        self.at_set = at_set

        self.max_args = -1
        self.expects_ret = False

    def add_child(self, child_fn):
        self.child_fns.add(child_fn)

    def add_parent(self, parent_fn):
        self.parent_fns.add(parent_fn)

    def has_plt_target(self, target_name):
        for cs in self.call_site_list:
            if cs.plt_target == target_name:
                return True
        return False


class MemRange:
    def __init__(self, start, end):
        self.start = start
        self.end = end


class Module:
    def __init__(self, module_path):
        self.module_path = module_path
        self.function_map = {}
        self.symbol_map = {}
        self.deps = set()
        self.main = False
        self.at = []

        self.context_at_added = set()

        self.rx_segment = None
        self.rw_segment = None
        self.ro_segment = None

        with open(self.module_path, 'rb') as f:
            elf = ELFFile(f)
            dynsym = elf.get_section_by_name('.dynsym')
            if dynsym and isinstance(dynsym, SymbolTableSection):
                logger.info("Populating dynamic symbols")
                for symbol in dynsym.iter_symbols():
                    if symbol['st_shndx'] == 'SHN_UNDEF':
                        continue
                    self.symbol_map[symbol.name] = symbol['st_value']
            symtab = elf.get_section_by_name('symtab')
            if symtab and isinstance(symtab, SymbolTableSection):
                logger.info("Populating general symbols")
                for symbol in symtab.iter_symbols():
                    if symbol['st_shndx'] == 'SHN_UNDEF':
                        continue
                    self.symbol_map[symbol.name] = symbol['st_value']

        PF_X, PF_W, PF_R = 1, 2, 4

        with open(self.module_path, 'rb') as f:
            elf = ELFFile(f)
            for seg in elf.iter_segments():
                if seg['p_type'] == 'PT_LOAD':
                    flags = seg['p_flags']
                    perm = ('R' if flags & PF_R else '-') + \
                           ('W' if flags & PF_W else '-') + \
                           ('X' if flags & PF_X else '-')
                    start = seg['p_vaddr']
                    end = start + seg['p_memsz'] - 1
                    logger.debug(f"{perm}  [0x{start:016x}, 0x{end:016x}]")
                    if 'X' in perm:
                        self.rx_segment = MemRange(start, end)
                    elif 'W' in perm:
                        self.rw_segment = MemRange(start, end)
                    else:
                        self.ro_segment = MemRange(start, end)

    def add_function(self, fn: Function):
        self.function_map[fn.addr] = fn

    def has_plt_target(self, target_name):
        for addr, fn in self.function_map.items():
            if fn.has_plt_target(target_name):
                return True
        return False

    def within_mem_range(self, addr):
        if self.rx_segment is not None and addr >= self.rx_segment.start and addr <= self.rx_segment.end:
            return True
        if self.rw_segment is not None and addr >= self.rw_segment.start and addr <= self.rw_segment.end:
            return True
        if self.ro_segment is not None and addr >= self.ro_segment.start and addr <= self.ro_segment.end:
            return True
        return False

    def code_ptr(self, addr):
        if addr >= self.rx_segment.start and addr <= self.rx_segment.end:
            fn = self.get_fn(addr)
            if fn is not None:
                return True
        return False

    def add_deps(self, dep_list):
        for d in dep_list:
            self.deps.add(d)

    def find_symbol(self, sym: str) -> Function:
        if sym in self.symbol_map:
            fn_addr = self.symbol_map[sym]
            if fn_addr != 0:
                fn = self.function_map.get(fn_addr)
                return fn
        return None

    def all_address_taken_fns(self):
        return self.at

    def main_fn(self):
        main_fn_list = []
        for addr, fn in self.function_map.items():
            if fn.main:
                main_fn_list.append(fn)
        return main_fn_list

    def get_fn(self, fn_addr):
        if fn_addr in self.function_map:
            return self.function_map[fn_addr]
        return None

    def export_to_json(self, outfile):
        data = []

        mod_data = {
            "module": self.module_path,
        }
        data.append(mod_data)

        for addr, fn in self.function_map.items():
            call_site_data = []
            for cs in fn.call_site_list:
                ind_data = []
                if cs.ind_cf_expr is not None:
                    ind_expr = {
                        "site": cs.site,
                        "type": cs.ind_cf_expr.access_type,
                        "reg_val": cs.ind_cf_expr.reg
                    }
                    ind_data.append(ind_expr)

                cs_info = {
                    "site": cs.site,
                    "args": cs.args_reg_state,
                    "expects_ret": cs.expects_ret,
                    "targets": cs.targets,
                    "plt_target": cs.plt_target,
                    "unresolved_icf": cs.unresolved_icf,
                    "icf_details": ind_data
                }
                call_site_data.append(cs_info)
            func_info = {
                "name": fn.name,
                "main": fn.main,
                "address": addr,
                "address_taken": fn.address_taken,
                "return_val": fn.returns_val,
                "args_use": fn.args_use,
                "syscall": list(fn.syscall_list),
                "at_list": list(fn.at_set),
                "call_sites": call_site_data
            }
            data.append(func_info)
        with open(outfile, "w") as f:
            json.dump(data, f, indent=4)
