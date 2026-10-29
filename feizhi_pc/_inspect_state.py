import json
from pathlib import Path
for f in ("state/feizhi_life.json", "state/feizhi_memory.json"):
    p = Path(f)
    if not p.exists():
        print(f, "缺失"); continue
    d = json.loads(p.read_text(encoding="utf-8"))
    print("=" * 60)
    print(f, " 大小", p.stat().st_size, "字节")
    for k, v in d.items():
        if isinstance(v, list):
            print("  %-12s list[%d]" % (k, len(v)))
            if v and isinstance(v[0], dict):
                print("      首项字段:", list(v[0].keys()))
        elif isinstance(v, dict):
            print("  %-12s dict keys=%s" % (k, list(v.keys())[:8]))
        else:
            print("  %-12s %r" % (k, str(v)[:60]))
