# -*- coding: utf-8 -*-
"""逐条导出一次运行的全部输出及其来源原文，供人工复核。

不调模型、不改任何状态：只读生产库取原消息文本。

用法: python _audit_records.py sample_run_m1a.json
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
EVAL = HERE / "eval"
DB = HERE / "state" / "context.sqlite3"
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def load_texts(ids) -> dict:
    if not ids:
        return {}
    con = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True)
    q = ",".join("?" * len(ids))
    rows = con.execute(
        "SELECT id, role, text FROM messages WHERE id IN (%s)" % q,
        list(ids)).fetchall()
    con.close()
    return {r[0]: ("<OWNER>" if r[1] == "user" else "绯栀", r[2] or "") for r in rows}


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "sample_run_m1a.json"
    d = json.loads((EVAL / name).read_text(encoding="utf-8"))
    total = 0
    for b in d["batches"]:
        print()
        print("=" * 78)
        print("批 %s  （%d 条）" % (b["id"], len(b.get("added") or [])))
        print("=" * 78)
        for a in b.get("added") or []:
            total += 1
            ids = a.get("source_msg_ids") or []
            texts = load_texts(ids)
            print("%s/%s [%s %s] %s"
                  % (b["id"], a["id"], a["kind"], a.get("certainty") or "-",
                     a["text"]))
            if a.get("event_time") or a.get("time_raw"):
                print("     时间：et=%r raw=%r" % (a.get("event_time"),
                                                 a.get("time_raw")))
            for i in ids:
                who, t = texts.get(i, ("?", "（取不到）"))
                print("     源#%s %s：%s" % (i, who, t.replace("\n", " ")[:88]))
            if not ids:
                print("     源：（无）")
    print()
    print("合计 %d 条" % total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
