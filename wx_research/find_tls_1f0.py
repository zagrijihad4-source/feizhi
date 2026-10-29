"""Locate every instruction that touches [reg+0x1F0] in Weixin.dll.

Why: 0x39B8F0 reads the per-thread WeChat service from TLS block +0x1F0.
Both our worker thread and the WeChat window thread report NO_SERVICE there,
so the service must be created lazily / bound to some other thread. The write
site tells us who installs it and under which condition.

Full linear disassembly of a 179 MB PE is too slow, so this pre-filters on the
raw disp32 bytes F0 01 00 00 and then decodes a short candidate window.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
IMAGE_BASE = 0x180000000
NEEDLE = b"\xf0\x01\x00\x00"
DISP = 0x1F0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    pe = pefile.PE(str(DLL), fast_load=True)
    data = DLL.read_bytes()
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

    secs = []
    for s in pe.sections:
        name = s.Name.rstrip(b"\x00").decode("ascii", "replace")
        secs.append({
            "name": name,
            "va": s.VirtualAddress,
            "vsize": max(s.Misc_VirtualSize, s.SizeOfRawData),
            "off": s.PointerToRawData,
            "raw": s.SizeOfRawData,
        })

    def rva_of(off: int):
        for s in secs:
            if s["off"] <= off < s["off"] + s["raw"]:
                return s["va"] + (off - s["off"]), s["name"]
        return None, None

    hits = []
    start = 0
    while True:
        i = data.find(NEEDLE, start)
        if i < 0:
            break
        start = i + 1
        rva, sname = rva_of(i)
        if rva is None or sname != ".text":
            continue
        # disp32 tail ends at i+4 == i+3; try decoding from 1..4 bytes back
        for back in range(1, 5):
            base_off = i - back
            for insn in md.disasm(data[base_off:base_off + 16], IMAGE_BASE + rva - back):
                if insn.size != back + 4:
                    break
                found = False
                for op in insn.operands:
                    if op.type == X86_OP_MEM and op.mem.disp == DISP and op.mem.base != 0:
                        found = True
                        break
                if found:
                    hits.append({
                        "rva": insn.address - IMAGE_BASE,
                        "text": f"{insn.mnemonic:<7} {insn.op_str}",
                        "write": insn.operands[0].type == X86_OP_MEM
                        and insn.operands[0].mem.disp == DISP
                        and insn.mnemonic not in ("cmp", "test", "lea"),
                    })
                break

    seen = set()
    uniq = []
    for h in hits:
        if h["rva"] in seen:
            continue
        seen.add(h["rva"])
        uniq.append(h)
    uniq.sort(key=lambda h: h["rva"])

    writes = [h for h in uniq if h["write"]]
    print(f"total [reg+0x1f0] insns: {len(uniq)}   writes: {len(writes)}")
    print("--- writes ---")
    for h in writes:
        print(f"  {h['rva']:#010x}  {h['text']}")
    print("--- all (first 80) ---")
    for h in uniq[:80]:
        print(f"  {h['rva']:#010x}  {h['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
