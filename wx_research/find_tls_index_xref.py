"""Find every instruction that references the WeChat TLS index slot at
rva 0xA530BA0 (the slot read by 0x39B8F0 to fetch the per-thread service).

Method: scan for the `8B <modrm>` RIP-relative mov family that loads a dword
from [rip+disp32], then check whether the computed target equals 0xA530BA0.
That is exactly the instruction shape at 0x39B8F6:
    8B 05 A4 52 19 0A     mov eax, [rip+0xA1952A4]   -> rva 0xA530BA0
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
IMAGE_BASE = 0x180000000
TARGET_RVA = 0xA530BA0

# mov r32, [rip+disp32]  ->  8B /r with mod=00 rm=101
MODRM = {
    0x05: "eax", 0x0D: "ecx", 0x15: "edx", 0x1D: "ebx",
    0x25: "esp", 0x2D: "ebp", 0x35: "esi", 0x3D: "edi",
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    pe = pefile.PE(str(DLL), fast_load=True)
    data = DLL.read_bytes()
    md = {}
    for s in pe.sections:
        name = s.Name.rstrip(b"\x00").decode("ascii", "replace")
        md[name] = (s.VirtualAddress, s.PointerToRawData, s.SizeOfRawData,
                    max(s.Misc_VirtualSize, s.SizeOfRawData))

    va, off, raw, vsize = md[".text"]

    hits = []
    for modrm, reg in MODRM.items():
        pat = bytes([0x8B, modrm])
        start = off
        end = off + raw
        while True:
            i = data.find(pat, start, end)
            if i < 0:
                break
            start = i + 1
            disp = struct.unpack_from("<i", data, i + 2)[0]
            insn_rva = (va + (i - off))
            tgt = insn_rva + 6 + disp
            if tgt != TARGET_RVA:
                continue
            hits.append((insn_rva, reg))

    hits.sort()
    print(f"refs to TLS index slot {TARGET_RVA:#x}: {len(hits)}")
    for rva, reg in hits:
        print(f"  {rva:#010x}  mov {reg}, [rip+disp]  ; -> {TARGET_RVA:#x}")
    print()
    print("--- dump bytes around each hit (32 bytes from insn) ---")
    for rva, reg in hits:
        hoff = off + (rva - va)
        chunk = data[hoff:hoff + 40]
        print(f"  {rva:#010x}: " + chunk.hex(" "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
