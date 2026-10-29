import json, collections
from pathlib import Path
base = Path("state/peers")
for d in sorted(p for p in base.iterdir() if p.is_dir()):
    mf = d / "memory.json"
    if not mf.exists(): continue
    data = json.loads(mf.read_text(encoding="utf-8"))
    print(d.name)
    for b in ("facts", "events"):
        rows = data.get(b) or []
        g = collections.Counter(r.get("gate_state", "(缺=legacy)") for r in rows)
        live = sum(1 for r in rows if not r.get("archived"))
        nr = sum(1 for r in rows if r.get("needs_review") and not r.get("archived"))
        print("  %-7s 总%-3d 活跃%-3d gate=%s 活跃待审=%d" % (b, len(rows), live, dict(g), nr))
