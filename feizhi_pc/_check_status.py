# -*- coding: utf-8 -*-
"""只读检查绯栀的运行状态与最新对话时间。"""
from __future__ import annotations

import datetime
import json
import sqlite3
import sys
from pathlib import Path

STATE = Path(r"<PROJECT_ROOT>\feizhi_pc\state")
DB = STATE / "context.sqlite3"
BJ = datetime.timezone(datetime.timedelta(hours=8))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def fmt(ms):
    return datetime.datetime.fromtimestamp(int(ms) / 1000, BJ).strftime("%Y-%m-%d %H:%M")


def main() -> int:
    con = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True)
    n = con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    lo, hi = con.execute("SELECT MIN(id), MAX(id) FROM messages").fetchone()
    print("消息总数 %d，id %s..%s" % (n, lo, hi))
    print()
    print("最新 6 条：")
    for r in con.execute("SELECT id, role, text, sent_at_ms FROM messages"
                         " ORDER BY id DESC LIMIT 6"):
        print("  #%s [%s] %s：%s"
              % (r[0], fmt(r[3]), "<OWNER>" if r[1] == "user" else "绯栀",
                 (r[2] or "").replace("\n", " ")[:46]))
    last_ms = con.execute("SELECT MAX(sent_at_ms) FROM messages").fetchone()[0]
    last_user = con.execute(
        "SELECT MAX(sent_at_ms) FROM messages WHERE role='user'").fetchone()[0]
    try:
        pend = con.execute("SELECT COUNT(*) FROM outbound WHERE status='pending'").fetchone()[0]
    except Exception:  # noqa: BLE001
        pend = "?"
    con.close()

    now = datetime.datetime.now(BJ)
    print()
    print("最后一条消息：", fmt(last_ms), "（距今 %.1f 小时）"
          % ((now.timestamp() * 1000 - last_ms) / 3600000))
    print("最后一条<OWNER>：", fmt(last_user), "（距今 %.1f 天）"
          % ((now.timestamp() * 1000 - last_user) / 86400000))
    print("outbound pending：", pend)
    print("现在：", now.strftime("%Y-%m-%d %H:%M"), "星期", "一二三四五六日"[now.weekday()])

    life = STATE / "feizhi_life.json"
    if life.exists():
        d = json.loads(life.read_text(encoding="utf-8"))
        print()
        print("生活状态文件字段：", list(d.keys())[:12])
        for k in ("last_tick", "mood", "energy", "sleeping", "awake"):
            if k in d:
                v = d[k]
                if isinstance(v, (int, float)) and k == "last_tick" and v > 1e11:
                    v = fmt(v)
                print("   %s = %s" % (k, v))
    print()
    print("state 目录时间线：")
    for p in sorted(STATE.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:8]:
        print("   %-26s %s" % (p.name,
                               datetime.datetime.fromtimestamp(p.stat().st_mtime, BJ)
                               .strftime("%m-%d %H:%M")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
