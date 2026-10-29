"""List vtable candidates inside a .rdata window.

Motivation: the text message model uses vtable rva 0x805E4E8 and works when fed
to 0x160EBE0. If WeChat's message models are a class family, their vtables are
usually laid out adjacently in .rdata. Finding neighbours helps identify the
sticker/emoji message model without guessing.

A vtable candidate = run of >=4 consecutive qwords that all point into .text.

Usage: python find_vtables.py 805E000 805F000
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
IMAGE_BASE = 0x180000000


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    lo = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x805E000
    hi = int(sys.argv[2], 16) if len(sys.argv) > 2 else 0x805F000
    focus = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0

    pe = pefile.PE(str(DLL), fast_load=True)
    data = DLL.read_bytes()
    secs = []
    text_lo = text_hi = 0
    for s in pe.sections:
        name = s.Name.rstrip(b"\x00").decode("ascii", "replace")
        secs.append((name, s.VirtualAddress, s.PointerToRawData, s.SizeOfRawData))
        if name == ".text":
            text_lo = s.VirtualAddress
            text_hi = s.VirtualAddress + s.SizeOfRawData
    print(f".text range {text_lo:#x}..{text_hi:#x}")

    def rva_to_off(r):
        for name, va, rp, rs in secs:
            if va <= r < va + rs:
                return rp + (r - va)
        return None

    def is_code_ptr(v):
        if v < IMAGE_BASE:
            return False
        r = v - IMAGE_BASE
        return text_lo <= r < text_hi

    off_lo = rva_to_off(lo)
    off_hi = rva_to_off(hi - 8)
    if off_lo is None or off_hi is None:
        print("range not mapped")
        return 1

    i = off_lo
    runs = []
    cur_start = None
    cur_len = 0
    while i <= off_hi:
        v = struct.unpack_from("<Q", data, i)[0]
        if is_code_ptr(v):
            if cur_start is None:
                cur_start = i
                cur_len = 0
            cur_len += 1
        else:
            if cur_start is not None and cur_len >= 4:
                runs.append((cur_start, cur_len))
            cur_start = None
            cur_len = 0
        i += 8
    if cur_start is not None and cur_len >= 4:
        runs.append((cur_start, cur_len))

    for start_off, n in runs:
        rva = lo + (start_off - off_lo)
        mark = "  <== FOCUS" if focus and rva <= focus < rva + n * 8 else ""
        first = struct.unpack_from("<Q", data, start_off)[0] - IMAGE_BASE
        print(f"  vtable? rva={rva:#010x} slots={n} first_fn={first:#x}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
