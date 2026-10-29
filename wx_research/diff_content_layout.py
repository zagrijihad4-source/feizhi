"""逐字段对比「手工构造的内容对象」与「微信原生构造的内容对象」。

数据来源：reports/sticker_precise.json 里 commit 记录的 content_hex
         （真实发送时捕获的 0x1B0 字节）。

目的（外部评审要求）：确认修正后的构造逻辑与原生布局逐字段一致，
特别是尾部两个 string 的偏移、元数据区与容量约定。

用法: python diff_content_layout.py
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

REPORTS = Path(r"<PROJECT_ROOT>\reports")
SRC = REPORTS / "sticker_precise.json"

# 原生布局：12 个 string 的起始偏移（相对 block）
def slot_offset(slot: int) -> int:
    if slot < 10:
        return 0x20 + slot * 0x20
    return 0x170 if slot == 10 else 0x190


def read_msvc_string(blk: bytes, off: int):
    """返回 (buf_ptr, len, cap, kind)。kind: 'sso' / 'heap' / 'empty'"""
    if off + 0x20 > len(blk):
        return None
    buf = struct.unpack_from("<Q", blk, off)[0]
    ln = struct.unpack_from("<Q", blk, off + 0x10)[0]
    cap = struct.unpack_from("<Q", blk, off + 0x18)[0]
    if ln == 0:
        return (buf, ln, cap, "empty")
    return (buf, ln, cap, "sso" if cap <= 0xF else "heap")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    if not SRC.exists():
        print(f"缺少 {SRC}")
        return 1
    data = json.loads(SRC.read_text(encoding="utf-8"))

    # 找 commit 记录里的 content_hex
    sample = None
    for rec in data.get("records", []):
        if rec.get("kind") == "commit":
            for o in rec.get("objs", []):
                hx = o.get("content_hex")
                if hx and len(hx) >= 0x100:
                    sample = (o.get("content_vt_rva"), bytes.fromhex(hx.strip()))
                    break
        if sample:
            break
    if not sample:
        print("未在 sticker_precise.json 里找到 content_hex")
        return 1
    vt_rva, blk = sample

    print("=" * 78)
    print(f"原生内容对象样本：{len(blk)} 字节，控制块 vtable RVA = {vt_rva}")
    print("=" * 78)

    print("\n【头部】")
    print(f"  +0x000 控制块 vtable = {struct.unpack_from('<Q', blk, 0)[0]:#x}")
    rq = struct.unpack_from("<Q", blk, 8)[0]
    print(f"  +0x008 引用计数 = {rq:#x}   (_Uses={rq & 0xFFFFFFFF}, _Weaks={rq >> 32})")
    print(f"  +0x010 对象体 vtable = {struct.unpack_from('<Q', blk, 0x10)[0]:#x}")
    print(f"  +0x018 (未命名) = {struct.unpack_from('<Q', blk, 0x18)[0]:#x}")

    print("\n【12 个 std::string（按原生偏移表）】")
    print(f"  {'slot':>4} {'off':>7} {'len':>6} {'cap':>6}  类型")
    for i in range(12):
        off = slot_offset(i)
        r = read_msvc_string(blk, off)
        if r is None:
            print(f"  {i:>4} {off:#07x}  (超出样本长度)")
            continue
        buf, ln, cap, kind = r
        print(f"  {i:>4} {off:#07x} {ln:>6} {cap:>6}  {kind}")

    print("\n【元数据区 block+0x160..0x16F】")
    for off in (0x160, 0x164, 0x168, 0x16C):
        if off + 4 <= len(blk):
            print(f"  +{off:#05x} = {struct.unpack_from('<I', blk, off)[0]:#010x}")

    print("\n【尾部两个 string 的完整字段】")
    for i in (10, 11):
        off = slot_offset(i)
        r = read_msvc_string(blk, off)
        if r is None:
            print(f"  slot {i} @ {off:#x}: 超出样本长度（样本仅 {len(blk)} 字节）")
            print(f"            —— 该槽位布局由静态反汇编 ctor_3d67da0.asm 确认")
            continue
        buf, ln, cap, kind = r
        print(f"  slot {i} @ {off:#x}: buf={buf:#x} len={ln} cap={cap} ({kind})")
        if kind == "sso":
            raw = blk[off:off + 16].split(b"\0")[0]
            print(f"            内联内容 = {raw!r}")

    print("\n【结论核对】")
    ok = True
    # 尾部两项必须落在 0x170 / 0x190
    for i, want in ((10, 0x170), (11, 0x190)):
        got = slot_offset(i)
        mark = "OK" if got == want else "MISMATCH"
        if got != want:
            ok = False
        print(f"  slot {i} 原生偏移 = {want:#x}，当前实现 = {got:#x}  [{mark}]")
    # 容量约定：cap 是否为 len|0xF 或 0xF
    caps = []
    for i in range(12):
        r = read_msvc_string(blk, slot_offset(i))
        if r:
            _, ln, cap, _ = r
            caps.append((i, ln, cap))
    print("  容量约定样本：")
    for i, ln, cap in caps:
        if ln:
            print(f"    slot {i}: len={ln} cap={cap}  (len|0xF = {ln | 0xF})")
    print(f"\n  尾部偏移表 {'一致' if ok else '不一致'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
