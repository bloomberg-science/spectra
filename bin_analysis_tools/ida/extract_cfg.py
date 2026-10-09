# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

"""
summary: produce disassembly listing for the entire file

description:
  automate IDA to perform auto-analysis on a file and,
  once that is done, produce a .lst file with the disassembly.

  Run like so:

        ida -A "-S...path/to/produce_lst_file.py" <binary-file>

  where:

    * -A instructs IDA to run in non-interactive mode
    * -S holds a path to the script to run (note this is a single token;
         there is no space between '-S' and its path.)

level: beginner
"""

import ida_auto
import ida_fpro
import ida_ida
import ida_loader
import ida_pro
import idautils
import idc
import idaapi
import ida_funcs
import ida_xref
import ida_bytes
import ida_name
import ida_search
import ida_ua
import ida_idp
import ida_entry
import ida_nalt
import traceback
import json
import ida_regfinder
import ida_idp

ida_auto.auto_wait() # wait for end of auto-analysis
logf = open("/tmp/ida/ida.log", "w")
rax_idx = ida_idp.str2reg("rax")
rdi_idx = ida_idp.str2reg("rdi")

syscall_wrapper = {}

def is_address_taken(func_ea):
    # Step 1: Check data refs (e.g., function ptrs in .data)
    if list(idautils.DataRefsTo(func_ea)):
        logf.write("Data refs found: " + idc.get_func_name(func_ea) + "\n") 
        return True

    # Step 2: Scan code for direct immediates (mov rax, func_ea)
    #for seg_start in idautils.Segments():
    #    seg_end = idc.get_segm_end(seg_start)
    #    ea = seg_start
    #    while ea < seg_end:
    #        if idc.is_code(idc.get_full_flags(ea)):
    #            insn = ida_ua.insn_t()
    #            if ida_ua.decode_insn(insn, ea):
    #                for op in insn.ops:
    #                    if op.type == ida_ua.o_imm and op.value == func_ea:
    #                        logf.write("Imm operand found for " + idc.get_func_name(func_ea) + " at " + str(hex(ea)) + "\n") 
    #                        return True
    #                    
    #                    # Step 3: Check RIP-relative displacement loads
    #                    if op.type == ida_ua.o_displ and op.reg == ida_idp.str2reg("rip"):
    #                        addr = idc.get_operand_value(ea, op.n)
    #                        # Try to read a pointer at that memory location
    #                        ptr = ida_bytes.get_qword(addr)
    #                        if ptr == func_ea:
    #                            logf.write("RIP relative operand found for " + idc.get_func_name(func_ea) + " at " + str(hex(ea)) + "\n") 
    #                            return True
    #        ea = idc.next_head(ea, seg_end)

    return False


def resolve_reg(ea, reg):
    return ida_idp.ph_find_reg_value(ea, reg)
    #rvi = ida_regfinder.reg_value_info_t()
    #if ida_regfinder.find_reg_value_info(rvi, ea, reg, 10):
    #    return rvi.value  # actual constant value
    #else:
    #    logf.write("[+] Reg tracker not supported\n")
    #return None

def resove_syscall_wrapper(func_ea):
    syscall_list = set()
    for ea in idautils.FuncItems(func_ea):
        mnem = idc.print_insn_mnem(ea).lower()
        if mnem in ['call', 'jmp']:
            op = idc.get_operand_type(ea, 0)
            if op in [idc.o_near, idc.o_far]:
                target = idc.get_operand_value(ea, 0)
                if target in syscall_wrapper:
                    logf.write("[+] call to syscall wrapper " + str(hex(ea)) + "->" + str(hex(target)) + "\n")
                    val = resolve_reg(ea, syscall_wrapper[target])
                    if val is not None:
                        syscall_list.add(val)
                        logf.write("[+] Syscall at " + str(hex(ea)) + ": RDI = " + str(hex(val)) + "\n")
                    else:
                        logf.write("[+] Syscall at " + str(hex(ea)) + ": could not resolve RDI\n")

    return syscall_list

def get_syscall_list(func_ea):
    syscall_list = set()
    for ea in idautils.FuncItems(func_ea):
        mnem = idc.print_insn_mnem(ea).lower()
        if mnem == "syscall":
            val = resolve_reg(ea, rax_idx)
            if val is not None:
                syscall_list.add(val)
                logf.write("[+] Syscall at " + str(hex(ea)) + ": RAX = " + str(hex(val)) + "\n")
            else:
                logf.write("[+] Syscall at " + str(hex(ea)) + ": could not resolve RAX\n")

    return syscall_list

def get_resolved_icf_targets(ea):
    """Return list of resolved targets (if IDA added xrefs)"""
    return list(idautils.CodeRefsFrom(ea, 0))  # 0 = don’t follow code flow

def is_outside_text(func_ea):
    segname = idc.get_segm_name(func_ea)
    return segname not in [".text", ".text.startup", "__text"]


