"""Find every instruction that loads a vtable pointer from the message-model
vtable cluster around 0x805E000-0x805F000.

Reasoning: the text message model works end-to-end through pack (0x160EBE0).
Its body vtable 0x805E578 is written by 0x6A35B0. That .rdata window holds ~20
adjacent vtable candidates, which looks like a per-message-type family. Each
should have its own initializer nearby (0x6A0860, 0x6A0F20, ...). Locating the
loaders tells us which initializer pairs with which vtable.

Usage: python find_vtable_loaders.py [lo] [hi]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
IMAGE_BASE = 0x180000000
LO = 0x805E000
HI = 0x805F000

# lea r64, [rip+disp32]: 48/4C 8D <modrm=00xxx101>
MODRMS = [0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D]
REX = [0x48, 0x4C]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    lo = int(sys.argv[1], 16) if len(sys.argv) > 1 else LO
    hi = int(sys.argv[2], 16) if len(sys.argv) > 2 else HI

    pe = pefile.PE(str(DLL), fast_load=True)
    data = DLL.read_bytes()
    text_va = text_off = text_size = 0
    for s in pe.sections:
        if s.Name.rstrip(b"\x00") == b".text":
            text_va, text_off, text_size = s.VirtualAddress, s.PointerToRawData, s.SizeOfRawData

    hits = []
    for rex in REX:
        for modrm in MODRMS:
            pat = bytes([rex, 0x8D, modrm])
            start = text_off
            end = text_off + text_size
            while True:
                i = data.find(pat, start, end)
                if i < 0:
                    break
                start = i + 1
                disp = struct.unpack_from("<i", data, i + 3)[0]
                insn_rva = text_va + (i - text_off)
                tgt = insn_rva + 7 + disp
                if lo <= tgt < hi and tgt % 8 == 0:
                    hits.append((insn_rva, tgt))

    hits.sort()
    print(f"vtable loads into [{lo:#x}, {hi:#x}): {len(hits)}")
    for insn_rva, tgt in hits:
        print(f"  insn {insn_rva:#010x}  -> vtable {tgt:#010x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
