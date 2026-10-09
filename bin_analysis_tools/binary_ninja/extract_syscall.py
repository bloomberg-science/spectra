# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import os
import sys
sys.path.append(os.path.join(os.environ.get("BNINJA_PATH", os.path.expanduser("~/binaryninja")), "python"))
from glob import glob

from binaryninja import LogLevel, PluginCommand, interaction, load, log, log_to_stdout, log_warn

from binaryninja.log import log_info, log_to_stdout
from binaryninja import load, BinaryView
from binaryninja import PluginCommand, LogLevel

from itertools import chain

from binaryninja import load
from binaryninja.enums import LowLevelILOperation, BranchType, SymbolType
from binaryninja.enums import LowLevelILOperation as LLO
from binaryninja.enums import RegisterValueType as RegisterValueType
from binaryninja.enums import RegisterValueType as RVT

from binaryninja import SSAVariable

def to_ssa_var(expr):
    """
    Return an SSAVariable from a MLIL/LLIL *_SSA expression across BN versions.
    Works for MLIL_VAR_SSA / LLIL_VAR_SSA nodes.
    """
    # Newer BN: some nodes expose .ssa_var directly
    if hasattr(expr, "ssa_var"):
        return expr.ssa_var

    # Older/other builds: synthesize from (var/src, version/ssa_version)
    var = getattr(expr, "var", None) or getattr(expr, "src", None)
    ver = getattr(expr, "ssa_version", None) or getattr(expr, "version", None)
    if var is None or ver is None:
        return None
    return SSAVariable(var, ver)


#def print_syscalls(fileName):
#	""" Print Syscall numbers for a provided file """
#	bv = load(fileName)
#	calling_convention = bv.platform.system_call_convention
#	if calling_convention is None:
#		print('Error: No syscall convention available for {:s}'.format(bv.platform))
#		return
#
#	register = calling_convention.int_arg_regs[0]
#
#	for func in bv.functions:
#

syscall_wrapper = {}

def resolve_syscall_wrapper(func, bv):
    calling_convention = bv.platform.system_call_convention
    if calling_convention is None:
    	print('Error: No syscall convention available for {:s}'.format(bv.platform))
    	return
    register = calling_convention.int_arg_regs[0]
    syscall_set = set()
    for c in func.call_sites:
        llil = c.llil
        if llil is not None:
            if(
                llil.operation == LowLevelILOperation.LLIL_CALL or 
                llil.operation == LowLevelILOperation.LLIL_TAILCALL or 
                llil.operation == LowLevelILOperation.LLIL_JUMP
            ):
                print(f"[Checking call to syscall wrapper] call site @ {hex(c.address)}: llil={llil}, dest={getattr(llil, 'dest', None)}")
                dest = llil.dest
                if dest is not None and dest.operation == LowLevelILOperation.LLIL_CONST_PTR:
                    dest_addr = dest.constant
                    if dest_addr in syscall_wrapper:
                        print("Found call to syscall wrapper: ", llil.address, "->", hex(dest_addr))
                        reg = calling_convention.int_arg_regs[syscall_wrapper[dest_addr]]
                        value = func.get_reg_value_at(llil.address, reg).value
                        print("Found syscall: ", value)
                        syscall_set.add(value)
    return syscall_set



def get_syscall_list(func, bv):
    calling_convention = bv.platform.system_call_convention
    if calling_convention is None:
    	print('Error: No syscall convention available for {:s}'.format(bv.platform))
    	return
    register = calling_convention.int_arg_regs[0]
    syscall_set = set()
    if func.low_level_il is not None:
        syscalls = (il for il in chain.from_iterable(func.low_level_il) if il.operation == LowLevelILOperation.LLIL_SYSCALL)
        if syscalls is not None:
            for il in syscalls:
                print("Resolving syscalls at: ", il.address)
                val_type = func.get_reg_value_at(il.address, register).type
                value = func.get_reg_value_at(il.address, register).value
                if val_type in (RegisterValueType.ConstantValue, RVT.ConstantPointerValue):
                    print("Found syscall: ", value, "type:", val_type)
                    syscall_set.add(value)
                else:
                    ml = il.mlil #func.get_mlil_at(il.address)
                    if ml:
                        arg0 = ml.ssa_form.params[0]
                        sv = to_ssa_var(arg0)
                        if sv is not None:
                            defi = func.mlil.ssa_form.get_ssa_var_definition(sv)
                            src = defi.src
                            print("Could not resolve RAX definition: ", src)
                        else:
                            print("Could not form SSAVariable for arg0")

    return syscall_set
    
