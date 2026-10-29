"""核验「手工构造的内容对象」与「原生样本」的逐字段差异。

背景（外部复核指出）：
  早期的 diff_content_layout.py 只打印旧原生样本，并把自定义偏移表与常量比较，
  从未读取新手工构造的对象，因此不能替代真正的对象差异核验。

本脚本读取 bridge 在微信进程内构造并落盘的对象：
  输入 A：<PROJECT_ROOT>\\wx-basic-bridge\\bridge\\control\\content_built.hex  （新，手工构造）
  输入 B：<PROJECT_ROOT>\\reports\\sticker_precise.json 的 content_hex          （旧，原生）

比对内容：
  1. 头部 vtable（控制块 / 对象体）
  2. 12 个 std::string 的偏移、len、cap、类型（SSO/堆/空）
  3. 尾部两项的 16 字节 buf 是否清零
  4. 元数据区（+0x160..+0x16F）—— 属于运行时状态，只报告不判错

用法: python verify_built_content.py
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

REPORTS = Path(r"<PROJECT_ROOT>\reports")
BUILT = Path(r"<PROJECT_ROOT>\wx-basic-bridge\bridge\control\content_built.hex")
BUILT_INFO = Path(r"<PROJECT_ROOT>\wx-basic-bridge\bridge\control\content_built.txt")

# 仅比较 Native 侧样本覆盖到的范围（其余部分用静态布局表判定）
NATIVE_COVER = 0x180


def slot_offset(slot: int) -> int:
    if slot < 10:
        return 0x20 + slot * 0x20
    return 0x170 if slot == 10 else 0x190


def read_str(blk: bytes, off: int):
    if off + 0x20 > len(blk):
        return None
    buf, = struct.unpack_from("<Q", blk, off)
    ln, = struct.unpack_from("<Q", blk, off + 0x10)
    cap, = struct.unpack_from("<Q", blk, off + 0x18)
    kind = "empty" if ln == 0 else ("sso" if cap <= 0xF else "heap")
    return buf, ln, cap, kind


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    if not BUILT.exists():
        print(f"缺少新构造对象 {BUILT}")
        print("请先执行 type=5（dump_content）让 bridge 构造并落盘。")
        return 1
    raw = BUILT.read_text(encoding="utf-8").strip()
    try:
        built = bytes.fromhex(raw)
    except ValueError as e:
        print(f"content_built.hex 不是合法十六进制: {e}")
        return 1
    print(f"新构造对象: {len(built)} 字节")
    if BUILT_INFO.exists():
        print("---- 构造参数 ----")
        print(BUILT_INFO.read_text(encoding="utf-8").strip())
        print()

    native = None
    if (REPORTS / "sticker_precise.json").exists():
        data = json.loads((REPORTS / "sticker_precise.json").read_text(encoding="utf-8"))
        for rec in data.get("records", []):
            if rec.get("kind") == "commit":
                for o in rec.get("objs", []):
                    hx = o.get("content_hex")
                    if hx and len(hx) >= 0x100:
                        native = bytes.fromhex(hx.strip())
                        break
            if native:
                break
    if native is None:
        print("未找到原生样本，只输出新对象的结构")
    else:
        print(f"原生样本  : {len(native)} 字节")

    def show(name: str, blk: bytes):
        print(f"\n===== {name} =====")
        print(f"  +0x000 控制块 vtable = {struct.unpack_from('<Q', blk, 0)[0]:#x}")
        rq, = struct.unpack_from("<Q", blk, 8)
        print(f"  +0x008 引用计数/其他 = {rq:#x}")
        print(f"  +0x010 对象体 vtable = {struct.unpack_from('<Q', blk, 0x10)[0]:#x}")
        print(f"  {'slot':>4} {'off':>7} {'len':>6} {'cap':>6}  类型")
        for i in range(12):
            off = slot_offset(i)
            r = read_str(blk, off)
            if r is None:
                print(f"  {i:>4} {off:#07x}  (超出长度)")
                continue
            buf, ln, cap, kind = r
            print(f"  {i:>4} {off:#07x} {ln:>6} {cap:>6}  {kind}")

    show("新：手工构造", built)
    if native is not None:
        show("旧：原生", native)

    # ---- 逐字段比对 ----
    print("\n" + "=" * 70)
    print("逐字段比对")
    print("=" * 70)
    if native is None:
        print("（无原生样本，跳过）")
        return 0

    ok = True
    for off, name in ((0, "控制块 vtable"), (0x10, "对象体 vtable")):
        a, = struct.unpack_from("<Q", built, off)
        b, = struct.unpack_from("<Q", native, off)
        same = (a == b)
        ok &= same
        print(f"  {name:14s} 新={a:#x}  旧={b:#x}  [{'一致' if same else '不一致'}]")

    print(f"\n  {'slot':>4} {'off':>7} {'新 len':>7} {'旧 len':>7} {'新 cap':>7} {'旧 cap':>7}  判定")
    for i in range(12):
        off = slot_offset(i)
        rb = read_str(built, off)
        rn = read_str(native, off)
        if rn is None:
            print(f"  {i:>4} {off:#07x}   (旧样本未覆盖，布局依据为静态反汇编)")
            continue
        if rb is None:
            print(f"  {i:>4} {off:#07x}   (新对象超出长度)")
            ok = False
            continue
        _, lb, cb, kb = rb
        _, ln_, cn, kn = rn
        # len/cap 必须一致；len==0 时 cap 允许 0xF（SSO 空串）
        good = (lb == ln_) and (cb == cn or (lb == 0 and cb == 0xF))
        ok &= good
        print(f"  {i:>4} {off:#07x} {lb:>7} {ln_:>7} {cb:>7} {cn:>7}  {'一致' if good else '不一致'}  ({kb}/{kn})")

    print("\n【尾部两项的 16 字节 buf 是否清零（外部复核关注点）】")
    for i in (10, 11):
        off = slot_offset(i)
        if off + 0x10 > len(built):
            print(f"  slot {i}: 新对象超出长度")
            continue
        buf = built[off:off + 0x10]
        zeroed = (buf == b"\0" * 16)
        ok &= zeroed
        print(f"  slot {i} @ {off:#x}: buf = {buf.hex()}  [{'已清零' if zeroed else '未清零'}]")

    print("\n【元数据区（运行时状态，不参与判定）】")
    for off in (0x160, 0x164, 0x168, 0x16C):
        vb, = struct.unpack_from("<I", built, off)
        vn, = struct.unpack_from("<I", native, off) if off + 4 <= len(native) else (None,)
        print(f"  +{off:#05x}  新={vb:#010x}  旧={vn if vn is None else hex(vn)}")

    print(f"\n总体结论：{'逐字段一致' if ok else '存在差异（见上）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
