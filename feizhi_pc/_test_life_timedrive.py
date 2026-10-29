# -*- coding: utf-8 -*-
"""验证「时间驱动」的生活推进：不喂任何聊天内容，看她自己怎么过一天。

用副本做实验，绝不碰 state/feizhi_life.json。

三次实验对应三个时段，看她会不会按时间说话：
  深夜 02:00 —— 该困、该垮，不该精神很好
  上午 09:30 —— 画室 / 早八
  傍晚 18:40 —— 饭点、收工
"""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import logging  # noqa: E402
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from life import FeizhiLife, period_of_day  # noqa: E402
from llm import LLMClient                   # noqa: E402

SRC = ROOT / "state" / "feizhi_life.json"


def at(hour: int, minute: int = 0, days_ago: int = 0) -> float:
    t = time.localtime()
    base = time.mktime((t.tm_year, t.tm_mon, t.tm_mday - days_ago,
                        hour, minute, 0, 0, 0, -1))
    return base


def run_case(name: str, now: float, gap_hours: float) -> None:
    tmp = ROOT / "state" / ("_life_test_%s.json" % name)
    shutil.copy(SRC, tmp)
    d = json.loads(tmp.read_text(encoding="utf-8"))
    # 把 last_tick 拨到 gap_hours 之前，触发 need_tick
    d["last_tick"] = time.strftime(
        "%Y-%m-%d %H:%M", time.localtime(now - gap_hours * 3600))
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    life = FeizhiLife(tmp)
    before = [(p.get("title"), (p.get("beats") or [{}])[-1].get("text", ""))
              for p in life.ongoing()]
    print("=" * 66)
    print("场景 %s  目标时刻 %s %s  间隔 %.1fh"
          % (name, time.strftime("%H:%M", time.localtime(now)),
             period_of_day(time.localtime(now).tm_hour), gap_hours))
    print("  推进前：", before)
    r = life.tick(LLMClient(), now=now)
    print("  返回：", json.dumps(r, ensure_ascii=False))
    after = [(p.get("title"), p.get("status"),
              (p.get("beats") or [{}])[-1].get("text", ""))
             for p in life.data.get("projects", [])]
    print("  推进后：")
    for t, s, b in after:
        print("    [%s] %s —— %s" % (s, t, b))
    print("  心情：", json.dumps(life.data.get("mood") or {}, ensure_ascii=False))
    tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    run_case("深夜", at(2, 10), 9.0)
    run_case("上午", at(9, 30, days_ago=1), 7.0)
    run_case("傍晚", at(18, 40, days_ago=2), 30.0)