def get_bininfo(filename):
    syscall_wrapper.clear()
    if not (os.path.isfile(filename) and os.access(filename, os.R_OK)):
        print("cannot read ", filename)
        return []
    bv = load(filename)
    base = bv.start
    functions = list(bv.functions)

    all_func_data = []

    for func in functions:
        fn_start = func.start - base
        fn_name = func.symbol.full_name
        symbol_type = func.symbol.type
        unresolved_icf = func.has_unresolved_indirect_branches
        callees = list(func.callees)
        call_sites = func.call_sites
        plt_targets = set()
        call_targets = set()
        address_taken = False

        code_refs = list(bv.get_code_refs(func.start))
        data_refs = list(bv.get_data_refs(func.start))

        if len(code_refs) > 0 or len(data_refs) > 0:
            address_taken = True
        for c in call_sites:
            llil = c.llil
            print(f"call site @ {hex(c.address)}: llil={llil}, dest={getattr(llil, 'dest', None)}")
            if llil is not None:
                if(
                    llil.operation == LowLevelILOperation.LLIL_CALL or 
                    llil.operation == LowLevelILOperation.LLIL_TAILCALL or 
                    llil.operation == LowLevelILOperation.LLIL_JUMP
                ):
                    dest = llil.dest
                    if dest is not None and dest.operation != LowLevelILOperation.LLIL_CONST_PTR:
                        resolved_tgts = func.get_indirect_branches_at(c.address)
                        if len(resolved_tgts) <= 0:
                            unresolved_icf = True
                        else:
                            for t in resolved_tgts:
                                call_targets.add(t.dest_addr - base)

        for c in callees:
            print("\t--Callee",c.name, " at ", hex(c.start - base))
            if c.name == "syscall":
                syscall_wrapper[c.start] = 1
            if c.symbol.type == SymbolType.ImportedFunctionSymbol:
                plt_targets.add(c.name)
            else:
                call_targets.add(c.start - base)
        syscall_list = get_syscall_list(func, bv)
        if symbol_type != SymbolType.ImportedFunctionSymbol:
            func_info = {
                "name": fn_name,
                "address": fn_start,
                "call_targets": list(call_targets),
                "plt_targets": list(plt_targets),
                "unresolved_icf": unresolved_icf,
                "address_taken": address_taken,
                "syscall": list(syscall_list)
            }
            print("------------function--------")
            print("name: ", fn_name)
            print("address: ", hex(fn_start))
            print("unresolved icf: ", unresolved_icf)
            print("address taken: ", address_taken)
            print("Symbol type: ", symbol_type)
            print("Syscall list: ", list(syscall_list))
            print("Call targets:", list(call_targets))
            print("PLT targets:", list(plt_targets))
            print("----------------------------")
            all_func_data.append(func_info)

    for d in all_func_data:
        func = bv.get_function_at(d["address"] + base)
        syscall_set = resolve_syscall_wrapper(func, bv)
        syscall_list = d["syscall"]
        syscall_list.extend(syscall_set)
        d["syscall"] = syscall_list

    if filename != "":
        bv.file.close()

    return all_func_data

if __name__ == "__main__":
	if len(sys.argv) != 2:
		print('Usage: {} <file>'.format(sys.argv[0]))
	else:
		get_bininfo(sys.argv[1])
