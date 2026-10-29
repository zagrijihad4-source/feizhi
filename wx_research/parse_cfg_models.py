"""Parse the pack-element hexdumps from reports/frida_cfg.txt precisely.

Motivation: the previous analysis of the image message model was done by hand
and may have mixed the raw/body coordinate systems. This script decodes the
recorded hex with no manual counting, printing a qword table with annotations,
so the field offsets can be settled from data.

Usage:
    python parse_cfg_models.py            # all PACK blocks
    python parse_cfg_models.py last       # only the newest block
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(r"<PROJECT_ROOT>\reports\frida_cfg.txt")
BASE = 0x7FFC9F060000


def anno(v: int) -> str:
    if v == 0:
        return ""
    if v == 0xAAAAAAAAAAAAAAAA:
        return "0xAA fill"
    if 0x7FFB00000000 <= v <= 0x7FFE00000000:
        return f"code rva {v - BASE:#x}"
    if v > 0x10000000000:
        return "heap ptr"
    b = v.to_bytes(8, "little")
    if all(32 <= c < 127 for c in b[:4]) and any(c == 0 for c in b[4:]):
        return f'ascii "{b.split(b"\\x00")[0].decode("latin1")}"'
    return f"scalar {v:#x}"


def dump_block(tag: str, hexs: str, limit: int = 0x120) -> None:
    data = bytes.fromhex(hexs)[:limit]
    print(f"\n===== {tag} ({len(data)}B) =====")
    for off in range(0, len(data), 8):
        v = int.from_bytes(data[off:off + 8], "little")
        mark = "  *" if v not in (0, 0xAAAAAAAAAAAAAAAA) else ""
        print(f"  +0x{off:03x}  {v:#018x}  {anno(v)}{mark}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    text = SRC.read_text(encoding="utf-8", errors="replace")
    blocks = re.findall(r"PACK tid=(\d+)\n(.*?)(?=\nPACK tid=|\Z)", text, re.S)
    pick_last = len(sys.argv) > 1 and sys.argv[1] == "last"
    for tid, body in (blocks[-1:] if pick_last else blocks):
        m = re.search(r"model0_vt=(\S+) hex=(\w+)", body)
        if not m:
            continue
        dump_block(f"tid={tid} model0 vt={m.group(1)}", m.group(2))
        c = re.search(r"model0_\+0xE8=(\S+) vt=(\S+) hex=(\w+)", body)
        if c:
            print(f"  (content object at +0xE8: addr={c.group(1)} vt={c.group(2)})")
            dump_block("  content object", c.group(3), 0x80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
