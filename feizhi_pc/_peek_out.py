import os, sys
sys.path.insert(0, ".")
print("FEIZHI_NO_MEMORY =", repr(os.environ.get("FEIZHI_NO_MEMORY")))
from store import ContextStore
st = ContextStore()
print("outbound:", st.outbound_stats())
for row in st.claim_outbound(limit=5):
    print("  任务", row)
