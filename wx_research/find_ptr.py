"""在 Weixin.dll 里搜索指定函数指针值的出现位置。

用途：函数零处直接 call 引用时，说明它是通过 vtable / 函数指针调用的。
      在文件里搜 `image_base + rva` 形式的 8 字节，命中处即为虚表槽位。
"""
from __future__ import annotations

import struct
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
    rvas = [int(a, 16) for a in sys.argv[1:]] or [0x21806A0]
    data = DLL.read_bytes()
    pe = pefile.PE(str(DLL), fast_load=True)
    secs = []
    for sec in pe.sections:
        name = sec.Name.rstrip(b"\0").decode("ascii", "replace")
        secs.append((name, sec.VirtualAddress, sec.Misc_VirtualSize,
                     sec.PointerToRawData, sec.SizeOfRawData))

    def off_to_rva(off):
        for name, va, vsz, rp, rs in secs:
            if rp <= off < rp + rs:
                return name, va + (off - rp)
        return None, None

    for rva in rvas:
        for label, needle in ((f"abs 0x{IMAGE_BASE + rva:x}", struct.pack("<Q", IMAGE_BASE + rva)),
                              (f"rva32 0x{rva:x}", struct.pack("<I", rva))):
            print(f"\n=== 搜 {label} ===")
            found = 0
            start = 0
            while True:
                pos = data.find(needle, start)
                if pos < 0:
                    break
                sec, hrv = off_to_rva(pos)
                if hrv is not None:
                    print(f"  off={pos:#010x} [{sec}] rva={hrv:#010x}")
                    found += 1
                start = pos + 1
                if found >= 25:
                    print("  ... 截断")
                    break
            if found == 0:
                print("  (无命中)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
