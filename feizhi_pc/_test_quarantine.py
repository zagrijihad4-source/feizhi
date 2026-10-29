import sys
sys.path.insert(0, ".")
import memrec as R
from memory import FeizhiMemory
import tempfile, json
from pathlib import Path

batch = [{"id": 456, "sent_at_ms": 1792480000000, "role": "user", "text": "辣椒炒肉"}]

tmp = Path(tempfile.mkdtemp()) / "m.json"
mem = FeizhiMemory(tmp)

cases = [
    ("无来源引用（模拟模型乱写 id）", {"kind": "fact", "text": "<OWNER>中午吃的是辣椒炒肉",
                                 "certainty": "high", "source_msg_ids": [999]}),
    ("来源为空", {"kind": "fact", "text": "<OWNER>中午吃的是辣椒炒肉",
                "certainty": "high", "source_msg_ids": []}),
    ("来源有效", {"kind": "fact", "text": "<OWNER>中午吃的是辣椒炒肉",
                "certainty": "high", "source_msg_ids": [456]}),
]
for name, rec in cases:
    w = FeizhiMemory(tmp)
    try:
        recs, stored, notes, mid = R.add_record(
            w._view(), rec, batch, 0, gate_state="pending")
        print("%-24s -> 存入 quarantined=%s gate=%s needs_review=%s"
              % (name, stored.get("quarantined"), stored.get("gate_state"),
                 stored.get("needs_review")))
        print("                           notes=%s" % ("; ".join(notes) or "无"))
        print("                           会被召回吗：%s"
              % ("是" if stored in R.recallable(recs) else "否"))
    except Exception as e:
        print("%-24s -> 拒绝入库：%s" % (name, e))
    print()
