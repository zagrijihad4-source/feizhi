import json
from pathlib import Path
d = json.loads(Path("state/peers/<WXID_FRIEND_A>/memory.json").read_text(encoding="utf-8"))
print("=== needs_review 的记录（本该被闸门拦住） ===")
for b in ("facts", "events"):
    for r in d.get(b) or []:
        if r.get("needs_review"):
            print(" [%s] %s" % (b, r.get("text")))
            print("    gate=%s certainty=%s archived=%s"
                  % (r.get("gate_state"), r.get("certainty"), r.get("archived")))
print()
print("=== 最近 6 条写入（看新数据长什么样） ===")
rows = [(r.get("created"), b, r) for b in ("facts", "events") for r in (d.get(b) or [])]
rows.sort(key=lambda x: str(x[0] or ""), reverse=True)
for c, b, r in rows[:6]:
    print(" %s [%s] gate=%s cert=%-4s %s"
          % (c, b, r.get("gate_state"), r.get("certainty"), str(r.get("text"))[:56]))
