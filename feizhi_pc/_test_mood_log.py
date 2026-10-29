# -*- coding: utf-8 -*-
"""情绪时间线回归：心情要留痕，不能被下一次 tick 覆盖。

背景：原来 `mood` 只有一个 {state, cause, since}，tick 一次覆盖一次，
她永远只知道"此刻什么心情"，说不出"我这几天一直没睡好"。
"""
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from life import FeizhiLife, MAX_MOOD_LOG, period_of_day   # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, extra="") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✓ %s" % name)
    else:
        FAIL += 1
        print("  ✗ %s %s" % (name, extra))


def main() -> int:
    tmp = Path(tempfile.mkdtemp()) / "life.json"
    life = FeizhiLife(tmp, keep_private_keys=False)

    print("[1] 三次不同心情 → 时间线留三段")
    life.set_mood("有点空", "海报交了但心里没着落")
    time.sleep(0.01)
    life.set_mood("困到发飘", "两点多了眼睛都是重影")
    time.sleep(0.01)
    life.set_mood("下午犯懒又有点悬着", "海报快交了却不敢点发送")
    log = life.data.get("mood_log") or []
    check("时间线 3 段", len(log) == 3, log)
    check("最新一段是当下", log[-1]["state"] == "下午犯懒又有点悬着", log[-1])

    print()
    print("[2] 同一股劲重复设定 → 只更新时间，不重复堆")
    life.set_mood("下午犯懒又有点悬着", "海报快交了却不敢点发送")
    log = life.data.get("mood_log") or []
    check("仍 3 段（没有变 4 段）", len(log) == 3, len(log))

    print()
    print("[3] 渲染里带出「这几天」，但不含当下这条")
    text = life.render(include_loops=False)
    check("有这几天的心情段落", "这几天的心情是这么过来的" in text)
    check("时间线里出现「有点空」", "有点空" in text)
    check("时间线里出现「困到发飘」", "困到发飘" in text)
    tail = text.split("这几天的心情是这么过来的：")[-1].split("\n")[0]
    check("当下这条没被当成历史重复列出", "悬着" not in tail, tail)
    print("     时间线：%s" % tail)

    print()
    print("[4] 同一天的心情用「今天/昨天」说法")
    now = time.localtime()
    same_day = time.strftime("%Y-%m-%d %H:%M", now)
    check("今天的显示", life._short_when(same_day).startswith("今天"),
          life._short_when(same_day))
    y = time.localtime(time.time() - 86400)
    check("昨天的显示",
          life._short_when(time.strftime("%Y-%m-%d %H:%M", y)).startswith("昨天"),
          life._short_when(time.strftime("%Y-%m-%d %H:%M", y)))

    print()
    print("[5] 超过上限会裁剪最旧的")
    for i in range(MAX_MOOD_LOG + 4):
        life.set_mood("心情%d" % i, "测试")
    log = life.data.get("mood_log") or []
    check("长度收敛到 %d" % MAX_MOOD_LOG, len(log) == MAX_MOOD_LOG, len(log))
    check("最旧的已被裁掉", all(x["state"] != "有点空" for x in log))

    print()
    print("[6] 落盘后重载，时间线还在")
    life.save()
    again = FeizhiLife(tmp, keep_private_keys=False)
    check("重载后长度一致",
          len(again.data.get("mood_log") or []) == MAX_MOOD_LOG,
          len(again.data.get("mood_log") or []))

    print()
    print("=" * 62)
    print("结论：%d 通过 / %d 失败" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
