import json
from pathlib import Path

PEER = "<WXID_FRIEND_B>"
p = Path("state/peers") / PEER / "life_private.json"
if p.exists():
    d = json.loads(p.read_text(encoding="utf-8"))
    loops = d.get("open_loops") or []
    print("<PEER_TEST> 现有待回访 %d 条：" % len(loops))
    for lp in loops:
        print("   -", str(lp.get("asked"))[:60])
    d["open_loops"] = []
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已清空（陌生人本来就不该有）")
else:
    print("没有 <PEER_TEST> 的私有文件")
