"""解析 msg_dump.json，把消息对象的内存按 8 字节字段展示，标出 vtable/指针/字符串。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SRC = Path(r"<PROJECT_ROOT>\reports\msg_dump.json")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    if not SRC.exists():
        print(f"找不到 {SRC}")
        return 1
    recs = json.loads(SRC.read_text(encoding="utf-8"))
    print(f"提交记录数 {len(recs)}\n")
    for r in recs:
        print(f"=== 提交 #{r.get('n')}  rcxs={r.get('rcxs')}  消息数={r.get('count')} ===")
        if r.get("err"):
            print(f"  遍历失败: {r['err']}")
        objs = r.get("objs") or []
        if not objs:
            print("  (无对象)")
        for o in objs:
            hexs = (o.get("hex") or "").replace("\n", "").strip()
            if not hexs:
                print(f"  obj {o['ptr']} 无 hex")
                continue
            b = bytes.fromhex(hexs)
            print(f"\n  --- obj ptr={o['ptr']} vtable={o['vt']} ({len(b)} 字节) ---")
            print("    非零 8 字节字段:")
            for off in range(0, len(b) - 7, 8):
                v = int.from_bytes(b[off:off + 8], "little")
                if v == 0:
                    continue
                tag = ""
                if v > 0x1000000000:
                    tag = " (指针/大值)"
                elif v <= 0x20:
                    tag = f" (小整数 {v})"
                print(f"      +{off:#05x} = {v:#018x}{tag}")
            if o.get("strs"):
                print("    扫描到的字符串:")
                for s in o["strs"]:
                    print(f"      +{s['off']:#05x} len={s['len']:<5} {s['s'][:110]!r}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
