"""Clean the rows my PowerShell test corrupted, then retest with real UTF-8."""
import json
import sqlite3
import urllib.request

DB = r"<PROJECT_ROOT>\feizhi_pc\state\context.sqlite3"
API = "http://127.0.0.1:8791"

con = sqlite3.connect(DB)
rows = con.execute("SELECT id, text FROM messages WHERE source='panel'").fetchall()
print("panel rows before:", rows)
n = con.execute("DELETE FROM messages WHERE source='panel' AND text LIKE '%?%'").rowcount
con.commit()
con.close()
print("cleaned:", n)

body = json.dumps({"text": "面板发消息，这次是真的中文"}, ensure_ascii=False).encode("utf-8")
req = urllib.request.Request(API + "/api/send", data=body,
                             headers={"Content-Type": "application/json; charset=utf-8"})
print("send:", urllib.request.urlopen(req, timeout=40).read().decode("utf-8"))

d = json.loads(urllib.request.urlopen(API + "/api/messages?limit=2", timeout=10).read().decode("utf-8"))
for m in d:
    print("  %-10s | %s | %s" % (m["role"], m["text"], m.get("source")))
