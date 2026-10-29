"""查内部记录标记有没有漏进对话历史。

背景：`_send_one` 成功后写库是 `store.add(peer, "assistant", "[照片]xxx.jpg")`
/ `"[图片]xxx"` / `"[语音]xxx"` / `"[表情]xxx"` / `"[翻唱]《x》"`。
这些是**给人看的内部标记**，不是发给对方的话。如果它们原样进了上下文，
模型会照着学，自己编造 `[照片]gen_xxx.jpg` 这种根本不存在的文件名当文字发出去。
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8")

con = sqlite3.connect("file:%s?mode=ro" % (ROOT / "state" / "context.sqlite3"), uri=True)
cur = con.cursor()

MARKERS = ["[照片]", "[图片]", "[语音]", "[表情]", "[翻唱]", "[贴纸]"]
print("=== 历史里各标记出现次数（assistant）===")
total = 0
for mk in MARKERS:
    n = cur.execute(
        "select count(*) from messages where role='assistant' and text like ?",
        ("%" + mk + "%",)).fetchone()[0]
    total += n
    print("  %-8s %d" % (mk, n))
print("  合计 %d" % total)

print()
print("=== 最近 8 条带标记的记录 ===")
for row in cur.execute(
        "select id, text from messages where role='assistant' "
        "and (text like '%[照片]%' or text like '%[图片]%' or text like '%[语音]%' "
        "or text like '%[表情]%' or text like '%[翻唱]%') "
        "order by id desc limit 8"):
    print("  %4s  %s" % (row[0], str(row[1])[:90]))

print()
print("=== 模型自己编造标记的痕迹（正文以 [xxx] 开头但不在已知形态里）===")
for row in cur.execute(
        "select id, text from messages where role='assistant' "
        "and text like '[%]' order by id desc limit 12"):
    print("  %4s  %s" % (row[0], str(row[1])[:90]))
