"""只读查看最近的对话记录，用来核对绯栀实际说了什么。"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8")

con = sqlite3.connect("file:%s?mode=ro" % (ROOT / "state" / "context.sqlite3"), uri=True)
cur = con.cursor()

tables = [r[0] for r in cur.execute(
    "select name from sqlite_master where type='table'")]
print("tables:", tables)
for (sql,) in cur.execute(
        "select sql from sqlite_master where type='table'"):
    print(sql)
print()

# 找带 role/text 的表
target = None
for t in tables:
    cols = [r[1] for r in cur.execute("pragma table_info(%s)" % t)]
    if "text" in cols and "role" in cols:
        target = t
        print("使用表 %s，列：%s" % (t, cols))
        break

if not target:
    sys.exit("没有找到含 role/text 的表")

for row in cur.execute(
        "select id, role, sent_at_ms, text from %s order by id desc limit 24" % target):
    rid, role, ms, text = row
    print("%4s  %-6s  %s" % (rid, role, str(text)[:120]))
