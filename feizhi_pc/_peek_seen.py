import sys
sys.path.insert(0, ".")
from bridge import HookBridge
b = HookBridge()
print("seen_file =", b.seen_file, " 存在:", b.seen_file.exists())
txt = b.seen_file.read_text(encoding="utf-8", errors="replace")
lines = [ln for ln in txt.splitlines() if ln.strip()]
print("总行数:", len(lines))
hits = [ln for ln in lines if any(k in ln for k in
        ("3540344040840048612", "3475858840290998220", "4370050590404559962",
         "35ntf33hupsh22"))]
print("<PEER_TEST> 相关行 %d 条：" % len(hits))
for h in hits:
    print("   ", h)
