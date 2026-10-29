"""执行反思层报出的 11 条修正。

两类动作，严格区分：
  * 归档 —— 信息已被别处覆盖，或纯属当场状态，留着只会误导；
  * 改写 —— 事件本身有价值，只是正文里带着已失效的时间词/瞬时状态。

定位方式：按正文**精确匹配**。刚 migrate 出来的 id 没有人工记录，
用 text 当键更可靠；匹配不到或匹配到多条就中止，不猜。
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from memory import FeizhiMemory  # noqa: E402
import memrec as R  # noqa: E402

STATE = ROOT / "state"
MEM = STATE / "feizhi_memory.json"

ARCHIVE = [
    ("<OWNER>明天9点有课",
     "正文带已过期的「明天」（入库 10-16）；「<OWNER>有早八」的信息已由另两条记录覆盖"),
    ("绯栀冰箱只剩前天买的半盒酸奶，没敢喝",
     "正文带已过期的「前天」（入库 10-18），说的是当天冰箱的瞬时状态"),
    ("绯栀中午没吃饭，光顾着改海报，打算待会儿下碗面",
     "正文带「待会儿」（入库 10-20），当时的打算早已失效"),
    ("绯栀跟<OWNER>说醒了要告诉她，她要讲自己今早干的蠢事",
     "正文带「今早」（入库 10-20），那次对话早已结束"),
    ("绯栀问<OWNER>海报配色行不行，<OWNER>还没回",
     "瞬时状态「还没回」已失效；同一件事由另外三条配色记录覆盖"),
    ("<OWNER>晚上会打游戏",
     "与「<OWNER>晚上8点就躺床上，会打游戏」重复，保留信息更全的那条"),
    ("<OWNER>周日没有课",
     "与「<OWNER>周日没课，绯栀让他别打游戏太晚」重复"),
    ("<OWNER>中午吃的是辣椒炒肉",
     "与事件「绯栀追问<OWNER>中午吃了没，<OWNER>答吃了辣椒炒肉」重复；"
     "单次进食归成长期事实本身也不准确"),
    ("<OWNER>有早八的课，前一晚12点多睡",
     "与「…十二点多睡，早上仍困得逃课回去补觉」重复，保留信息更全的那条"),
]

REWRITE = [
    ("<OWNER>要参加国家级职业生涯规划大赛（A3），本周末20点前交",
     "<OWNER>参加过国家级职业生涯规划大赛（A3）",
     "去掉已失效的「本周末20点前交」，参赛这件事保留"),
    ("绯栀连问<OWNER>困不困、在忙什么，<OWNER>没回，最后说要去睡觉",
     "绯栀连问<OWNER>困不困、在忙什么，<OWNER>最后说要去睡觉",
     "去掉瞬时状态「没回」，事件本身保留"),
]

snap = ROOT / "eval" / ("pre_fix_" + time.strftime("%Y%m%d-%H%M%S"))
snap.mkdir(parents=True, exist_ok=False)
for f in STATE.iterdir():
    if f.is_file():
        shutil.copy2(f, snap / f.name)
print("快照：%s\n" % snap)

m = FeizhiMemory(MEM)


def locate(text):
    hits = [x for x in m._view() if str(x.get("text")) == text]
    if len(hits) != 1:
        print("定位失败：%r 命中 %d 条" % (text, len(hits)))
        sys.exit(2)
    return hits[0]


before_live = len(R.recallable(m._view()))
before_render = m.render()

for text, why in ARCHIVE:
    rec = locate(text)
    m.archive_record(rec["id"], reason=why)
    print("归档 %s  %s" % (rec["id"], text[:34]))

for old, new, why in REWRITE:
    rec = locate(old)
    res = m.update_record(rec["id"], {"text": new}, reason=why)
    notes = res.get("notes") or []
    print("改写 %s  %s -> %s%s"
          % (rec["id"], old[:22], new[:22],
             ("  【note】" + "；".join(map(str, notes))) if notes else ""))

view = m._view()
after_live = len(R.recallable(view))
after_arch = sum(1 for x in view if x.get("archived"))
need_review = sum(1 for x in R.recallable(view) if x.get("needs_review"))
after_render = m.render()

print()
print("可召回 %d -> %d ；归档 %d ；待复核 %d"
      % (before_live, after_live, after_arch, need_review))

stale = ["明天9点有课", "前天买的半盒酸奶", "待会儿下碗面", "今早干的蠢事", "<OWNER>还没回"]
leak = [w for w in stale if w in after_render]
print("渲染里残留的时效缺陷：%d 处%s" % (len(leak), ("  " + str(leak)) if leak else ""))

if before_render == after_render:
    print("警告：render 没有任何变化，动作可能没生效")
    sys.exit(1)
if need_review:
    print("警告：出现新的待复核记录，需要人看")
    sys.exit(1)
