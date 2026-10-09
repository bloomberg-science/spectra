# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

from ghidra.util.task import ConsoleTaskMonitor

from ghidra.app.script import GhidraScript
from ghidra.program.model.listing import Program
from ghidra.util.task import TaskMonitor
from ghidra.program.util import ProgramMerge
from ghidra.util.exception import CancelledException
from ghidra.app.util import Option
from ghidra.framework.model import DomainFolder
from ghidra.app.util.opinion import LoaderService
from ghidra.app.decompiler import DecompInterface
from ghidra.app.decompiler import DecompInterface
from ghidra.program.model.pcode import PcodeOp, Varnode
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.model.lang import Register
from ghidra.program.model.symbol import RefType
from ghidra.program.model.symbol import FlowType
from ghidra.program.model.block import BasicBlockModel
from ghidra.program.model.listing import Instruction
from ghidra.program.model.address import Address
from ghidra.program.model.lang import OperandType
from ghidra.app.decompiler import DecompInterface
from ghidra.program.model.address import AddressSet
from ghidra.program.model.symbol import SymbolType



listing = currentProgram.getListing()
fm = currentProgram.getFunctionManager()
block_model = BasicBlockModel(currentProgram)
monitor = ConsoleTaskMonitor()

image_base = currentProgram.getImageBase()

args = getScriptArgs()
print(args)

syscall_wrapper = {}

def rebase(addr):
    addr_int = addr.getOffset() - image_base.getOffset()
    return addr_int


def is_address_taken(func):
    refs = getReferencesTo(func.getEntryPoint())
    for ref in refs:
        ref_type = ref.getReferenceType()
        if not ref_type.isCall() and not ref_type.isJump():
            return True
    return False

def has_unresolved_icf(func):
    #print("Checking for unresolved ICF")
    instr = listing.getInstructions(func.getBody(), True)
    for i in instr:
        flow_type = i.getFlowType()
        if (flow_type.isCall() or flow_type.isJump()):
            if is_direct_cf(i) == False:
                print("Indirect CF")
                refs = i.getFlows()
                #print("instr: ", hex(rebase(i.getAddress())), " indirect targets: ", refs)
                if len(refs) <= 0:
                    return True
    #print("Unresolved ICF check done")
    return False


#def is_indirect_control_flow(instr):
#    flow_type = instr.getFlowType()
#
#    # Only apply to calls/jumps/branches
#    if not (flow_type.isCall() or flow_type.isJump()):
#        return False
#
#    op_type = instr.getOperandType(0)
#
#    # These mean indirect: register, memory, or indirect reference
#    return (
#        (op_type & OperandType.REGISTER) != 0 or
#        (op_type & OperandType.ADDRESS) != 0 and (op_type & OperandType.INDIRECT) != 0 or
#        (op_type & OperandType.INDIRECT) != 0
#    )


def is_direct_cf(instr):
    
    op_type = instr.getOperandType(0)
    #print("checking jump type: ", hex(rebase(instr.getAddress())),op_type, OperandType.ADDRESS, OperandType.CODE, (OperandType.ADDRESS | OperandType.CODE))
    if op_type == (OperandType.ADDRESS | OperandType.CODE):
        #print("Direct CF")
        return True
    return False

def is_function_external(func):
    if not func:
        return False

    symtab = currentProgram.getSymbolTable()
    externals = symtab.getExternalSymbols()
    func_name = func.getName()

    for ext_sym in externals:
        if ext_sym.getName() == func_name:
            return True

    return False

