"""清理一条被模型幻觉污染的对话记录。

第 569 条是模型输出的整段文本：
  「好，你终于同意了，等着啊，我这就拍。 绯栀：[照片]gen_4c9f2b7e8a1d3f6c.jpg
    你看这版，靛蓝就巴掌大一块缩在角上…」
其中「绯栀：[照片]gen_4c9f2b7e8a1d3f6c.jpg」是它照抄 store 内部记录格式编出来的，
那个文件在 images/ 里根本不存在、日志里也没有任何生成记录。

★ 为什么改写而不是留着：记录里挂着一个**从未发生的动作**（发照片）。留着它，
  模型每轮都会在上下文里看到这个坏例子。改掉之后记录反映的是实际发生的事
  —— 她只说了话，没发图。

只改文本，不动时间、去重键、source。
"""
import shutil
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "state" / "context.sqlite3"
NEW = ("好，你终于同意了，等着啊，我这就拍。你看这版，靛蓝就巴掌大一块缩在角上，"
       "暗红只在边上一道窄边——是不是没那么花了？")

sys.stdout.reconfigure(encoding="utf-8")

bak = DB.with_name(DB.name + ".bak-markerfix-%s" % time.strftime("%Y%m%d-%H%M%S"))
shutil.copy2(DB, bak)
print("备份:", bak.name)

con = sqlite3.connect(str(DB))
cur = con.cursor()
row = cur.execute("select text from messages where id=569").fetchone()
if not row:
    sys.exit("569 不存在")
print("改前:", str(row[0])[:100])
if "gen_4c9f2b7e8a1d3f6c" not in str(row[0]):
    sys.exit("这条不含目标标记，可能已处理过，中止")

cur.execute("update messages set text=? where id=569", (NEW,))
con.commit()
after = cur.execute("select text from messages where id=569").fetchone()[0]
print("改后:", after)

left = 0
for (n,) in cur.execute("select count(*) from messages where text like '%gen_%jpg%'"):
    left = n
print()
print("仍含 gen_* 文件名的记录数:", left)
con.close()
