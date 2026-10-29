"""清理 facts 桶里的伪事件：7 条。

两类，判据不同：
  * 跨桶重复（6 条）—— 同一件事既进了 facts 又进了 events。
    events 版本带语境、信息更全，保留 events，归档 facts 这版。
  * 一次性琐事（1 条）—— events 里没有对应，但按 EXTRACT_SYSTEM 自己写的
    「只记具体的、以后能复用的信息」本来就不该入账。

★ 保留的那条反例（m0011「<OWNER>参加过国家级职业生涯规划大赛」）判为**真 fact**：
  这句话今天成立、明年也成立，不是「只能指代某一次」的描述。
  程序靠「了/过」粗筛会把它误报，这里不跟着错。
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

# (记录 id, 期望正文片段, 归档理由)
TARGETS = [
    ("m0051", "海报改到第三版", "与 m0092「把海报第三版靛蓝贴回去的照片发给他看」是同一件事"),
    ("m0058", "倒猫粮手抖倒多了", "与 m0094「跟他说糊糊猫粮倒多了撑趴地上的蠢事」是同一件事"),
    ("m0062", "magichut", "与 m0102「问配色意见，<OWNER>回了个链接说够用了」是同一件事"),
    ("m0063", "muse", "与 m0104「吐槽<OWNER>连艺术都看不懂还搞 muse」是同一件事"),
    ("m0064", "梯子链接", "与 m0103「问梯子链接是干嘛的」是同一件事"),
    ("m0065", "ping0.cc", "与 m0105「<OWNER>接连甩网址给绯栀」是同一件事"),
    ("m0050", "上课路上买了吃的", "一次性琐事，events 里没有对应，也不属于可复用信息"),
]

snap = ROOT / "eval" / ("pre_kind_fix_" + time.strftime("%Y%m%d-%H%M%S"))
snap.mkdir(parents=True, exist_ok=False)
for f in STATE.iterdir():
    if f.is_file():
        shutil.copy2(f, snap / f.name)
print("快照：%s\n" % snap)

m = FeizhiMemory(MEM)
before_facts = len([x for x in R.recallable(m._view()) if x.get("kind") != "event"])
before_events = len([x for x in R.recallable(m._view()) if x.get("kind") == "event"])
before_render = m.render()

for rid, must_have, why in TARGETS:
    hit = [x for x in m._view() if str(x.get("id")) == rid]
    if len(hit) != 1:
        print("定位失败：%s 命中 %d 条" % (rid, len(hit)))
        sys.exit(2)
    text = str(hit[0].get("text"))
    if must_have not in text:
        print("正文对不上：%s 期望含 %r，实际 %r" % (rid, must_have, text))
        sys.exit(2)
    m.archive_record(rid, reason=why)
    print("归档 %s  %s" % (rid, text[:38]))

view = m._view()
after_facts = len([x for x in R.recallable(view) if x.get("kind") != "event"])
after_events = len([x for x in R.recallable(view) if x.get("kind") == "event"])
after_render = m.render()

print()
print("fact %d -> %d ；event %d -> %d ；归档 %d"
      % (before_facts, after_facts, before_events, after_events,
         sum(1 for x in view if x.get("archived"))))
print("待复核 %d" % sum(1 for x in R.recallable(view) if x.get("needs_review")))

leak = [t for t in ("magichut", "ping0.cc", "倒猫粮", "买吃的", "梯子链接", "muse")
        if t in after_render]
print("渲染里仍残留的跨桶重复：%s" % (leak if leak else "无"))

if after_facts != before_facts - len(TARGETS):
    print("警告：fact 数量变化与预期不符")
    sys.exit(1)
