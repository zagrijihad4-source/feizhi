import sys
sys.path.insert(0, ".")
from store import ContextStore
st = ContextStore()
for r in st.history("<WXID_FRIEND_B>", limit=10):
    print("  %-9s %s" % (r[0], r[1][:160]))
