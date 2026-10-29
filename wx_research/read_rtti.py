"""从 vtable 反查 MSVC RTTI 类名。

x64 MSVC RTTI 布局（本 PE 实测）：
  vtable[-1]            -> _RTTICompleteObjectLocator*  8 字节【绝对地址】
  COL + 0x04            -> offset                      4 字节
  COL + 0x08            -> cdOffset                    4 字节
  COL + 0x0C            -> TypeDescriptor*             4 字节 RVA
  TypeDescriptor + 0x10 -> 类名字符串 (char[])

注意：vtable[-1] 是 8 字节绝对地址（imagebase + RVA），不是 4 字节 RVA。
依据：dynamic_cast 实现 `0x0664d9fc` 里的 `mov rsi,[rax-8]`（8 字节读）。

用法:
    python read_rtti.py 0x82c02c8 0x83dcc28 0x8755528 ...
"""
from __future__ import annotations

import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
IMAGE_BASE = 0x180000000


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    pe = pefile.PE(str(DLL), fast_load=True)
    data = DLL.read_bytes()

    def off_of(rva):
        for s in pe.sections:
            a = s.VirtualAddress
            b = a + max(s.Misc_VirtualSize, s.SizeOfRawData)
            if a <= rva < b:
                d = rva - s.VirtualAddress
                if d < s.SizeOfRawData:
                    return s.PointerToRawData + d
        return None

    def u32(rva):
        o = off_of(rva)
        if o is None or o + 4 > len(data):
            return None
        return int.from_bytes(data[o:o + 4], "little")

    def u64(rva):
        o = off_of(rva)
        if o is None or o + 8 > len(data):
            return None
        return int.from_bytes(data[o:o + 8], "little")

    def cstr(rva, n=240):
        o = off_of(rva)
        if o is None:
            return None
        end = data.find(b"\0", o, o + n)
        if end < 0:
            end = o + n
        return data[o:end].decode("ascii", "replace")

    def rtti_of(vtable_rva, slot_back=1):
        col_abs = u64(vtable_rva - 8 * slot_back)
        if not col_abs or col_abs < IMAGE_BASE:
            return None
        col = col_abs - IMAGE_BASE
        td = u32(col + 0x0C)
        if not td:
            return None
        nm = cstr(td + 0x10)
        if not nm:
            return None
        return {"vtable": hex(vtable_rva), "col": hex(col), "td": hex(td), "name": nm}

    targets = [int(a, 16) for a in sys.argv[1:]]
    if not targets:
        targets = [0x82C02C8, 0x82C0398, 0x83DCC28, 0x8755528, 0x85265E8,
                   0x82CB8D8, 0x82CB848, 0x82CB658, 0x805E708]

    for t in targets:
        got = None
        for back in range(1, 5):
            r = rtti_of(t, back)
            if r and r["name"].startswith("."):
                r["slot_back"] = back
                got = r
                break
        if got:
            print(f"{t:#010x}  ->  {got['name']}   (COL slot_back={got['slot_back']})")
        else:
            print(f"{t:#010x}  ->  (未找到 RTTI)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
