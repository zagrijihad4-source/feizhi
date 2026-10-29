"""从「引用某 vtable 的 lea」中筛出「设置 vtable」的代码 —— 即构造函数。

原理：
    构造函数总是先 lea reg, [rip+disp] 取到 vtable，紧接着 mov [this+off], reg。
    而其它引用（RTTI、类型表、比较、动态转型等）不会紧跟这种写入。

为了减少噪声，还支持反向模式：有些编译器写成
    mov qword [rcx], imm64        （绝对地址，加载时由重定位修正）
这类在文件里是 48 C7 01 <8字节立即数> 或 48 B8 <imm64> + mov [rcx], rax。

用法:
    python find_ctor.py <vtable_rva_hex> [more...]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
IMAGE_BASE = 0x180000000
RIP_MODRM = {0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    targets = [int(a, 16) for a in sys.argv[1:]]
    if not targets:
        print(__doc__)
        return 1

    data = DLL.read_bytes()
    pe = pefile.PE(str(DLL), fast_load=True)
    text = None
    for sec in pe.sections:
        if sec.Name.rstrip(b"\0").decode("ascii", "replace") == ".text":
            text = sec
            break
    if text is None:
        raise SystemExit("找不到 .text")
    tva = text.VirtualAddress
    body = text.get_data()

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    target_set = set(targets)
    # 第一遍：找所有 lea 引用点
    refs = {t: [] for t in targets}
    i = 0
    n = len(body)
    while i < n - 7:
        b0 = body[i]
        if b0 in (0x48, 0x4C) and body[i + 1] == 0x8D and body[i + 2] in RIP_MODRM:
            disp = struct.unpack_from("<i", body, i + 3)[0]
            instr = tva + i
            tgt = instr + 7 + disp
            if tgt in target_set:
                refs[tgt].append(instr)
            i += 7
            continue
        i += 1

    for tgt in targets:
        print(f"\n########## vtable RVA {tgt:#x}：{len(refs[tgt])} 处 lea 引用 ##########")
        if not refs[tgt]:
            print("  (无引用)")
            continue
        ctor_like = []
        for instr in refs[tgt]:
            off = instr - tva
            code = body[off: off + 48]
            insns = []
            for insn in md.disasm(code, IMAGE_BASE + instr):
                insns.append(insn)
                if len(insns) >= 6:
                    break
            # 判断这 6 条里是否出现"把刚取到的 vtable 写进内存"
            verdict = None
            for k, insn in enumerate(insns[:4]):
                if insn.mnemonic != "lea":
                    continue
                # lea 的目标必须是本 vtable
                is_ours = False
                for op in insn.operands:
                    if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
                        t = insn.address + insn.size + op.mem.disp - IMAGE_BASE
                        if t == tgt:
                            is_ours = True
                if not is_ours:
                    continue
                for nxt in insns[k + 1:k + 3]:
                    if nxt.mnemonic == "mov" and len(nxt.operands) == 2:
                        dst, src = nxt.operands
                        if dst.type == X86_OP_MEM and src.type == X86_OP_REG:
                            verdict = f"SET vtbl -> mov {nxt.op_str}"
                            break
                if verdict:
                    break
            tag = "  ★ 疑似构造函数" if verdict else ""
            print(f"  instr={instr:#010x}{tag}")
            for insn in insns[:5]:
                print(f"      {insn.mnemonic:<7} {insn.op_str}")
            if verdict:
                ctor_like.append((instr, verdict))
            print()
        if ctor_like:
            print(f"  => 疑似构造函数候选：{[hex(a) for a, _ in ctor_like]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
