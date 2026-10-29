"""回访（open_loops）：登记她问过的事、判断该不该问、问了计数、过期不提。"""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

import life as life_mod
from life import FeizhiLife

fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name, "->", got, "" if ok else "want " + str(want))


tmp = Path(tempfile.mkdtemp()) / "life.json"
L = FeizhiLife(tmp)

# --- 问句提取：只认"问他的"、长度合理 ---
qs = FeizhiLife._extract_questions(
    "你那PPT做完了吗？我今天画崩了，烦。你会来吗？好")
check("提取问句", qs, ["你那PPT做完了吗", "你会来吗"])

check("太短不认", FeizhiLife._extract_questions("你？"), [])
check("自问自答不认", FeizhiLife._extract_questions("我今天怎么了？"), [])
check("祈使句不认",
      FeizhiLife._extract_questions("嗯什么嗯呀，你倒是闭眼。不说这个了，你听着就行，别应我。"),
      [])
check("省略问号也认", FeizhiLife._extract_questions("你吃了吗。"), ["你吃了吗"])
check("多问句", FeizhiLife._extract_questions("你那PPT交了？老师骂你了吗？"), ["你那PPT交了", "老师骂你了吗"])

# --- 登记 + 去重 ---
check("首次登记", L.add_loop("你那PPT做完了吗？"), 1)
check("近似去重", L.add_loop("你那 PPT 做完了吗"), 0)
check("登记第二件", L.add_loop("你那个比赛报名了没？"), 1)

# --- 刚问完不该回访（LOOP_MIN_AGE_H = 2h）---
check("刚问不回访", len(L.due_loops()), 0)

# 把时间推到 5 小时前
for lp in L.data["open_loops"]:
    lp["ts"] = int(time.time()) - 5 * 3600
L.save()
due = L.due_loops()
check("5 小时后可回访", len(due), 2)

# --- 他答过了：优先回访那些"答过但没说结果"的 ---
L.data["open_loops"][0]["ts"] = int(time.time()) - 20 * 3600
L.data["open_loops"][0]["status"] = "answered"
L.save()
due = L.due_loops()
check("answered 优先", due[0]["asked"], L.data["open_loops"][0]["asked"])

# --- 回访计数与自动关闭 ---
ids = [lp["id"] for lp in due]
L.mark_followed(ids)
check("回访计数 +1", L.data["open_loops"][0]["follow_ups"], 1)
L.mark_followed(ids)
check("问满两次关闭", L.data["open_loops"][0]["status"], "closed")
check("关闭后不再出现", any(lp["asked"] == L.data["open_loops"][0]["asked"]
                        for lp in L.due_loops()), False)

# --- 过期不提（>72h）---
for lp in L.data["open_loops"]:
    if lp["status"] != "closed":
        lp["ts"] = int(time.time()) - 100 * 3600
        lp["follow_ups"] = 0
L.save()
check("超过 3 天不提", len(L.due_loops()), 0)

# --- render 注入 / include_loops 开关 ---
for lp in L.data["open_loops"]:
    if lp["status"] == "closed":
        lp["status"] = "open"
        lp["follow_ups"] = 0
    lp["ts"] = int(time.time()) - 6 * 3600
L.data["projects"] = [{"id": "p1", "title": "海报", "status": "ongoing", "beats": []}]
L.save()
r = L.render()
check("render 含挂念段", "你还惦记着的几件事" in r, True)
check("render(include_loops=False) 不含", "你还惦记着的几件事" in L.render(include_loops=False), False)
check("render 仍含日子", "手上正在弄的" in L.render(include_loops=False), True)

# --- note_answered ---
expect_before = len([lp for lp in L.data["open_loops"] if lp["status"] == "open"])
n = L.note_answered()
check("note_answered 数目", n, expect_before)
check("answer 后变 answered",
      all(lp["status"] in ("answered", "closed")
          for lp in L.data["open_loops"] if lp["follow_ups"] == 0), True)

# 落盘可读回
L2 = FeizhiLife(tmp)
check("重新加载后 loops 保留", len(L2.data["open_loops"]) > 0, True)

print("\n临时文件:", tmp)
print("FAILS =", fails)
sys.exit(0 if fails == 0 else 1)
