"""分析 frida_sample_multi.py 采样结果，输出紧凑摘要。

重点回答：
  1. 发图过程中图片 XML 构造器被调用几次、每次哪些字段已填充
     （用于判断「是否可以先发不带 cdn 字段的占位消息」）
  2. 表情包走的是哪条路径（是否有 emoticon 相关命中）
  3. 各 hook 的上游调用链（backtrace 的 RVA）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SRC = Path(r"<PROJECT_ROOT>\reports\multi_sample.json")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    if not SRC.exists():
        print(f"找不到 {SRC}")
        return 1
    recs = json.loads(SRC.read_text(encoding="utf-8"))
    print(f"记录数 {len(recs)}\n")

    by_hook = {}
    for r in recs:
        by_hook.setdefault(r["hook"], []).append(r)

    for hook, rs in by_hook.items():
        print(f"########## {hook}  ({len(rs)} 次) ##########")
        for r in rs:
            print(f"\n--- #{r['n']}  this={r['self']} ---")
            f = {k: v for k, v in (r.get("fields") or {}).items() if v}
            i = {k: v for k, v in (r.get("ints") or {}).items() if v}
            print(f"  fields 非空: {list(f.keys())}")
            for k, v in f.items():
                print(f"    {k:<16} len={len(v):<4} {v[:80]!r}")
            print(f"  ints 非零: {i}")
            strs = r.get("strs") or []
            print(f"  自动扫描到 {len(strs)} 个字符串:")
            for s in strs:
                print(f"    +{s['off']:#05x} len={s['len']:<4} {s['s'][:80]!r}")
            print(f"  bt: {r.get('bt')}")
        print()

    # 表情相关线索
    print("########## 表情线索搜索 ##########")
    hit_kw = ("emoticon", "emoji", "fileext", "tpauthkey", "attachid")
    found = False
    for r in recs:
        for s in (r.get("strs") or []):
            low = s["s"].lower()
            if any(k in low for k in hit_kw):
                print(f"  [{r['hook']}#{r['n']}] +{s['off']:#x} {s['s'][:100]!r}")
                found = True
    if not found:
        print("  未发现 emoticon/emoji 等表情字段 —— 表情包可能没走这两个 hook 点")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
