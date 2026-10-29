# -*- coding: utf-8 -*-
"""只读扫描生产上下文库，为小样本验证挑选批次。**不写入任何文件。**

用法:
    python _scan_samples.py            # 概览
    python _scan_samples.py 480 520    # 打印 id 区间的消息
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = Path(r"<PROJECT_ROOT>\feizhi_pc\state\context.sqlite3")
BJ = timezone(timedelta(hours=8))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def fmt(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=BJ).strftime("%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return "??"


def main() -> int:
    con = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True)
    n, lo, hi = con.execute(
        "SELECT COUNT(*), MIN(id), MAX(id) FROM messages").fetchone()
    print("消息总数 = %d，id 范围 %s..%s" % (n, lo, hi))

    if len(sys.argv) >= 2 and sys.argv[1] == "--time":
        kws = ("明天", "后天", "昨天", "前天", "今天", "昨天", "下周", "上周",
               "月", "去年", "前年", "周末", "生日", "考试", "上班", "加班")
        rows = con.execute(
            "SELECT id, role, sent_at_ms, text FROM messages ORDER BY id").fetchall()
        print("\n含时间/事件词的消息：")
        for (mid, role, sent, text) in rows:
            t = text or ""
            hit = [k for k in kws if k in t]
            if not hit:
                continue
            who = "<OWNER>" if role == "user" else "绯栀"
            print("#%-4d [%s] %s(%s)：%s"
                  % (mid, fmt(sent), who, "/".join(hit[:3]), t[:100]))
        con.close()
        return 0

    print("按 source 分布 =", dict(con.execute(
        "SELECT source, COUNT(*) FROM messages GROUP BY source").fetchall()))
    print("按角色分布 =", dict(con.execute(
        "SELECT role, COUNT(*) FROM messages GROUP BY role").fetchall()))
    print("peer =", dict(con.execute(
        "SELECT peer_wxid, COUNT(*) FROM messages GROUP BY peer_wxid").fetchall()))

    a, b = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) >= 3 else (0, 0)
    if a and b:
        print()
        rows = con.execute(
            "SELECT id, role, sent_at_ms, text FROM messages"
            " WHERE id BETWEEN ? AND ? ORDER BY id", (a, b)).fetchall()
        for (mid, role, sent, text) in rows:
            who = "<OWNER>" if role == "user" else "绯栀"
            t = (text or "").replace("\n", " ⏎ ")
            print("#%-4d [%s] %s：%s" % (mid, fmt(sent), who, t[:110]))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