def get_call_targets(func):
    targets = set()
    plt_targets = set()
    #print("Looking for call targets")
    instructions = listing.getInstructions(func.getBody(), True)

    for instr in instructions:
        ft = instr.getFlowType()

        if ft.isCall() and is_direct_cf(instr):
            flows = instr.getFlows()
            for f in flows:
                targets.add(rebase(f))
        elif ft.isCall() and is_direct_cf(instr) == False:
            flows = instr.getFlows()
            for f in flows:
                tgt_fn = getFunctionAt(f)
                if tgt_fn:
                    print("indirect call target ", hex(rebase(instr.getAddress())), "--> ", hex(rebase(f)))
                    if is_function_external(tgt_fn):
                        plt_targets.add(tgt_fn.getName())
                        print("PLT function -- ", tgt_fn.getName())
                        if tgt_fn.getName() == "syscall":
                            print("Found syscall wrapper: ", hex(rebase(func.getEntryPoint())))
                            syscall_wrapper[func.getEntryPoint()] = "RDI"
                    else:
                        targets.add(rebase(f))
        elif ft.isJump() and is_direct_cf(instr):
            flows = instr.getFlows()
            for f in flows:
                if getFunctionAt(f) and not func.getBody().contains(f):
                    targets.add(rebase(f))
        elif ft.isJump() and is_direct_cf(instr) == False:
            flows = instr.getFlows()
            for f in flows:
                tgt_fn = getFunctionAt(f)
                if tgt_fn:
                    print("indirect jump target ", hex(rebase(instr.getAddress())), "--> ", hex(rebase(f)))
                    if is_function_external(tgt_fn):
                        plt_targets.add(tgt_fn.getName())
                        print("PLT function -- ", tgt_fn.getName())
                        if tgt_fn.getName() == "syscall":
                            print("Found syscall wrapper: ", hex(rebase(func.getEntryPoint())))
                            syscall_wrapper[func.getEntryPoint()] = "RDI"
                    elif not func.getBody().contains(f):
                        targets.add(rebase(f))
    #print("Call target look up done")
    return targets, plt_targets


def is_register(op_obj, name):
    return isinstance(op_obj, Register) and op_obj.getName().upper() == name.upper()

def defines_reg(instr, reg):
    rax_reg = currentProgram.getRegister(reg)
    if instr.getNumOperands() >= 1:
        dest_objs = instr.getOpObjects(0)
        print("Destination objects: ", dest_objs)
        if len(dest_objs) > 0 and isinstance(dest_objs[0], Register):
            if rax_reg.contains(dest_objs[0]):
                return True
    return False

def get_predecessor_blocks(block):
    preds = []
    refs = block.getSources(monitor)
    while refs.hasNext():
        ref = refs.next()
        from_block = ref.getSourceBlock()
        preds.append(from_block)

    return preds

def walk_paths(block, start_instr, seen_blocks, model, reg):
    if block in seen_blocks:
        return []  # Prevent loops

    seen_blocks.add(block)

    # Walk backward in the current block
    listing = currentProgram.getListing()
    instr = listing.getInstructionContaining(block.getMaxAddress())
    #print("Checking block for RAX def: ", hex(rebase(block.getMinAddress())))
    while instr and block.contains(instr.getAddress()):
        #print("Instr: ", hex(rebase(instr.getAddress())))
        if block.contains(start_instr) and instr.getAddress().getOffset() >= start_instr.getOffset():
            instr = instr.getPrevious()
            continue
        if defines_reg(instr, reg):
            print("RAX def found: ", hex(rebase(instr.getAddress())))
            return [instr.getAddress()]  # Closest def on this path
        instr = instr.getPrevious()

    # No RAX def in this block -- recurse into predecessors
    rax_defs = []
    for pred in get_predecessor_blocks(block):
        subpath_defs = walk_paths(pred, start_instr, seen_blocks.copy(), model, reg)
        rax_defs.extend(subpath_defs)
    return rax_defs

def get_pathwise_reg_definitions(start_instr, reg):
    model = BasicBlockModel(currentProgram)
    block = model.getFirstCodeBlockContaining(start_instr, monitor)

    if not block:
        return []

    seen_blocks = set()
    all_defs = walk_paths(block, start_instr, seen_blocks, model, reg)
    return list(set(all_defs))


def get_high_function(func):
    decomp = DecompInterface()
    decomp.openProgram(currentProgram)
    res = decomp.decompileFunction(func, 60, ConsoleTaskMonitor())
    if res.decompileCompleted():
        return res.getHighFunction()
    return None

def is_constant_varnode(vnode):
    return vnode.isConstant()

def get_varnode_value(varnode):
    return varnode.getOffset()

