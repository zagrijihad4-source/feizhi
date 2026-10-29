# -*- coding: utf-8 -*-
"""真实模型小样本抽取跑批。**只读生产 db，写入都在内存/临时目录。**

按 YG 定的实验设计：
  * 标注先行（eval/gold_v1.json 已在调用前落盘，本脚本只读它）
  * 每次处置结果分开记录：正常新增 / 隔离 / 提升 / 重复跳过
  * 保留**原始模型输出**与处置理由，事后逐条人工核对

用法:
    python _run_extract_sample.py            # 跑全部批次
    python _run_extract_sample.py A          # 只跑 A 批
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
OUT = EVAL / "sample_run.json"
PEER = "<WXID_FRIEND_A>"

sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
logging.basicConfig(level=logging.WARNING)

import memrec as R          # noqa: E402
import memory as M          # noqa: E402
import llm as L             # noqa: E402

BJ = timezone(timedelta(hours=8))


class RecordingLLM:
    """包一层，把模型**原始输出**留下来。"""

    def __init__(self, inner, tag=""):
        self.inner = inner
        self.tag = tag
        self.raw: list[str] = []

    def chat(self, system: str, user: str, **kw):
        out = self.inner.chat(system, user, **kw)
        self.raw.append(out)
        return out


class StaticStore:
    """只回一批固定消息，绝不读写生产库。"""

    def __init__(self, rows):
        self.rows = rows

    def recent(self, limit: int = 120):
        return list(self.rows)


def fmt(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=BJ).strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return "?"


def load_rows(lo: int, hi: int) -> list[dict]:
    con = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True)
    cur = con.execute(
        "SELECT id, peer_wxid, role, text, sent_at_ms, source FROM messages"
        " WHERE id BETWEEN ? AND ? ORDER BY id", (lo, hi))
    cols = ["id", "peer_wxid", "role", "text", "sent_at_ms", "source"]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    con.close()
    for r in rows:
        r["peer_wxid"] = PEER          # 统一 peer，避免脏 wxid 干扰过滤
    return rows


def run_batch(batch: dict, tmp: Path, model_tag: str, llm_client) -> dict:
    """跑一批。

    ★ `llm_client` 必须是 `main()` 里那个**锁定单一 provider**的实例。
      上一版这里自己又 `L.LLMClient()` 了一次 —— 默认实例带着完整候选列表，
      于是 `_meta` 写着 `fallback: disabled`，实际调用仍可回退到第二家供应商。
      标签是打印出来的，只有真正传同一个客户端才算锁定。
    """
    bid = batch["id"]
    lo, hi = batch["range"]
    rows = load_rows(lo, hi)
    if len(rows) < 8:
        return {"id": bid, "error": "消息太少（%d）" % len(rows)}

    m = M.FeizhiMemory(tmp / ("mem_%s.json" % bid))
    before = {str(x.get("id") or "") + "|" + str(x.get("text")): dict(x)
              for x in m._view()}
    rec = RecordingLLM(llm_client, bid)
    try:
        res = m.maybe_extract(StaticStore(rows), PEER, rec,
                              min_new=8, min_interval=0.0)
    except Exception as e:  # noqa: BLE001
        return {"id": bid, "error": "%s: %s" % (type(e).__name__, e),
                "raw": rec.raw}

    after = m._view()
    added = []
    for x in after:
        key = str(x.get("id") or "") + "|" + str(x.get("text"))
        if key in before:
            continue
        added.append({
            "id": x.get("id"),
            "kind": x.get("kind"),
            "text": x.get("text"),
            "certainty": x.get("certainty"),
            "source_msg_ids": x.get("source_msg_ids"),
            "speaker": x.get("speaker"),
            "time_raw": x.get("time_raw"),
            "time_raw_at_ms": x.get("time_raw_at_ms"),
            "time_anchor_msg_id": x.get("time_anchor_msg_id"),
            "event_time": x.get("event_time"),
            "time_basis": x.get("time_basis"),
            "needs_review": x.get("needs_review"),
            "quarantined": x.get("quarantined"),
        })
    return {
        "id": bid,
        "model": model_tag,
        "msg_count": len(rows),
        "messages": [{"id": r["id"], "role": r["role"],
                      "sent": fmt(r["sent_at_ms"]),
                      "text": (r["text"] or "")[:300]} for r in rows],
        "raw_output": rec.raw,
        "result": res,
        "added": added,
        "recallable_after": len(R.recallable(after)),
    }


def main() -> int:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    want = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else None
    # ★ 固定单一 provider：默认 `LLMClient()` 会在失败后自动切换到下一个供应商，
    #   而标签仍按候选列表第一项生成 —— 模型变了也看不出来，直接污染提示词对比。
    provider = sys.argv[2] if len(sys.argv) > 2 else "deepseek"
    lc = L.LLMClient(order=[provider])
    spec = dict(L.PROVIDERS.get(provider, {}))
    spec.update(lc.cfg.overrides.get(provider, {}))
    model_name = spec.get("model", "?")
    base_host = str(spec.get("base_url", "")).split("//")[-1].split("/")[0]
    model_tag = "%s/%s" % (provider, model_name)
    print("模型（锁定，无回退）：", model_tag, " base=", base_host or "?")

    tmp = Path(tempfile.mkdtemp(prefix="feizhi_sample_"))
    out = {"_meta": {"ran_at": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"),
                     "provider": provider, "model": model_name,
                     "model_tag": model_tag, "base_host": base_host,
                     "fallback": "disabled（单一 provider，失败单列）",
                     "gold_file": str(GOLD), "peer": PEER},
           "batches": []}
    try:
        for b in gold["batches"]:
            if want and b["id"] not in want:
                continue
            print()
            print("=" * 70)
            print("批 %s  %s  （%d..%d）" % (b["id"], b["span"],
                                           b["range"][0], b["range"][1]))
            print("=" * 70)
            r = run_batch(b, tmp, model_tag, lc)
            out["batches"].append(r)
            if r.get("error"):
                print("  [失败]", r["error"])
                continue
            res = r["result"]
            if res.get("error"):
                # ★ 失败必须单列，不能被当成"这轮没抽到东西"
                print("  [失败，不计入结果] error=%s  raw长度=%d"
                      % (res["error"], sum(len(x) for x in (r.get("raw_output") or []))))
            print("  返回：", {k: res.get(k) for k in
                            ("facts_added", "events_added",
                             "quarantined_added", "promoted", "partial")})
            print("  处置说明：")
            for f in (res.get("ingest_fails") or []):
                print("    -", f)
            print("  新增 %d 条：" % len(r["added"]))
            for a in r["added"]:
                print("    %s [%s] %s" % (a["id"], a["kind"], a["text"]))
                print("        时间=%r basis=%s 来源=%s 隔离=%s 复核=%s"
                      % (a["event_time"], a["time_basis"], a["source_msg_ids"],
                         a["quarantined"], a["needs_review"]))
            print("  原始输出长度：", sum(len(x) for x in r["raw_output"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    EVAL.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("结果已写入", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
