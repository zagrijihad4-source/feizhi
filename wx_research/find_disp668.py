"""扫描 Weixin.dll，找所有以 0x668 为位移的内存操作数指令。

用途：定位 [env+0x668]（收藏表情信封里的内容指针/内容对象）的写入点。
capstone 全量线性扫描 179MB 太慢，这里只扫给定 RVA 区间，默认覆盖
发送相关热区（0x1500000-0x1780000）与内容对象构造区（0x3d00000-0x3e00000）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_OP_REG

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
IMAGE_BASE = 0x180000000
DISP = 0x668

DEFAULT_RANGES = [
    (0x01500000, 0x01780000),
    (0x03D00000, 0x03E00000),
    (0x00500000, 0x00600000),
]


def load():
    pe = pefile.PE(str(DLL), fast_load=True)
    data = DLL.read_bytes()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    return pe, data, md


def sec_of(pe, rva):
    for s in pe.sections:
        a = s.VirtualAddress
        b = a + max(s.Misc_VirtualSize, s.SizeOfRawData)
        if a <= rva < b:
            return s
    return None


def rva_to_off(pe, rva):
    s = sec_of(pe, rva)
    if s is None:
        return None
    d = rva - s.VirtualAddress
    if d >= s.SizeOfRawData:
        return None
    return s.PointerToRawData + d


def is_write(insn, op):
    """粗略判断 op 是不是目标（写）操作数：是内存操作数且不是唯一源。
    对 mov 家族：op0 是目标。对 lea：不是写。对 cmp/test：不是写。"""
    m = insn.mnemonic
    if m == "lea":
        return False
    if m in ("cmp", "test", "nop", "push", "call", "jmp", "bt"):
        return False
    return True


def scan(pe, data, md, ranges):
    hits = []
    for lo, hi in ranges:
        off = rva_to_off(pe, lo)
        if off is None:
            continue
        size = hi - lo
        chunk = data[off:off + size]
        for insn in md.disasm(chunk, IMAGE_BASE + lo):
            for i, op in enumerate(insn.operands):
                if op.type != X86_OP_MEM:
                    continue
                if op.mem.disp != DISP:
                    continue
                if op.mem.base == 0 and op.mem.index == 0:
                    continue
                hits.append({
                    "rva": insn.address - IMAGE_BASE,
                    "text": f"{insn.mnemonic} {insn.op_str}",
                    "opidx": i,
                    "write": is_write(insn, op) and i == 0,
                })
    return hits


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    ranges = DEFAULT_RANGES
    if len(sys.argv) > 1:
        ranges = []
        for a in sys.argv[1:]:
            lo, _, hi = a.partition("-")
            ranges.append((int(lo, 16), int(hi, 16)))
    pe, data, md = load()
    hits = scan(pe, data, md, ranges)
    print(f"命中 {len(hits)} 条 [reg+0x{DISP:x}] 内存操作数指令\n")
    for h in hits:
        flag = "写" if h["write"] else " "
        print(f"  {h['rva']:#010x} {flag} {h['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