def apply_operation(opcode, lhs, rhs):
    if lhs is None or rhs is None:
        return None
    if opcode == PcodeOp.INT_ADD:
        return lhs + rhs
    elif opcode == PcodeOp.INT_SUB:
        return lhs - rhs
    elif opcode == PcodeOp.INT_MULT:
        return lhs * rhs
    elif opcode == PcodeOp.INT_AND:
        return lhs & rhs
    elif opcode == PcodeOp.INT_OR:
        return lhs | rhs
    elif opcode == PcodeOp.INT_XOR:
        return lhs ^ rhs
    elif opcode == PcodeOp.INT_LEFT:
        return lhs << rhs
    elif opcode == PcodeOp.INT_RIGHT:
        return lhs >> rhs
    return None


def resolve_syscall(instr_addr, reg_name, visited=None):
    if visited is None:
        visited = set()
    if instr_addr in visited:
        #print("[+] Instr at ", hex(rebase(instr_addr)), " already visited..returning NONE")
        return None
    visited.add(instr_addr)

    instr = getInstructionAt(instr_addr)
    if not instr:
        print("[-] No instruction at ", hex(instr_addr.getOffset()))
        return None

    reg = currentProgram.getRegister(reg_name)

    for op in instr.getPcode():
        out = op.getOutput()
        inputs = op.getInputs()
        opcode = op.getOpcode()

        if out and out.isRegister():
            out_reg = currentProgram.getRegister(out.getAddress(), out.getSize())
            #print("[+] Out reg ", out_reg, reg.contains(out_reg))
            if reg.contains(out_reg) or out_reg.contains(reg):
                inp1, inp2 = [], []

                # Input 1
                if len(inputs) < 1:
                    return None
                if opcode in (PcodeOp.INT_SUB, PcodeOp.INT_XOR) and len(inputs) > 1 and inputs[0].isRegister() and inputs[1].isRegister():
                    inp_reg1 = currentProgram.getRegister(inputs[0].getAddress(), inputs[0].getSize())
                    inp_reg2 = currentProgram.getRegister(inputs[1].getAddress(), inputs[1].getSize())
                    if inputs[0].getAddress() == inputs[1].getAddress():
                        #print("[+] SUB/XOR op found with same reg as operand:", inp_reg1, inp_reg2)
                        return [0]

                if inputs[0].isConstant():
                    inp1.append(inputs[0].getOffset())
                elif inputs[0].isRegister():
                    inp_reg = currentProgram.getRegister(inputs[0].getAddress(), inputs[0].getSize())
                    reg_defs = get_pathwise_reg_definitions(instr_addr, inp_reg.getName())
                    for d in reg_defs:
                        #print("[+] Resolving ", inp_reg.getName(), " at ", hex(rebase(d)))
                        val = resolve_syscall(d, inp_reg.getName(), visited)
                        if val is not None:
                            inp1.extend(val)
                else:
                    return None

                if opcode == PcodeOp.COPY:
                    #print("[+] COPY op at ", hex(rebase(instr_addr)), " source ", inp1)
                    return inp1

                # Input 2
                if opcode in (
                    PcodeOp.INT_ADD, PcodeOp.INT_SUB, PcodeOp.INT_MULT,
                    PcodeOp.INT_AND, PcodeOp.INT_OR, PcodeOp.INT_XOR,
                    PcodeOp.INT_LEFT, PcodeOp.INT_RIGHT
                ):
                    if len(inputs) < 2:
                        return None
                    if inputs[1].isConstant():
                        inp2.append(inputs[1].getOffset())
                    elif inputs[1].isRegister():
                        inp_reg = currentProgram.getRegister(inputs[1].getAddress(), inputs[1].getSize())
                        reg_defs = get_pathwise_reg_definitions(instr_addr, inp_reg.getName())
                        for d in reg_defs:
                            val = resolve_syscall(d, inp_reg.getName(), visited)
                            if val is not None:
                                inp2.extend(val)
                    else:
                        return None

                    res = []
                    for lhs in inp1:
                        for rhs in inp2:
                            val = apply_operation(opcode, lhs, rhs)
                            res.append(val)
                    return res
    return None

