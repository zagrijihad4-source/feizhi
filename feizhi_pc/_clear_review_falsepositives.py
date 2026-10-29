# -*- coding: utf-8 -*-
"""按新规则重跑一遍 validate，清掉「双人互动被误标复核」的噪音。

只对**已有记录**重新校验，不改文案、不改时间字段；
需要 batch_msgs（来源原文）才能重算，所以从生产库只读取引用到的消息。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import memrec as R      # noqa: E402
import memory as M      # noqa: E402

DB = HERE / "state" / "context.sqlite3"
PEER = "<WXID_FRIEND_A>"


def load_rows(ids):
    ids = sorted({int(i) for i in ids if str(i).isdigit()})
    if not ids:
        return []
    con = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True)
    q = ",".join("?" * len(ids))
    rows = con.execute(
        "SELECT id, role, text, sent_at_ms FROM messages WHERE id IN (%s)" % q,
        ids).fetchall()
    con.close()
    return [{"id": r[0], "role": r[1], "text": r[2] or "",
             "sent_at_ms": r[3], "peer_wxid": PEER} for r in rows]


def main() -> int:
    path = HERE / "state" / "feizhi_memory.json"
    m = M.FeizhiMemory(path)
    changed = []
    # ★ 不能靠重算 validate 来清：validate 会**继承**输入的 needs_review=True
    #   （它只在特定分支"设置 True"，不会主动清零），所以旧值会一直留着。
    #   新记录本来就正确（new_record 默认 False），只有历史记录残留了旧规则的标记。
    #   这里按新规则的判据直接判定：
    #     speaker 为空 + 正文显式提到双方 + 没有未定的时间表达  → 属双人互动，清标记
    for bucket in ("facts", "events"):
        for rec in m.data.get(bucket, []):
            if not rec.get("needs_review"):
                continue
            text = str(rec.get("text") or "")
            both = ("绯栀" in text) and ("<OWNER>" in text)
            no_time_issue = not str(rec.get("time_raw") or "").strip()
            if both and no_time_issue and not rec.get("speaker"):
                rec["needs_review"] = False
                changed.append((rec.get("id"), text[:40]))
    if changed:
        m.save()
        print("已清除 %d 条的误报复核：" % len(changed))
        for rid, txt in changed:
            print("  %s  %s" % (rid, txt))
    else:
        print("没有需要清除的复核标记")
    print()
    st = m.stats()
    print("当前：facts %d / events %d / 待复核 %d / 归档 %d"
          % (st["facts"], st["events"], st["needs_review"], st["archived"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
