import sys, json
sys.path.insert(0, ".")
from store import ContextStore

st = ContextStore()
PEER = "<WXID_FRIEND_A>"
rows = st.all_messages(PEER)
print("总消息 %d 条，搜「辣椒」：" % len(rows))
for r in rows:
    t = str(r.get("text") or "")
    if "辣椒" in t:
        print("  #%s %-9s %s" % (r.get("id"), r.get("role"), t[:200]))

print()
d = json.loads(open("state/peers/%s/memory.json" % PEER, encoding="utf-8").read())
print("记忆里搜「辣椒」：")
for b in ("facts", "events"):
    for x in d.get(b) or []:
        if "辣椒" in str(x.get("text")):
            print("  [%s] %s" % (b, x.get("text")))
            print("     gate=%s cert=%s archived=%s" % (x.get("gate_state"), x.get("certainty"), x.get("archived")))
            print("     event_time=%r time_basis=%r time_raw=%r anchor=%s"
                  % (x.get("event_time"), x.get("time_basis"), x.get("time_raw"), x.get("time_anchor_msg_id")))
            print("     source_msg_ids=%s created=%s" % (x.get("source_msg_ids"), x.get("created")))
