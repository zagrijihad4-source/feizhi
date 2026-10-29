"""诊断：按「任意一天都成立 = fact / 只能用那一次指代 = event」筛出 kind 可疑项。

纯程序粗筛，**结论必须人工核对**。这里只负责把候选缩小到能一条条看完的规模。

两个方向：
  * facts 里出现完成态（了/过/完/已经/曾经）却没有任何习惯性归纳词
    → 说的是某一次发生的事，疑似该是 event。
  * events 里出现习惯性归纳词（每天/每周/总是/经常/习惯…）
    → 说的是长期规律，疑似该是 fact。

故意不把「到」「在」放进完成态：它们太泛
（「在石家庄」是状态，「描到手腕酸」是某次），放进去只会制造假阳性。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from memory import FeizhiMemory  # noqa: E402
import memrec as R  # noqa: E402

DONE = re.compile(r"了|过|完|已经|曾经")
HABIT = re.compile(r"每天|每周|每周.|总是|经常|习惯|常常|老是|一般|都会|向来|平时")

live = [x for x in R.recallable(FeizhiMemory()._view()) if x.get("text")]
facts = [x for x in live if x.get("kind") != "event"]
events = [x for x in live if x.get("kind") == "event"]

suspect_event = []
for x in facts:
    t = str(x.get("text"))
    if DONE.search(t) and not HABIT.search(t):
        suspect_event.append(x)

suspect_fact = []
for x in events:
    t = str(x.get("text"))
    if HABIT.search(t):
        suspect_fact.append(x)

print("活记录 %d（fact %d / event %d）" % (len(live), len(facts), len(events)))
print()
print("=== facts 里疑似 event：%d 条（%.0f%% of facts） ==="
      % (len(suspect_event), 100.0 * len(suspect_event) / max(1, len(facts))))
for x in suspect_event:
    print("  %s  %s" % (x.get("id"), x.get("text")))
print()
print("=== events 里疑似 fact：%d 条 ===" % len(suspect_fact))
for x in suspect_fact:
    print("  %s  %s" % (x.get("id"), x.get("text")))
