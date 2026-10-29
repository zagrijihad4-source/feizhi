"""扫描 Weixin.dll 里所有「mov ecx, <size> ; call operator_new」模式。

用途：定位某个大小的对象由哪些代码分配。
     已知 0x64A7D1C = operator new(size_t)，所以模式为
         B9 <imm32>            mov ecx, imm32      (5 字节)
         E8 <rel32>            call rel32          (5 字节，目标 = 0x64A7D1C)
     也兼容 `mov r8d, imm32`(41 B8 imm32) 等其它寄存器形式。

用法:
    python find_alloc_1b0.py 0x1b0            # 找 0x1B0 的分配点
    python find_alloc_1b0.py 0x1b0 0x698 0x108
"""
from __future__ import annotations

import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
IMAGE_BASE = 0x180000000
OPNEW = 0x64A7D1C

# mov ecx, imm32 / mov r8d, imm32 / mov edx, imm32 ... → 前缀 + 5 字节
MOV_IMM_PREFIXES = {
    b"\xb9": "ecx",
    b"\xba": "edx",
    b"\xb8": "eax",
    b"\x41\xb8": "r8d",
    b"\x41\xb9": "r9d",
    b"\x41\xba": "r10d",
    b"\x41\xbb": "r11d",
}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    sizes = [int(a, 16) for a in sys.argv[1:]] or [0x1B0]

    pe = pefile.PE(str(DLL), fast_load=True)
    data = DLL.read_bytes()

    # .text 段
    text = None
    for s in pe.sections:
        name = s.Name.rstrip(b"\0").decode("ascii", "replace")
        if name == ".text":
            text = s
            break
    if text is None:
        print("找不到 .text")
        return 1
    base_rva = text.VirtualAddress
    off = text.PointerToRawData
    size = text.SizeOfRawData
    blk = data[off:off + size]

    targets = set(sizes)
    hits = []
    # 用 bytes.find 定位候选，避免 102MB 逐字节循环
    for sz in targets:
        for pref, reg in MOV_IMM_PREFIXES.items():
            needle = pref + sz.to_bytes(4, "little")
            start = 0
            while True:
                i = blk.find(needle, start)
                if i < 0:
                    break
                start = i + 1
                p = i + len(pref)
                q = p + 4
                for skip in range(0, 4):
                    r = q + skip
                    if r + 5 > len(blk):
                        break
                    if blk[r] != 0xE8:
                        continue
                    rel = int.from_bytes(blk[r + 1:r + 5], "little", signed=True)
                    call_rva = base_rva + r
                    dst = call_rva + 5 + rel
                    if dst == OPNEW:
                        hits.append((base_rva + i, sz, reg, call_rva))
                    break
    hits.sort()

    print(f"扫描 .text（{size/1024/1024:.1f} MB），尺寸 {[hex(x) for x in sizes]}")
    print(f"命中 {len(hits)} 处 «mov <reg>, size ; call operator_new»\n")
    for rva, imm, reg, call_at in hits:
        print(f"  {rva:#010x}  mov {reg}, {imm:#x}   → call@ {call_at:#010x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
