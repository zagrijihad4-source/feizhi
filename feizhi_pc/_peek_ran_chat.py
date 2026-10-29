import sys, time
sys.path.insert(0, ".")
from store import ContextStore
st = ContextStore()
rows = st.all_messages("<WXID_FRIEND_B>")
print("共 %d 条：" % len(rows))
for r in rows:
    ms = r.get("sent_at_ms")
    t = time.strftime("%H:%M:%S", time.localtime(ms/1000)) if ms else "?"
    who = "<PEER_TEST> " if r.get("role") == "user" else "绯栀"
    print("%s %s | %s" % (t, who, str(r.get("text"))))
