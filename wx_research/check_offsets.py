"""核对 wx_bridge_offsets.h 里的 offset 到底是「函数入口」还是别的东西。

手段：直接读文件字节 + 解引用 vtable。
不做任何猜测，只看数据。
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")

# 来自 wx_bridge_offsets.h
OFFS = {
    "DOADDMSG (known-good)": 0x166A6BF,
    "SEND_CALL1_TEXT": 0x6A35B0,
    "SEND_CALL2": 0xDB40,
    "SEND_CALL3": 0x160EBE0,
}
# .rdata 里的 vtable 指针
VTABLES = {
    "SEND_HC1_TEXT (msg+0)": 0x805E4E8,
    "CALL2_HC1": 0x83661E8,
    "CALL2_HC2": 0x8366128,
    "CALL2_HC3": 0x8366068,
}
# 对这些入口地址，前后各看几个字节，判断是否指向指令中间
NEIGHBOR = {"SEND_CALL1_TEXT": 0x6A35B0, "SEND_CALL2": 0xDB40, "SEND_CALL3": 0x160EBE0}


def parse_pe_sections(data: bytes):
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    num_sec = struct.unpack_from("<H", data, pe_off + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe_off + 20)[0]
    sec_off = pe_off + 24 + opt_size
    out = []
    for i in range(num_sec):
        o = sec_off + i * 40
        name = data[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, o + 8)
        out.append((name, va, vsize, rawptr, rawsize))
    return out


def rva_to_off(sections, rva):
    for _n, va, vsize, rawptr, rawsize in sections:
        if va <= rva < va + max(vsize, rawsize):
            off = rawptr + (rva - va)
            if off < rawptr + rawsize:
                return off
    return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    data = DLL.read_bytes()
    sections = parse_pe_sections(data)

    print("=== 1) offset 处原始字节 ===")
    for name, rva in OFFS.items():
        off = rva_to_off(sections, rva)
        if off is None:
            print(f"{name:<24} RVA={rva:#x} 未映射")
            continue
        b = data[off:off + 16]
        print(f"{name:<24} RVA={rva:#010x} off={off:#010x}  {' '.join(f'{x:02X}' for x in b)}")

    print()
    print("=== 2) 入口附近对齐检查（看是否落在指令中间）===")
    for name, rva in NEIGHBOR.items():
        off = rva_to_off(sections, rva)
        if off is None:
            continue
        pre = data[off - 4:off]
        post = data[off:off + 12]
        print(f"{name}:")
        print(f"  前置4字节 {' '.join(f'{x:02X}' for x in pre)}")
        print(f"  该地址起 {' '.join(f'{x:02X}' for x in post)}")

    print()
    print("=== 3) vtable 解引用（.rdata 处的函数指针）===")
    for name, rva in VTABLES.items():
        off = rva_to_off(sections, rva)
        if off is None:
            print(f"{name:<24} RVA={rva:#x} 未映射")
            continue
        print(f"{name} @RVA {rva:#x}")
        for i in range(6):
            raw = data[off + i * 8: off + i * 8 + 8]
            if len(raw) < 8:
                break
            ptr = struct.unpack_from("<Q", raw)[0]
            # vtable 槽位通常是 RVA 或绝对地址；两种都打印
            note = ""
            if ptr < 0x100000000:
                sec = next((s[0] for s in sections
                            if s[1] <= ptr < s[1] + max(s[2], s[4])), "?")
                note = f"-> 作为RVA 落在 {sec}"
            print(f"   [{i}] {ptr:#018x} {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
