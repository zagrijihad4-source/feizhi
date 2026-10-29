import json
import glob
import os

files = sorted(glob.glob(r"<PROJECT_ROOT>\wx-basic-bridge\bridge\inbox\*.json"),
               key=os.path.getmtime)[-3:]
for f in files:
    print("=" * 70)
    print(os.path.basename(f))
    data = json.load(open(f, encoding="utf-8"))
    for k in ("msgId", "localId", "type", "subType", "timestamp",
              "from", "to", "direction", "isSendMsg", "isIncoming",
              "peerWxId", "senderWxId", "selfWxId", "roomId", "contentBytes"):
        print("  %-14s %r" % (k, data.get(k)))
    c = str(data.get("content", ""))
    print("  content[:60]   %r" % c[:60])
