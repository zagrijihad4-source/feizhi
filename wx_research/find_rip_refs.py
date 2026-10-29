"""Find every RIP-relative reference to one or more target RVAs.

Use case: 0x1B6A700 is the std::function target that WeChat's scheduler runs for
a sticker send, and 0x8E07B0 is the send logic. Whoever materialises those
addresses is the layer that *initiates* the send -- i.e. the UI-side entry we
want. Locating the references finds that layer.

Scans .text for `lea r64, [rip+disp32]`, `mov r64, [rip+disp32]` and
`mov r32, [rip+disp32]` and matches the computed target.

Usage: python find_rip_refs.py 1B6A700 8E07B0 [...]
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")

# (prefix bytes, instr length, description)
SHAPES = []
for rex in (0x48, 0x4C):
    for modrm in (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D):
        SHAPES.append((bytes([rex, 0x8D, modrm]), 7, "lea"))
        SHAPES.append((bytes([rex, 0x8B, modrm]), 7, "mov"))
for modrm in (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D):
    SHAPES.append((bytes([0x8B, modrm]), 6, "mov32"))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    targets = {int(a, 16) for a in sys.argv[1:]}
    if not targets:
        print(__doc__)
        return 1

    pe = pefile.PE(str(DLL), fast_load=True)
    data = DLL.read_bytes()
    text_va = text_off = text_size = 0
    for s in pe.sections:
        if s.Name.rstrip(b"\x00") == b".text":
            text_va, text_off, text_size = s.VirtualAddress, s.PointerToRawData, s.SizeOfRawData

    found: dict[int, list[tuple[int, str]]] = {t: [] for t in targets}
    for prefix, length, kind in SHAPES:
        start = text_off
        end = text_off + text_size
        dispoff = len(prefix)
        while True:
            i = data.find(prefix, start, end)
            if i < 0:
                break
            start = i + 1
            disp = struct.unpack_from("<i", data, i + dispoff)[0]
            insn_rva = text_va + (i - text_off)
            tgt = insn_rva + length + disp
            if tgt in targets:
                found[tgt].append((insn_rva, kind))

    for t in sorted(targets):
        hits = sorted(set(found[t]))
        print(f"== refs to {t:#x} : {len(hits)}")
        for insn_rva, kind in hits:
            print(f"   insn {insn_rva:#010x} ({kind})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
