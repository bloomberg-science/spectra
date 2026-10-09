# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import angr
import sys
import archinfo
import angr.analyses.reaching_definitions.dep_graph as dep_graph
from capstone.x86_const import X86_GRP_CALL, X86_GRP_JUMP
from multiprocessing import Queue
from collections import deque

external_syscall_function = {}

def get_defs(proj, func, target_ins, reg):
    rax_defs = []
    print("[+] getting defs: ", hex(target_ins), reg)
    try:
        rda = proj.analyses.ReachingDefinitions(
            subject=func,
            func_graph=func.graph,
            cc=func.calling_convention,
            observation_points=[("insn", target_ins, 0)],
            dep_graph=dep_graph.DepGraph()
        )
        result = rda.observed_results[("insn", target_ins, 0)]
        rax_offset = proj.arch.registers[reg][0]
        defs = result.get_register_definitions(rax_offset, 8)
        rax_defs.extend(defs)

    except Exception as e:
        print(f"[!] RDA failed: {e}")
    
    print("[+] returning defs: ", rax_defs)
    return rax_defs

from queue import Empty

ARG_REGS = {"rdi", "rsi", "rcx", "rdx", "r8", "r9"}

def normalize_reg(name: str) -> str:
    name = name.strip().lower()
    # quick width-normalization for x86-64
    m = {
        "eax":"rax","ax":"rax","al":"rax","ah":"rax",
        "ebx":"rbx","bx":"rbx","bl":"rbx","bh":"rbx",
        "ecx":"rcx","cx":"rcx","cl":"rcx","ch":"rcx",
        "edx":"rdx","dx":"rdx","dl":"rdx","dh":"rdx",
        "edi":"rdi","di":"rdi","dil":"rdi",
        "esi":"rsi","si":"rsi","sil":"rsi",
        "esp":"rsp","sp":"rsp","spl":"rsp",
        "ebp":"rbp","bp":"rbp","bpl":"rbp",
    }
    return m.get(name, name)


def resolve(q, proj, func, cfg):
    syscall_set = set()
    visited = set()   # (ins_addr, reg) pairs you’ve processed
    
    while q:
    
        target_ins, reg = q.popleft()
        #reg = normalize_reg(reg)
    
        if (target_ins, reg) in visited:
            continue
        visited.add((target_ins, reg))
    
        print(f"[+] Analyzing at 0x{target_ins:x}, reg={reg} ...")
        rax_defs = get_defs(proj, func, target_ins, reg)
        print("[+] defs: ", rax_defs)
    
        if not rax_defs:
            print("[+] Possibly syscall wrapper:", hex(func.addr), "arg reg", reg)
            external_syscall_function[func.addr] = reg
            if reg in ARG_REGS:
                print("[+] Syscall wrapper function:", hex(func.addr), "arg reg", reg)
            continue
    
        found = False
        for d in rax_defs:
            def_addr = getattr(d.codeloc, "ins_addr", None)
            if def_addr is None:
                continue
    
            print(f"[+] def at {hex(def_addr)}")
            state = proj.factory.blank_state(addr=def_addr)
            simgr = proj.factory.simgr(state)
            try:
                simgr.step(num_inst=1)
            except Exception as e:
                print(f"[!] step failed at {hex(def_addr)}: {e}")
                continue
    
            for s in simgr.active:
                try:
                    val = getattr(s.regs, reg)   # e.g., s.regs.rdi
                except AttributeError:
                    continue
    
                if getattr(val, "concrete", False):
                    num = s.solver.eval(val)
                    syscall_set.add(num)
                    print(f"[+] syscall number {num}")
                    found = True
                    break
                else:
                    for var in getattr(val, "variables", []):
                        if var.startswith("reg_"):
                            nxt = var.split("_", 2)[1]  # 'rdi' from 'reg_rdi_0'
                            nxt = normalize_reg(nxt)
                            if (def_addr, nxt) not in visited:
                                print("[*] New tracking reg:", nxt)
                                q.append((def_addr, nxt))
    
        #print("[+] Queue empty?", q.empty())
        #if q.empty():
        #    break

    return syscall_set

def resolve_syscall_wrapper_calls(proj, func, cfg):
    q = deque()
    for block in func.blocks:
        for insn in block.capstone.insns:
            syscall_addr = insn.address
            if "call" in insn.mnemonic or "jmp" in insn.mnemonic or "jmp" in insn.op_str:
                bb_node = cfg.model.get_any_node(block.addr)
                if bb_node is not None:
                    successors = list(cfg.graph.successors(bb_node))
                    for succ in successors:
                        if succ.addr in external_syscall_function:
                            q.append((syscall_addr,external_syscall_function[succ.addr]))
    return resolve(q, proj, func, cfg)

