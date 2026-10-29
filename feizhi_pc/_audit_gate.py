import json, collections
from pathlib import Path

for label, p in (("<OWNER>(迁移后)", Path("state/peers/<WXID_FRIEND_A>/memory.json")),
                 ("旧文件(迁移前)", Path("state/feizhi_memory.json"))):
    if not p.exists():
        print(label, "不存在"); continue
    d = json.loads(p.read_text(encoding="utf-8"))
    print("=" * 62)
    print(label, "->", p)
    for bucket in ("facts", "events"):
        rows = d.get(bucket) or []
        g = collections.Counter(r.get("gate_state", "(缺字段=legacy)") for r in rows)
        q = sum(1 for r in rows if r.get("quarantined"))
        nr = sum(1 for r in rows if r.get("needs_review"))
        ar = sum(1 for r in rows if r.get("archived"))
        print("  %-7s 总%-3d gate=%s  隔离=%d  待审=%d  归档=%d"
              % (bucket, len(rows), dict(g), q, nr, ar))
