import sys
sys.path.insert(0, ".")
from store import ContextStore
st = ContextStore()
rows = st.all_messages("<WXID_FRIEND_A>")
print("最近 12 条：")
for r in rows[-12:]:
    who = "<OWNER>" if r.get("role") == "user" else "绯栀"
    print("%s | %s" % (who, str(r.get("text"))))
