# -*- coding: utf-8 -*-
"""把**保存的原始模型输出**用当前代码重新入库并重评。

YG 指出的关键点：只对旧 `added` 重评分**不会**应用新校验 ——
必须重放 `raw_output`，重新走一遍解析 + `_ingest` + 渲染。

用法:
    python _replay_raw.py sample_run_v1.json
    python _replay_raw.py sample_run_v2.json

输出 `eval/replay_<原名>.json`，格式与 `sample_run.json` 一致，
可直接喂给 `_review_sample.py`。
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
EVAL = HERE / "eval"
DB = HERE / "state" / "context.sqlite3"
GOLD = EVAL / "gold_v1.json"
PEER = "<WXID_FRIEND_A>"

sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
logging.getLogger("feizhi_pc.memory").setLevel(logging.CRITICAL)

import memrec as R          # noqa: E402
import memory as M          # noqa: E402

BJ = timezone(timedelta(hours=8))


class StaticLLM:
    """永远返回**保存下来的那段原始输出**，不调任何模型。"""

    def __init__(self, raw: str):
        self.raw = raw
        self.calls = 0

    def chat(self, system: str, user: str, **kw):
        self.calls += 1
        return self.raw


class StaticStore:
    def __init__(self, rows):
        self.rows = rows

    def recent(self, limit: int = 120):
        return list(self.rows)


def load_rows(lo: int, hi: int) -> list[dict]:
    """从生产库**只读**取原始消息（不用保存时被截断的文本）。"""
    con = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True)
    cur = con.execute(
        "SELECT id, peer_wxid, role, text, sent_at_ms, source FROM messages"
        " WHERE id BETWEEN ? AND ? ORDER BY id", (lo, hi))
    cols = ["id", "peer_wxid", "role", "text", "sent_at_ms", "source"]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    for r in rows:
        r["peer_wxid"] = PEER
    return rows


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python _replay_raw.py sample_run_v1.json")
        return 2
    src = EVAL / sys.argv[1]
    if not src.exists():
        print("找不到", src)
        return 2
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    old = json.loads(src.read_text(encoding="utf-8"))
    olds = {b["id"]: b for b in old["batches"]}
    print("重放：", src.name, " 原模型：", old["_meta"]["model"])
    print("说明：只重放**已保存的原始输出**，不调用模型；")
    print("      消息体从生产库只读重取（保存件里的 text 被截到 300 字）。")
    print()

    tmp = Path(tempfile.mkdtemp(prefix="feizhi_replay_"))
    out = {"_meta": {"replay_of": src.name,
                     "ran_at": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"),
                     "model": old["_meta"]["model"],
                     "note": "旧输出 + 当前代码"},
           "batches": []}
    try:
        for gb in gold["batches"]:
            bid = gb["id"]
            ob = olds.get(bid)
            if not ob or not ob.get("raw_output"):
                print("[跳过] %s 没有保存的原始输出" % bid)
                continue
            lo, hi = gb["range"]
            rows = load_rows(lo, hi)
            m = M.FeizhiMemory(tmp / ("replay_%s.json" % bid))
            llm = StaticLLM(ob["raw_output"][0])
            res = m.maybe_extract(StaticStore(rows), PEER, llm,
                                  min_new=8, min_interval=0.0)
            added = [{k: x.get(k) for k in
                      ("id", "kind", "text", "certainty", "source_msg_ids",
                       "speaker", "time_raw", "time_raw_at_ms",
                       "time_anchor_msg_id", "event_time", "time_basis",
                       "needs_review", "quarantined")}
                     for x in m._view()]
            out["batches"].append({
                "id": bid, "model": old["_meta"]["model"],
                "msg_count": len(rows), "raw_output": [llm.raw],
                "result": res, "added": added,
                "recallable_after": len(R.recallable(m._view())),
            })
            print("批 %s：新增 %d 条，partial=%s%s"
                  % (bid, len(added), res.get("partial"),
                     "，" + "；".join((res.get("ingest_fails") or [])[:3])
                     if res.get("ingest_fails") else ""))
            for a in added:
                if a["time_raw"] or a["event_time"]:
                    print("   %-6s raw=%-12r et=%-11s 原话时间=%s  正文=%s"
                          % (a["id"], a["time_raw"], a["event_time"],
                             (datetime.fromtimestamp(a["time_raw_at_ms"] / 1000, tz=BJ)
                              .strftime("%Y-%m-%d") if a.get("time_raw_at_ms") else "未知"),
                             (a["text"] or "")[:32]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    dst = EVAL / ("replay_" + src.name)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("已写入", dst)
    print("下一步： python _review_sample.py %s" % dst.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
