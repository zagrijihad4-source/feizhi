import sys, json, time
sys.path.insert(0, ".")
from store import ContextStore
st = ContextStore()
rows = st.all_messages("<WXID_FRIEND_A>")
print("字段:", list(rows[0]) if rows else "空")
print("共 %d 条，最近 26 条：" % len(rows))
for r in rows[-26:]:
    ms = r.get("sent_at_ms")
    t = time.strftime("%H:%M", time.localtime(ms/1000)) if ms else "  ?  "
    who = "<OWNER>" if r.get("role") == "user" else "绯栀"
    print("%s %s | %s" % (t, who, str(r.get("text"))))
