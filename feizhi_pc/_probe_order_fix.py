"""探针：把 `_view()` 的排序键从 `id` 换成 `created/added` 后，
migrate 还会不会打乱「最近这些天」。

结论要能回答一个问题：**migrate 能不能安全执行**。
在副本上验证，不碰生产。
"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from memory import FeizhiMemory  # noqa: E402
import memrec as R  # noqa: E402

SRC = ROOT / "state" / "feizhi_memory.json"
PROBE = ROOT / "eval" / "_order_probe.json"
shutil.copy2(SRC, PROBE)


def view_by_created(m):
    """与 `_view()` 同构，但排序键用入库日；稳定排序保留同日内原顺序。"""
    out = []
    for b in ("facts", "events"):
        kind = "fact" if b == "facts" else "event"
        for x in m.data.get(b, []):
            if isinstance(x, dict):
                d = dict(x)
                d.setdefault("kind", kind)
                out.append(d)
    out.sort(key=lambda x: str(x.get("created") or x.get("added") or ""))
    return out


def recent_events(m, key):
    recs = sorted(R.recallable(view_by_created(m)),
                  key=lambda x: str(x.get("created") or x.get("added") or ""))
    return [x.get("text") for x in recs if x.get("kind") == "event"][-12:]


m = FeizhiMemory(PROBE)
before = recent_events(m, "created")
before_live = len(R.recallable(view_by_created(m)))

res = m.migrate()
after = recent_events(m, "created")

print("migrate:", res)
print("可召回条数 before=%d after=%d" % (before_live, len(R.recallable(view_by_created(m)))))
print()
print("按入库日排序时，migrate 前后「最近 12 条事件」一致:", before == after)
print()
if before != after:
    only_b = [t for t in before if t not in after]
    only_a = [t for t in after if t not in before]
    print("丢失 %d 条 / 多出 %d 条" % (len(only_b), len(only_a)))
    for t in only_b:
        print("  - %s" % t)
    for t in only_a:
        print("  + %s" % t)
else:
    print("最后 3 条：")
    for t in after[-3:]:
        print("  · %s" % t)

# 附带确认：migrate 没有改动正文，也没有改动归档状态
m2 = FeizhiMemory(SRC)
texts_before = [x.get("text") for x in view_by_created(m2)]
texts_after = [x.get("text") for x in view_by_created(m)]
arch_before = sum(1 for x in view_by_created(m2) if x.get("archived"))
arch_after = sum(1 for x in view_by_created(m) if x.get("archived"))
print()
print("正文集合不变:", sorted(map(str, texts_before)) == sorted(map(str, texts_after)))
print("归档数 before=%d after=%d" % (arch_before, arch_after))

PROBE.unlink(missing_ok=True)
