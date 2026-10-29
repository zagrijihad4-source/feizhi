# -*- coding: utf-8 -*-
"""闸门出口回归：新记忆入库必经 pending，干净才自动放行。

要证明三件事：
  1. 干净记忆（来源有效、无时间疑点）→ 自动 eligible → 能召回
  2. 带时段词污染的记忆 → 留 pending → **不召回**（辣椒炒肉那条）
  3. 人工放行（by="human"）能把它放出来，但归档/隔离的仍然跳过
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import memrec as R                                    # noqa: E402
from memory import FeizhiMemory                       # noqa: E402

BATCH = [
    {"id": 456, "sent_at_ms": 1792480000000, "role": "user", "text": "辣椒炒肉"},
    {"id": 457, "sent_at_ms": 1792480060000, "role": "user", "text": "我晚上不吃饭了"},
]

PASS = FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ %s" % name)
    else:
        FAIL += 1
        print("  ✗ %s %s" % (name, extra))


def fresh() -> FeizhiMemory:
    return FeizhiMemory(Path(tempfile.mkdtemp()) / "m.json")


def ingest(mem: FeizhiMemory, items, kind="events"):
    return mem._ingest(kind, items, BATCH, gate_state="pending")


def main() -> int:
    print("=" * 68)
    print("[1] 干净记忆：入库即 pending，自动放行后 eligible、可召回")
    mem = fresh()
    n, q, p, fails = ingest(mem, [{
        "text": "<OWNER>要交材料", "certainty": "high",
        "source_msg_ids": [456], "time_raw": "", "time_anchor_msg_id": None}])
    view = mem._view()
    rec = [r for r in view if r.get("text") == "<OWNER>要交材料"][0]
    check("入库后 gate=pending", rec.get("gate_state") == "pending", rec.get("gate_state"))
    check("没有复核标记", not rec.get("needs_review"))
    check("此刻不可召回（闸门关着）",
          rec not in R.recallable(view))
    recs, notes, summary = R.approve_pending(view, by="auto")
    check("自动放行成功", recs is not None and len(summary["approved"]) == 1,
          json.dumps(summary, ensure_ascii=False))
    after = [r for r in recs if r.get("text") == "<OWNER>要交材料"][0]
    check("放行后 gate=eligible", after.get("gate_state") == "eligible",
          after.get("gate_state"))
    check("放行后可召回", after in R.recallable(recs))

    print()
    print("[2] 时段词污染（辣椒炒肉那条）：留 pending，不召回")
    mem2 = fresh()
    ingest(mem2, [{
        "text": "<OWNER>中午吃的是辣椒炒肉", "certainty": "high",
        "source_msg_ids": [456], "time_raw": "", "time_anchor_msg_id": None}])
    view2 = mem2._view()
    rec2 = [r for r in view2 if "辣椒炒肉" in str(r.get("text"))][0]
    check("被标 needs_review", bool(rec2.get("needs_review")))
    check("gate 仍是 pending", rec2.get("gate_state") == "pending", rec2.get("gate_state"))
    recs2, notes2, sum2 = R.approve_pending(view2, by="auto")
    check("自动审核**拒绝**放行", recs2 is None and not sum2["approved"],
          json.dumps(sum2, ensure_ascii=False))
    check("它仍在 kept 里等人看", sum2["kept"] == [rec2.get("id")])
    check("所以召回列表里没有它", rec2 not in R.recallable(view2))
    print("     notes: %s" % ("; ".join(notes2) or "无"))

    print()
    print("[3] 人工放行：by=human 能放出来")
    recs3, _, sum3 = R.approve_pending(view2, by="human")
    check("human 放行成功", recs3 is not None and len(sum3["approved"]) == 1,
          json.dumps(sum3, ensure_ascii=False))
    check("放行后可召回", any(r["id"] == rec2["id"] for r in R.recallable(recs3)))

    print()
    print("[4] 归档/隔离的记录不能被批准复活")
    mem4 = fresh()
    ingest(mem4, [{"text": "<OWNER>去打球", "certainty": "high",
                   "source_msg_ids": [456], "time_raw": "", "time_anchor_msg_id": None}])
    view4 = mem4._view()
    for r in view4:
        if r.get("text") == "<OWNER>去打球":
            r["archived"] = True
    recs4, _, sum4 = R.approve_pending(view4, by="human")
    check("归档项被跳过", recs4 is None and not sum4["approved"],
          json.dumps(sum4, ensure_ascii=False))

    print()
    print("[5] 已经 eligible 的不重复处理")
    mem5 = fresh()
    ingest(mem5, [{"text": "<OWNER>去打球", "certainty": "high",
                   "source_msg_ids": [456], "time_raw": "", "time_anchor_msg_id": None}])
    view5 = mem5._view()
    for r in view5:
        if r.get("text") == "<OWNER>去打球":
            r["gate_state"] = "eligible"
    recs5, _, sum5 = R.approve_pending(view5, by="auto")
    check("eligible 被 skipped", recs5 is None and not sum5["approved"])

    print()
    print("=" * 68)
    print("结论：%d 通过 / %d 失败" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
