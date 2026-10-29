"""Field-by-field diff between our envelope and WeChat's own, both captured at
the pack (0x160EBE0) call site.

Source: reports/frida_pack_models.txt
  tid=28800 -> WeChat's own sticker envelope (reference, user sent manually)
  tid=33936 -> our wxb_send_sticker_pack() envelope

Usage: python compare_pack_models.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(r"<PROJECT_ROOT>\reports\frida_pack_models.txt")


def load() -> dict[int, bytes]:
    text = SRC.read_text(encoding="utf-8", errors="replace")
    out: dict[int, bytes] = {}
    for tid, _vt, hexs in re.findall(
            r"--- pack tid=(\d+) models=1\s*\n\s*\[0\] vt=(\S+) hex=(\w+)", text):
        out[int(tid)] = bytes.fromhex(hexs)
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    d = load()
    if 28800 not in d or 33936 not in d:
        print("need both tid=28800 (wechat) and tid=33936 (ours); have:", list(d))
        return 1
    a = d[28800]
    b = d[33936]
    n = min(len(a), len(b), 0x800)
    print(f"wechat len={len(a)}  ours len={len(b)}  comparing {n} bytes\n")
    print(f"{'off':>7}  {'wechat':>20}  {'ours':>20}   note")
    diff = 0
    for off in range(0, n, 8):
        va = int.from_bytes(a[off:off + 8], "little")
        vb = int.from_bytes(b[off:off + 8], "little")
        if va != vb:
            note = ""
            if 0 < va < 0x100000:
                note = f"wechat small={va:#x}"
            if 0 < vb < 0x100000:
                note += f" ours small={vb:#x}"
            print(f"  +0x{off:03x}  {va:#020x}  {vb:#020x}   {note}")
            diff += 1
    print(f"\ndiffering qwords: {diff} / {n // 8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
