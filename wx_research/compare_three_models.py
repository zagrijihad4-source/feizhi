"""Align the three pack-element models side by side, from recorded raw hex.

Sources
  reports/frida_pack_models.txt  tid=7676  text model  (ours, proven to deliver)
                                 tid=28800 sticker envelope (native)
  reports/frida_cfg.txt          newest   image model (native)

Goal: settle field offsets and their likely roles by data instead of by hand,
after the previous hand-drawn offsets turned out to be off by one qword.

Usage: python compare_three_models.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PACK = Path(r"<PROJECT_ROOT>\reports\frida_pack_models.txt")
CFG = Path(r"<PROJECT_ROOT>\reports\frida_cfg.txt")
BASE = 0x7FFC9F060000
N = 0x120


def q(hexs: str, limit: int = N) -> list[int]:
    d = bytes.fromhex(hexs)[:limit]
    return [int.from_bytes(d[i:i + 8], "little") for i in range(0, len(d) - 7, 8)]


def load() -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    t = PACK.read_text(encoding="utf-8", errors="replace")
    for tid, vt, hexs in re.findall(
            r"--- pack tid=(\d+) models=1\s*\n\s*\[0\] vt=(\S+) hex=(\w+)", t):
        name = {"7676": "TEXT(ours)", "28800": "STICKER(native)"}.get(tid, f"tid{tid}")
        out[name] = q(hexs)
    c = CFG.read_text(encoding="utf-8", errors="replace")
    blocks = re.findall(r"PACK tid=(\d+)\n.*?model0_vt=(\S+) hex=(\w+)", c, re.S)
    if blocks:
        out["IMAGE(native)"] = q(blocks[-1][2])
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    models = load()
    order = [k for k in ("TEXT(ours)", "IMAGE(native)", "STICKER(native)") if k in models]
    print("models:", ", ".join(f"{k}={len(v) * 8}B" for k, v in models.items()))
    print()
    width = 22
    print(f"{'off':>7} " + " ".join(f"{k:>{width}}" for k in order))
    rows = max(len(models[k]) for k in order)
    for i in range(rows):
        cells = []
        for k in order:
            v = models[k][i] if i < len(models[k]) else None
            cells.append(f"{v:#018x}" if v is not None else "")
        line = f"  +0x{i * 8:03x} " + " ".join(f"{c:>{width}}" for c in cells)
        vals = [models[k][i] for k in order if i < len(models[k])]
        if len(set(vals)) > 1:
            line += "   <-- differs"
        print(line)
    print("\n=== role hints ===")
    for k in order:
        m = models[k]
        def at(o: int) -> int:
            return m[o // 8] if o // 8 < len(m) else 0
        print(f"  {k}: +0x078={at(0x78):#x} +0x0C0={at(0xC0):#x} +0x0C8={at(0xC8):#x} "
              f"+0x0D0={at(0xD0):#x} +0x0D8={at(0xD8):#x} +0x0E0={at(0xE0):#x} "
              f"+0x0E8={at(0xE8):#x} +0x0F0={at(0xF0):#x} +0x0F8={at(0xF8):#x} "
              f"+0x100={at(0x100):#x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
