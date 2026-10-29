import sys, time
sys.path.insert(0, ".")
from store import ContextStore
st = ContextStore()
for r in st.all_messages("<WXID_FRIEND_A>"):
    if r.get("id") in (456, 457, 463, 700):
        ms = r.get("sent_at_ms")
        t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ms / 1000)) if ms else "?"
        print("#%-4s %s  %-9s %s" % (r.get("id"), t, r.get("role"), str(r.get("text"))[:70]))
