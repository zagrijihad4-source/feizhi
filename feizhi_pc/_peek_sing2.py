import sys
sys.path.insert(0, ".")
from store import ContextStore
st = ContextStore()
print("=== 最近 8 条 ===")
for r in st.all_messages("<WXID_FRIEND_A>")[-8:]:
    who = "<OWNER>" if r.get("role") == "user" else "绯栀"
    print("%s | %s" % (who, str(r.get("text"))))
print()
print("=== 曲库 ===")
import sing
print("catalog_text:", sing.catalog_text())
print("tracks:")
for t in sing.tracks():
    print("  ", t)
