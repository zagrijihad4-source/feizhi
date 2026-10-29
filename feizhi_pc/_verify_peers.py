import json, sys
from pathlib import Path
sys.path.insert(0, ".")
from peer_state import get_registry

PEER = "<WXID_FRIEND_A>"
st = get_registry().get(PEER)
st.life.reload_shared()

print("=" * 70)
print("关系档位：", st.relation.data)
print("=" * 70)
print("【记忆渲染】前 400 字：")
print(st.memory.render()[:400])
print("=" * 70)
print("【生活状态合成渲染】前 700 字：")
print(st.life.render()[:700])
print("=" * 70)
print("共享层文件 feizhi_self.json：")
d = json.loads(Path("state/feizhi_self.json").read_text(encoding="utf-8"))
print("  字段:", list(d))
for p in d.get("projects", []):
    print("   [%s] %s" % (p.get("status"), p.get("title")))
    print("       最新一步:", (p.get("beats") or [{}])[-1].get("text", ""))
print("  心情:", (d.get("mood") or {}).get("state"), "|", (d.get("mood") or {}).get("since"))
print("  last_tick:", d.get("last_tick"))
print("私有层文件 life_private.json：")
p2 = json.loads(Path("state/peers/%s/life_private.json" % PEER).read_text(encoding="utf-8"))
print("  字段:", list(p2), " open_loops:", len(p2.get("open_loops") or []))
