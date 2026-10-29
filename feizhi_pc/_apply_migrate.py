"""执行生产迁移：给 96 条 legacy 记录补 id 与结构字段。

顺序与护栏：
  1. 先拍快照（整个 state/ 目录），出问题直接回滚；
  2. migrate 只做 setdefault + 补 id，不改正文、不改归档状态；
  3. 迁移前后比对 `render()` / `render_existing()` —— **必须完全一致**。
     我在 2026-10-27 已把 `_view()` 的排序键从 id 改成入库日，
     正是为了让这一步不再打乱时间线；这里是用真实数据复核那个结论。
  4. 校验 id 唯一、全部记录都有 id、last_id 水位没被动过。
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from memory import FeizhiMemory  # noqa: E402
import memrec as R  # noqa: E402

STATE = ROOT / "state"
MEM = STATE / "feizhi_memory.json"

snap = ROOT / "eval" / ("pre_migrate_" + time.strftime("%Y%m%d-%H%M%S"))
snap.mkdir(parents=True, exist_ok=False)
for f in STATE.iterdir():
    if f.is_file():
        shutil.copy2(f, snap / f.name)
print("快照：%s" % snap)
print()

m = FeizhiMemory(MEM)
before_render = m.render()
before_existing = m.render_existing()
before_live = len(R.recallable(m._view()))
before_arch = sum(1 for x in m._view() if x.get("archived"))
before_last_id = m.data.get("last_id")

res = m.migrate()
print("migrate 返回：%s" % (res,))
print()

after_render = m.render()
after_existing = m.render_existing()
after_live = len(R.recallable(m._view()))
after_arch = sum(1 for x in m._view() if x.get("archived"))

checks = []
checks.append(("render 完全一致", before_render == after_render))
checks.append(("render_existing 完全一致", before_existing == after_existing))
checks.append(("可召回数不变", before_live == after_live))
checks.append(("归档数不变", before_arch == after_arch))
checks.append(("last_id 水位未动", before_last_id == m.data.get("last_id")))

view = m._view()
missing = [x for x in view if not x.get("id")]
ids = [x.get("id") for x in view]
checks.append(("全部记录都有 id", not missing))
checks.append(("id 唯一", len(ids) == len(set(ids))))
checks.append(("last_mid 推进到 %d" % len(view), int(m.data.get("last_mid", 0)) >= len(view)))

print("可召回 %d -> %d / 归档 %d -> %d / last_id %s -> %s"
      % (before_live, after_live, before_arch, after_arch,
         before_last_id, m.data.get("last_id")))
print("last_mid = %s，id 示例 %s .. %s"
      % (m.data.get("last_mid"), ids[0] if ids else "-", ids[-1] if ids else "-"))
print()
for name, ok in checks:
    print("  [%s] %s" % ("OK" if ok else "FAIL", name))

if before_render != after_render:
    diff = ROOT / "eval" / "_migrate_render_diff.txt"
    diff.write_text(
        "=== BEFORE ===\n%s\n\n=== AFTER ===\n%s\n" % (before_render, after_render),
        encoding="utf-8")
    print("\n渲染差异已存到 %s" % diff)

bad = [n for n, ok in checks if not ok]
print()
print("全部通过" if not bad else "失败项：" + "、".join(bad))
sys.exit(1 if bad else 0)
