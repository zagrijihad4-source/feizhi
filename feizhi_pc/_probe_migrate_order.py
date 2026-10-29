"""探针：migrate 会不会打乱 `render()` 的时间顺序。

背景：`_view()` 按 `str(x.get("id") or "")` 排序。legacy 记录没有 id，
排序键是空串，全部排在最前；新记录 m0001..m0009 紧随其后。
migrate 给 legacy 补 id 时按原顺序发号 m0010..，于是排序键变成
  m0001..m0009（最新 9 条） < m0010..m0105（10-16 起的旧记录）
「按 id 排序」和「按时间排序」就对不上了。

`render()` 取 `events[-12:]` 当「最近这些天」，顺序一乱，她记住的
就不再是最近发生的事。**在副本上验证，不碰生产。**
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from memory import FeizhiMemory  # noqa: E402

SRC = ROOT / "state" / "feizhi_memory.json"
PROBE = ROOT / "eval" / "_migrate_probe.json"
shutil.copy2(SRC, PROBE)

m = FeizhiMemory(PROBE)
before_render = m.render()
before_events = [x.get("text") for x in
                 __import__("memrec").recallable(m._view())
                 if x.get("kind") == "event"][-12:]

res = m.migrate()
print("migrate:", res)

after_render = m.render()
after_events = [x.get("text") for x in
                __import__("memrec").recallable(m._view())
                if x.get("kind") == "event"][-12:]

print()
print("render 完全一致:", before_render == after_render)
print()
print("=== migrate 前「最近这些天」(%d 条) ===" % len(before_events))
for i, t in enumerate(before_events, 1):
    print("  %2d. %s" % (i, t))
print()
print("=== migrate 后「最近这些天」(%d 条) ===" % len(after_events))
for i, t in enumerate(after_events, 1):
    print("  %2d. %s" % (i, t))
print()

only_before = [t for t in before_events if t not in after_events]
only_after = [t for t in after_events if t not in before_events]
print("migrate 后丢失的近期事件 %d 条：" % len(only_before))
for t in only_before:
    print("  - %s" % t)
print("migrate 后新冒出来的旧事件 %d 条：" % len(only_after))
for t in only_after:
    print("  + %s" % t)

PROBE.unlink(missing_ok=True)
