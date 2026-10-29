"""按 RVA dump 原始字节（hex + ASCII），用于快速核对结构体布局。

用法:
    python dump_rva.py 0x83dcc50 48
    python dump_rva.py 0x83dcc50 48 0x8755500 64
"""
from __future__ import annotations

import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")


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
                    return s.PointerToRawData + d, s.Name.rstrip(b"\0").decode("ascii", "replace")
        return None, None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        rva = int(args[i], 16)
        n = int(args[i + 1]) if i + 1 < len(args) and not args[i + 1].startswith("0x") else 64
        i += 2 if (i + 1 < len(args) and not args[i + 1].startswith("0x")) else 1
        off, sec = off_of(rva)
        if off is None:
            print(f"{rva:#010x}: 无法映射")
            continue
        blk = data[off:off + n]
        print(f"{rva:#010x} [{sec}] {n} bytes:")
        for j in range(0, len(blk), 16):
            row = blk[j:j + 16]
            hexs = " ".join(f"{b:02x}" for b in row)
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
            print(f"  +{j:04x}  {hexs:<48}  {asc}")
        # 8 字节 qword 解读，便于看指针
        print("   qwords:", " ".join(
            f"[{j:#x}]={int.from_bytes(blk[j:j+8],'little'):#x}"
            for j in range(0, min(len(blk) - 7, 48), 8)))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
