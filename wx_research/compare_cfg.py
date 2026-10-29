"""Diff the pack task-config (rdx of 0x160EBE0) between WeChat's native sticker
send and ours.

Source: reports/frida_cfg.txt
  tid=7416  -> ours  (from wxb_send_sticker_pack)
  tid=28800 -> WeChat native

Layout reminder (from db40.asm): 0xDB40 fills the config object as
  +0x00/+0x08  shared_ptr replaced by 5th arg (or the internal new(0x18) block)
  +0x10..+0x4F delegate #1 (std::function: inline storage, +0x48 = self/ptr)
  +0x50..+0x8F delegate #2 (+0x88)
  +0x90..+0xCF delegate #3 (+0xC8)
  +0xD0        6th arg (64-bit scalar)

Usage: python compare_cfg.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(r"<PROJECT_ROOT>\reports\frida_cfg.txt")
BASE = 0x7FFC9F060000


def qwords(hexs: str, n: int = 0xF0) -> list[int]:
    d = bytes.fromhex(hexs)[:n]
    return [int.from_bytes(d[i:i + 8], "little") for i in range(0, len(d) - 7, 8)]


def tag(v: int) -> str:
    if v == 0:
        return "0"
    if v == 0xAAAAAAAAAAAAAAAA:
        return "0xAA..AA (uninit)"
    if 0x7FFC00000000 <= v <= 0x7FFD00000000:
        return f"code rva {v - BASE:#x}"
    if v > 0x100000000000:
        return "heap ptr"
    return f"scalar {v:#x}"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    text = SRC.read_text(encoding="utf-8", errors="replace")
    blocks = re.findall(r"PACK tid=(\d+)\n\s+container_hex=(\w+)\n\s+cfg_hex=(\w+)", text)
    if len(blocks) < 2:
        print("need 2 PACK blocks, got", len(blocks))
        return 1
    ours = next((b for b in blocks if b[0] == "7416"), blocks[0])
    native = next((b for b in blocks if b[0] == "28800"), blocks[-1])

    qo = qwords(ours[2])
    qn = qwords(native[2])
    print(f"ours   tid={ours[0]}")
    print(f"native tid={native[0]}\n")
    print(f"{'off':>6} {'ours':>22} {'native':>22}  note")
    for i in range(max(len(qo), len(qn))):
        a = qo[i] if i < len(qo) else 0
        b = qn[i] if i < len(qn) else 0
        mark = "" if a == b else "  <-- DIFF"
        if mark or i < 4:
            print(f"  +0x{i * 8:02x} {a:#020x} {b:#020x}  {tag(a)} | {tag(b)}{mark}")

    print("\n=== delegate blocks ===")
    for name, base_off in (("d1", 0x10), ("d2", 0x50), ("d3", 0x90)):
        io = base_off // 8
        print(f"  {name}: ours  vt={tag(qo[io])}  self_field(+0x{base_off + 0x38:x})="
              f"{tag(qo[io + 7])}")
        print(f"  {name}: nativ vt={tag(qn[io])}  self_field(+0x{base_off + 0x38:x})="
              f"{tag(qn[io + 7])}")
    print(f"  +0xd0 scalar: ours={tag(qo[0xd0 // 8])} native={tag(qn[0xd0 // 8])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
