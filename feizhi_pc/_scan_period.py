import json, sys
from pathlib import Path
sys.path.insert(0, ".")
from memrec import PERIOD_WORDS

base = Path("state/peers")
for d in sorted(p for p in base.iterdir() if p.is_dir()):
    mf = d / "memory.json"
    if not mf.exists():
        continue
    data = json.loads(mf.read_text(encoding="utf-8"))
    print("=" * 70)
    print(d.name)
    for bucket in ("facts", "events"):
        rows = data.get(bucket) or []
        live = [r for r in rows if not r.get("archived")]
        hit = [r for r in live if any(w in str(r.get("text")) for w in PERIOD_WORDS)]
        print("  %-7s 活跃 %-3d 条，含时段词 %d 条" % (bucket, len(live), len(hit)))
        for r in hit:
            words = [w for w in PERIOD_WORDS if w in str(r.get("text"))]
            flag = "待审" if r.get("needs_review") else "未标"
            print("    [%s] %-45s  %s  gate=%s"
                  % (",".join(words), str(r.get("text"))[:45], flag,
                     r.get("gate_state")))
