"""扫描 Weixin.dll 的 .text，反查对某个 RVA 的引用（xref）。

支持三种引用形式：
    E8 rel32            call
    E9 rel32            jmp
    48/4C 8D modrm rel32   lea rip-relative

做法是全段字节模式扫描 + 强约束过滤（目标必须精确等于待查 RVA）。
随机 4 字节恰好等于特定 rel32 的概率极低，所以误报可忽略。

用法:
    python wxref.py <rva_hex> [more...]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
RIP_MODRM = {0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D}


def load():
    data = DLL.read_bytes()
    pe = pefile.PE(str(DLL), fast_load=True)
    text = None
    for sec in pe.sections:
        name = sec.Name.rstrip(b"\0").decode("ascii", "replace")
        if name == ".text":
            text = sec
            break
    if text is None:
        raise SystemExit("找不到 .text")
    va = text.VirtualAddress
    raw = text.get_data()
    return data, va, raw


def scan(text_va: int, body: bytes, targets: set[int]):
    """返回 {target: [(kind, instr_rva), ...]}"""
    hits = {t: [] for t in targets}
    n = len(body)
    i = 0
    while i < n - 7:
        b0 = body[i]
        if b0 == 0xE8 or b0 == 0xE9:
            disp = struct.unpack_from("<i", body, i + 1)[0]
            instr = text_va + i
            tgt = instr + 5 + disp
            if tgt in hits:
                hits[tgt].append(("call" if b0 == 0xE8 else "jmp", instr))
            i += 5
            continue
        if b0 in (0x48, 0x4C) and body[i + 1] == 0x8D and body[i + 2] in RIP_MODRM:
            disp = struct.unpack_from("<i", body, i + 3)[0]
            instr = text_va + i
            tgt = instr + 7 + disp
            if tgt in hits:
                hits[tgt].append(("lea", instr))
            i += 7
            continue
        i += 1
    return hits


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    targets = {int(a, 16) for a in sys.argv[1:]}
    print(f"扫描 .text 找 {len(targets)} 个目标的引用 ...")
    _data, text_va, body = load()
    print(f".text VA={text_va:#x} size={len(body)/1048576:.1f}MB")
    hits = scan(text_va, body, targets)
    for t in sorted(targets):
        lst = hits[t]
        print(f"\n=== {t:#010x} : {len(lst)} 处引用 ===")
        for kind, instr in lst[:40]:
            print(f"  {kind:<5} 指令RVA={instr:#010x}")
        if len(lst) > 40:
            print(f"  ... 还有 {len(lst)-40} 处")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
