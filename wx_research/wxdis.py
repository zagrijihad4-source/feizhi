"""精确反汇编 Weixin.dll 的指定 RVA 区域。

为什么不用 r2 / rizin：
    这个 179MB 的 PE 在 r2 -n 模式下寻址不可靠，
    `s <小地址>` 会落到 paddr 语义，`s <imagebase+rva>` 又读到空洞，
    两次结果都与文件字节矛盾。改用 pefile + capstone，结果与文件字节一致。
"""
from __future__ import annotations

import bisect
import sys
from pathlib import Path

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
IMAGE_BASE = 0x180000000

_state = {}


def load():
    if "data" in _state:
        return _state
    pe = pefile.PE(str(DLL), fast_load=True)
    _state["pe"] = pe
    _state["data"] = DLL.read_bytes()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    _state["md"] = md
    return _state


def pdata_index():
    """解析 .pdata，得到按起始 RVA 排序的函数区间表。"""
    st = load()
    if "pdata" in st:
        return st["pdata"]
    pe = st["pe"]
    data = st["data"]
    starts, ends = [], []
    for sec in pe.sections:
        name = sec.Name.rstrip(b"\0").decode("ascii", "replace")
        if name != ".pdata":
            continue
        raw = sec.get_data()
        base = sec.VirtualAddress
        # RUNTIME_FUNCTION: BeginAddress(4) EndAddress(4) UnwindInfoAddress(4)
        for i in range(0, len(raw) - 11, 12):
            b, e = int.from_bytes(raw[i:i + 4], "little"), int.from_bytes(raw[i + 4:i + 8], "little")
            if b == 0 or e <= b:
                continue
            starts.append(b)
            ends.append(e)
        break
    order = sorted(range(len(starts)), key=lambda i: starts[i])
    st["pdata"] = ([starts[i] for i in order], [ends[i] for i in order])
    return st["pdata"]


def find_fn(rva: int):
    """返回包含 rva 的函数 [start, end)，找不到返回 None。"""
    starts, ends = pdata_index()
    i = bisect.bisect_right(starts, rva) - 1
    if i < 0:
        return None
    if starts[i] <= rva < ends[i]:
        return (starts[i], ends[i])
    return None


def rva_to_off(rva: int):
    st = load()
    try:
        return st["pe"].get_offset_from_rva(rva)
    except Exception:
        return None


def read_str(rva: int, maxlen: int = 96) -> str:
    st = load()
    off = rva_to_off(rva)
    if off is None or off < 0:
        return ""
    raw = st["data"][off:off + maxlen]
    s = raw.split(b"\0")[0]
    if not s:
        return ""
    try:
        txt = s.decode("utf-8")
    except UnicodeDecodeError:
        try:
            txt = s.decode("gbk")
        except UnicodeDecodeError:
            return ""
    if not txt:
        return ""
    printable = sum(1 for c in txt if c.isprintable())
    if printable / len(txt) < 0.85:
        return ""
    return txt


def fmt(insn, base: int) -> str:
    note = ""
    for op in insn.operands:
        if op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP:
            tgt = insn.address + insn.size + op.mem.disp
            trva = tgt - base
            s = read_str(trva, 72)
            note = f'   ; "{s}"' if s else f"   ; ->rva {trva:#x}"
            break
        if op.type == X86_OP_IMM and insn.mnemonic in ("call", "jmp"):
            note = f"   ; ->rva {op.imm - base:#x}"
            break
    line = f"{insn.address - base:#010x}  {insn.mnemonic:<8} {insn.op_str}{note}"
    try:
        return line
    except Exception:
        return line


def out(line: str):
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("gbk", "replace").decode("gbk", "replace"))


def disasm(rva: int, count: int, base: int = IMAGE_BASE, entry: bool = False):
    st = load()
    md = st["md"]
    if entry:
        fn = find_fn(rva)
        if fn:
            out(f"; 命中点 {rva:#x} 属于函数 [{fn[0]:#x}, {fn[1]:#x})，从入口反汇编")
            rva = fn[0]
    off = rva_to_off(rva)
    if off is None or off < 0:
        out(f"RVA {rva:#x} 无法映射")
        return
    code = st["data"][off: off + count * 16 + 128]
    n = 0
    for insn in md.disasm(code, base + rva):
        out(fmt(insn, base))
        n += 1
        if n >= count:
            break


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "str":
        rva = int(argv[1], 16)
        out(f"{rva:#x}: {read_str(rva)!r}")
        return 0
    if cmd == "fn":
        for a in argv[1:]:
            rva = int(a, 16)
            fn = find_fn(rva)
            if fn:
                out(f"{rva:#010x} -> fn [{fn[0]:#010x}, {fn[1]:#010x})  size={fn[1]-fn[0]}")
            else:
                out(f"{rva:#010x} -> 不在任何 .pdata 函数内")
        return 0
    if cmd == "entry":
        rva = int(argv[1], 16)
        count = int(argv[2]) if len(argv) > 2 else 60
        disasm(rva, count, entry=True)
        return 0
    rva = int(argv[0], 16)
    count = int(argv[1]) if len(argv) > 1 else 40
    disasm(rva, count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
