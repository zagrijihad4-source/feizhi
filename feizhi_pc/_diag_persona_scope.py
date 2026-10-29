"""统计「性格」在代码里到底分布在哪些地方，为评估改动量提供依据。"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.stdout.reconfigure(encoding="utf-8")

print("=== persona.py 的顶层常量 ===")
src = (ROOT / "persona.py").read_text(encoding="utf-8")
tree = ast.parse(src)
total = 0
for node in tree.body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        name = node.targets[0].id
        if name.isupper():
            seg = ast.get_source_segment(src, node) or ""
            total += len(seg)
            print("  %-18s %5d 字符" % (name, len(seg)))
print("  小计 %d 字符" % total)

print()
print("=== 各文件里出现性格相关词的行数 ===")
WORDS = ["傲娇", "嘴硬", "心软", "毒舌", "19岁", "19 岁", "杭州", "美院",
         "绯栀", "<OWNER>", "女朋友", "前女友", "爸妈", "糊糊"]
for f in ("persona.py", "autoreply.py", "voice.py", "memory.py", "life.py",
          "proactive.py", "sing.py", "tts.py"):
    p = ROOT / f
    if not p.exists():
        continue
    hits = {}
    lines = p.read_text(encoding="utf-8").splitlines()
    for w in WORDS:
        n = sum(1 for ln in lines if w in ln)
        if n:
            hits[w] = n
    if hits:
        print("  %-14s %s" % (f, hits))

print()
print("=== voice.MOODS 档位（按人设设计的情绪集合）===")
import voice  # noqa: E402
for k, v in voice.MOODS.items():
    print("  %-4s %s" % (k, v.get("desc", "")))

print()
print("=== 记忆里带人设色彩的记录（可能和新性格冲突）===")
sys.path.insert(0, str(ROOT))
from memory import FeizhiMemory  # noqa: E402
import memrec as R  # noqa: E402
live = [x for x in R.recallable(FeizhiMemory()._view()) if x.get("text")]
KEY = re.compile(r"嘴硬|傲娇|毒舌|毛病|话多|跑调|不舍得|前女友|凶|冷冷")
n = 0
for x in live:
    t = str(x.get("text"))
    if KEY.search(t):
        n += 1
        print("  %s  %s" % (x.get("id"), t[:60]))
print("  共 %d 条 / 活记录 %d 条" % (n, len(live)))