def resolve_syscall_wrapper(func):
    listing = currentProgram.getListing()
    syscall_rax_def_list = []
    
    syscall_nums = set()

    for instr in listing.getInstructions(func.getBody(), True):
        if is_direct_cf(instr):
            flows = instr.getFlows()
            for f in flows:
                if f in syscall_wrapper:
                    syscall_addr = instr.getAddress()
                    print("[+] Found syscall wrapper call at ", hex(rebase(syscall_addr)))
                    all_rax_defs = get_pathwise_reg_definitions(syscall_addr, syscall_wrapper[f])
                    syscall_rax_def_list.append((syscall_addr, all_rax_defs, syscall_wrapper[f]))
    if len(syscall_rax_def_list) > 0:
        high_func = get_high_function(func)
        if high_func is None:
            print("[-] Failed to decompile function.")
            return
        for syscall in syscall_rax_def_list:
            syscall_addr = syscall[0]
            print("[+] Resolving syscall num for syscall at ", hex(rebase(syscall_addr)))
            rax_defs = syscall[1]
            reg = syscall[2]
            for defs in rax_defs:
                result = resolve_syscall(defs, reg)
                if result is not None:
                    print("[+] Resolved syscall number ", result)
                    for n in result:
                        syscall_nums.add(n)
                else:
                    print("[!] Could not resolve RAX")

                break

    return syscall_nums

def trace_syscall_rax(func):

    listing = currentProgram.getListing()
    syscall_rax_def_list = []
    
    syscall_nums = set()

    for instr in listing.getInstructions(func.getBody(), True):
        if instr.getMnemonicString().upper() == "SYSCALL":
            syscall_addr = instr.getAddress()
            print("[+] Found syscall at ", hex(rebase(syscall_addr)))
            all_rax_defs = get_pathwise_reg_definitions(syscall_addr, "RAX")
            syscall_rax_def_list.append((syscall_addr, all_rax_defs, "RAX"))


    if len(syscall_rax_def_list) > 0:
        high_func = get_high_function(func)
        if high_func is None:
            print("[-] Failed to decompile function.")
            return
        for syscall in syscall_rax_def_list:
            syscall_addr = syscall[0]
            print("[+] Resolving syscall num for syscall at ", hex(rebase(syscall_addr)))
            rax_defs = syscall[1]
            reg = syscall[2]
            for defs in rax_defs:
                result = resolve_syscall(defs, reg)
                if result is not None:
                    print("[+] Resolved syscall number ", result)
                    for n in result:
                        syscall_nums.add(n)
                else:
                    print("[!] Could not resolve RAX")

                break

    return syscall_nums

import json
import os
from ghidra.util import SystemUtilities

def export_function_info_json(output_path, data):
    with open(output_path, "w") as f:
        json.dump(data, f, indent=4)
    print("[+] Exported to: ", output_path)

all_functions = []

for func in fm.getFunctions(True):
    name = func.getName()
    addr = rebase(func.getEntryPoint())
    at = is_address_taken(func)
    unresolved_icf = has_unresolved_icf(func)
    targets, plt_targets_set = get_call_targets(func)
    print("[+] Function name ", name)
    print("[+] Function address ", hex(addr))
    print("[+] targets ", targets)
    print("[+] address taken ", at)
    print("[+] unresolved icf ", unresolved_icf)
    print("[+] plt targets ", plt_targets_set)
    syscall_list = trace_syscall_rax(func)

    func_info = {
        "name": name,
        "address": addr,
        "call_targets": list(targets),
        "address_taken": at,
        "unresolved_icf": unresolved_icf,
        "plt_targets": list(plt_targets_set),
        "syscall": list(syscall_list)
    }

    all_functions.append(func_info)

for func in fm.getFunctions(True):
    addr = rebase(func.getEntryPoint())
    additional_syscalls = resolve_syscall_wrapper(func)
    if len(additional_syscalls) > 0:
        for fn_data in all_functions:
            if fn_data["address"] == addr:
                syscall_list = fn_data["syscall"]
                syscall_list.extend(additional_syscalls)
                fn_data["syscall"] = syscall_list

export_function_info_json(args[0] + "/functions.json", all_functions)
