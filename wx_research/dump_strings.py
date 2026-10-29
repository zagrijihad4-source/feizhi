"""dump 指定 RVA 区域内的所有可打印字符串。

用途：protobuf descriptor 的字段名通常连续存放，dump 一段就能看到整族字段，
      便于判断某个消息类型有哪些字段、以及消息类型的划分。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
PAT = re.compile(rb"[\x20-\x7e]{4,}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    rva = int(sys.argv[1], 16)
    before = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x400
    after = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x400
    data = DLL.read_bytes()
    pe = pefile.PE(str(DLL), fast_load=True)
    for sec in pe.sections:
        va, vsz = sec.VirtualAddress, sec.Misc_VirtualSize
        rp, rs = sec.PointerToRawData, sec.SizeOfRawData
        if va <= rva < va + max(vsz, rs):
            off = rp + (rva - va)
            start = max(rp, off - before)
            end = min(rp + rs, off + after)
            chunk = data[start:end]
            print(f"区域 rva {rva - (off - start):#x} .. {rva + (end - off):#x}  "
                  f"({len(chunk)} 字节)")
            for m in PAT.finditer(chunk):
                s = m.group().decode("ascii", "replace")
                pos = rva - (off - start) + m.start()
                mark = "  <<<" if abs(m.start() - (off - start)) < 40 else ""
                print(f"  rva={pos:#010x} {s!r}{mark}")
            return 0
    print("RVA 未映射")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