def normalize_function_name(name):
    for prefix in ['__imp_', '_imp__', 'j_', 'nullsub_']:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def get_call_targets(func_ea):
    targets = set()
    plt_targets = set()
    unresolved_indirect = False
    """Get all call/jump targets inside the function"""

    logf.write("Getting targets for fn: " + idc.get_func_name(func_ea) + "\n") 
    for head in idautils.FuncItems(func_ea):
        if not idc.is_code(idc.get_full_flags(head)):
            continue

        mnem = idc.print_insn_mnem(head).lower()
        #logf.write("ins: " + mnem + "\n")
        if mnem in ['call', 'jmp']:
            op = idc.get_operand_type(head, 0)

            if op in [idc.o_near, idc.o_far]:
                target = idc.get_operand_value(head, 0)
                logf.write("Checking direct target: " + idc.get_func_name(func_ea) + "-->" + str(hex(target)) + "\n") 
                if ida_funcs.get_func(target):
                    tgt_fn_name = normalize_function_name(idc.get_func_name(target))
                    if tgt_fn_name == "syscall":
                        logf.write("Adding syscall wrapper function at " + str(hex(target)) + "\n")
                        syscall_wrapper[target] = rdi_idx
                    targets.add(target)

            else:
                # Indirect (e.g., call rax, jmp [rax], etc.)

                ind_targets = get_resolved_icf_targets(head)
                if len(ind_targets) <= 0:
                    unresolved_indirect = True
                    logf.write("Unresolved ICF at: " + str(hex(head)) + "\n") 
                for t in ind_targets:
                    logf.write("Checking indirect target: " + idc.get_func_name(func_ea) + "-->" + str(hex(t)) + ":" + idc.get_func_name(t) + "\n")

                    if ida_funcs.get_func(t):
                        if is_outside_text(t):
                            logf.write("Indirect function outside text segment\n")
                            plt_fn_name = normalize_function_name(idc.get_func_name(t))
                            plt_targets.add(plt_fn_name)
                            if plt_fn_name == "syscall":
                                logf.write("Adding syscall wrapper function at " + str(hex(func_ea)) + "\n")
                                syscall_wrapper[func_ea] = rdi_idx
                        else:
                            targets.add(t)
                    else:
                        logf.write("No function for indirect target " + idc.get_func_name(t) + "\n")


    return targets, plt_targets, unresolved_indirect

def describe_function(func_ea):
    name = idc.get_func_name(func_ea)
    addr = hex(func_ea)
    targets, plt_targets, unresolved_indirect = get_call_targets(func_ea)
    is_taken = is_address_taken(func_ea)
    syscall_set = get_syscall_list(func_ea)
    
    return {
        "name": name,
        "address": int(addr,0),
        "call_targets": list(targets),
        "plt_targets": list(plt_targets),
        "syscall": list(syscall_set),
        "unresolved_icf": unresolved_indirect,
        "address_taken": is_taken
    }

    #print(f"\nFunction: {name}")
    #print(f"  Address: {addr}")
    #print(f"  Call Targets:")
    #for t in targets:
    #    print(f"    - {idc.get_func_name(t)} @ {hex(t)}")
    #print(f"  PLT/External Targets:")
    #for e in plt_targets:
    #    print(f"    - {ida_name.get_name(e)} @ {hex(e)}")
    #print(f"  Address Taken: {'yes' if is_taken else 'no'}")
    #print(f"  Has Unresolved Indirect CF: {'yes' if unresolved_indirect else 'no'}")


# ---- Main loop ----
# derive output file name
idb_path = ida_loader.get_path(ida_loader.PATH_TYPE_IDB)
idb_path = idb_path.removesuffix(".i64")
#lst_path = "%s.lst" % idb_path
json_path = "%s.json" % idb_path
#with open(lst_path, "w") as f:
all_data = []
for func_ea in idautils.Functions():
    try:
        data = describe_function(func_ea)
        all_data.append(data)

        #f.write("-----------------------\n")
        #f.write("name: " + data["name"] + "\n")
        #f.write("address: " + data["address"] + "\n")
        #call_targets = data["call_targets"]
        #tgt_line = "targets: " + ", ".join(str(x) for x in call_targets) + "\n"
        #f.write(tgt_line)
        #plt_targets = data["plt_targets"]
        #plt_line = "plt_targets: " + ", ".join(x for x in plt_targets) + "\n"
        #f.write(plt_line)
        #f.write("unresolved icf: " + str(data["unresolved_icf"]) + "\n")
        #f.write("address taken: " + str(data["address_taken"]) + "\n")
        #f.write("-----------------------\n")

    except Exception as e:
        with open("/tmp/ida/ida_error.log", "w") as ef:
            ef.write("Error occurred:\n")
            ef.write(str(e) + "\n")
            ef.write(traceback.format_exc())

for d in all_data:
    try:
        syscall_set = resove_syscall_wrapper(d["address"])
        new_syscall_list = d["syscall"]
        new_syscall_list.extend(syscall_set)
        d["syscall"] = new_syscall_list
    except Exception as e:
        with open("/tmp/ida/ida_error.log", "w") as ef:
            ef.write("Error occurred:\n")
            ef.write(str(e) + "\n")
            ef.write(traceback.format_exc())
    
#f.close()
with open(json_path, "w") as f:
    json.dump(all_data, f, indent=4)
f.close()

logf.close()
ida_pro.qexit(0)