def resolve_syscall(proj, func, cfg):

    arch = proj.arch.name
    syscall_reg = 'rax' if '64' in arch else 'eax'
    syscall_fn_reg = 'rdi' if '64' in arch else 'edi'

    q = deque()

    for block in func.blocks:
        for insn in block.capstone.insns:
            syscall_addr = insn.address
            if insn.mnemonic == 'syscall' or (insn.mnemonic == 'int' and '0x80' in insn.op_str):
                q.append((syscall_addr,syscall_reg))
    
    return resolve(q, proj, func, cfg)
   


def is_address_taken(proj, func_addr):
    refs = list(proj.kb.xrefs.get_xrefs_by_dst(func_addr))
    return len(refs) > 0

def analyze_function(proj, func, cfg):
    call_targets = set()
    plt_targets = set()
    has_unresolved = False
    func_name = func.name if func.name else f"func_{func.addr}"
    for block in func.blocks:
        print(block)
        bb_node = cfg.model.get_any_node(block.addr)
        if block.capstone:
            cf_ins = False
            for insn in block.capstone.insns:
                print(f"[+] {hex(insn.address)}: {insn.mnemonic} {insn.op_str}")
                if "call" in insn.mnemonic or "jmp" in insn.mnemonic or "jmp" in insn.op_str:
                #if X86_GRP_CALL in insn.groups or X86_GRP_JUMP in insn.groups:
                    #insn_addr = insn.address
                    #cfg_node = cfg.model.get_any_node(insn_addr)
                    cf_ins = True
                    if bb_node is not None:
                        successors = list(cfg.graph.successors(bb_node))
                        if not successors:
                            print("No successors")
                            has_unresolved = True
                        for succ in successors:
                            print(
                                "succ -> ", hex(succ.addr), succ.name, 
                                " succ fn: ", hex(succ.function_address),
                                " current fn: ", hex(func.addr),
                                " current node fn: ", hex(bb_node.function_address)
                            )
                            if succ.function_address != func.addr:
                                if succ.name is not None:
                                    if succ.name.startswith("Unresolvable"):
                                        has_unresolved = True
                                        continue
                                    sym = proj.loader.main_object.get_symbol(succ.name)
                                    if sym is not None:
                                        if sym.is_import:
                                            plt_targets.add(succ.name)
                                            print("PLT target: ", succ.name)
                                            if succ.name == "syscall":
                                                print("syscall wrapper: ", hex(func.addr))
                                                external_syscall_function[func.addr] = "rdi"
                                        else:
                                            print("call target: ", succ.name)
                                            if succ.name == "syscall":
                                                print("syscall wrapper: ", hex(succ.addr))
                                                external_syscall_function[succ.addr] = "rdi"
                                            call_targets.add(sym.rebased_addr)
                                    else:
                                        call_targets.add(succ.addr)
                                else:
                                    call_targets.add(succ.addr)
                    else:
                        print("could not get CFG node")
                        has_unresolved = True


            if cf_ins == False:
                if bb_node is not None:
                    successors = list(cfg.graph.successors(bb_node))
                    if not successors:
                        print("[+] No succ for bb: ", hex(block.addr))
                    else:
                        for succ in successors:
                            #print(
                            #    "succ -> ", hex(succ.addr), succ.name, 
                            #    " succ fn: ", hex(succ.function_address),
                            #    " current fn: ", hex(func.addr),
                            #    " current node fn: ", hex(bb_node.function_address)
                            #)
                            if succ.function_address != func.addr:
                                call_targets.add(succ.addr)

        else:
            print(" No capstone available")

    syscall_list = resolve_syscall(proj, func, cfg)

    return {
        "address": func.addr,
        "name": func_name,
        "address_taken": is_address_taken(proj, func.addr),
        "call_targets": sorted(call_targets),
        "plt_targets": sorted(plt_targets),
        "unresolved_icf": has_unresolved,
        "syscall_list": syscall_list
    }

def analyze_binary(binary_path, known_funcs = []):
    external_syscall_function.clear()
    proj = angr.Project(binary_path, load_options={'auto_load_libs':False}, main_opts={'base_addr': 0})

    print(f"[+] Analyzing binary {binary_path}...")
    cfg = None
    if len(known_funcs) > 0:
        cfg = proj.analyses.CFGFast(normalize=True, detect_tail_calls=True, function_starts=known_funcs)
    else:
        cfg = proj.analyses.CFGFast(normalize=True, detect_tail_calls=True)

    fn_info = []

    for addr, func in sorted(cfg.kb.functions.items()):
        print("Analyzing function: ", hex(addr))
        info = analyze_function(proj, func, cfg)
        print(info)
        fn_info.append(info)

    for info in fn_info:
        func = cfg.kb.functions[info["address"]]
        syscall_set = resolve_syscall_wrapper_calls(proj, func, cfg)
        info["syscall_list"].update(syscall_set)

    return fn_info

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python extract_syscall.py <binary>")
    else:
        analyze_binary(sys.argv[1])
