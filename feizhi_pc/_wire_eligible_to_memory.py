# -*- coding: utf-8 -*-
"""副本端接线：eligible → kind/时间 → 记忆召回。**全程不碰生产。**

YG 定的接线验收项：
  1. pending 隔离：pending/rejected 一律不得进入召回
  2. 提交失败恢复：写入失败不得留下半条记录
  3. 重放幂等：同一批重复提交不产生重复

数据来源：
  * 闸门账本 = v1.3 `verified_candidates_v1_3.sqlite3` 的**副本**
  * kind 阶段 = `gold_kind_v2.json` 的人工标签（**模拟**上游 kind 输出，如实标注）
  * 记忆库 = 临时目录里的空 `feizhi_memory.json`

用法: python _wire_eligible_to_memory.py
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
EVAL = HERE / "eval"
ARCH = EVAL / "source_verification_20261026" / "work" / "source-verification-v1_1"
LEDGER_SRC = ARCH / "verified_candidates_v1_3.sqlite3"
KIND_V2 = EVAL / "gold_kind_v2.json"
DB = HERE / "state" / "context.sqlite3"
OUT = EVAL / "wire_eligible.json"
BJ = timezone(timedelta(hours=8))

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ARCH))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

import memrec as R          # noqa: E402
import memory as M          # noqa: E402
import review_ledger as RL  # noqa: E402

RES = {"pass": 0, "fail": 0}


def check(label, cond, detail=""):
    RES["pass" if cond else "fail"] += 1
    print("   %s %-50s %s" % ("[ OK ]" if cond else "[FAIL]", label, str(detail)[:52]))
    return cond


def head(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


def load_rows(ids):
    ids = [int(i) for i in ids if str(i).isdigit()]
    if not ids:
        return []
    con = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True)
    q = ",".join("?" * len(ids))
    rows = con.execute(
        "SELECT id, role, text, sent_at_ms FROM messages WHERE id IN (%s)" % q,
        ids).fetchall()
    con.close()
    return [{"id": r[0], "role": r[1], "text": r[2] or "",
             "sent_at_ms": r[3], "peer_wxid": "<WXID_FRIEND_A>"} for r in rows]


def to_item(cand: dict, kind: str) -> dict:
    return {"text": cand.get("text"),
            "source_msg_ids": cand.get("source_msg_ids") or [],
            "time_raw": cand.get("time_raw") or "",
            "time_anchor_msg_id": cand.get("time_anchor_msg_id"),
            "certainty": "high",
            "_kind": kind}


def main() -> int:
    if not LEDGER_SRC.exists():
        print("找不到账本：", LEDGER_SRC)
        return 2
    kind_map = {}
    kmeta = json.loads(KIND_V2.read_text(encoding="utf-8"))
    for r in kmeta["rows"]:
        kind_map[r["cid"]] = r["ref"] if r["status"] == "decided" else "event"

    tmp = Path(tempfile.mkdtemp(prefix="wire_"))
    ok = True
    try:
        led_path = tmp / "ledger.sqlite3"
        shutil.copy2(LEDGER_SRC, led_path)
        mem = M.FeizhiMemory(tmp / "feizhi_memory.json")

        head("0. 账本现状（副本）")
        led = RL.ReviewLedger(led_path)
        # ★ 必须用账本的完整 candidate_key（`A/c1`）去查人工 kind 表。
        #   账本导出的是**局部 cid**（`c1`），直接用它查会零命中、全部落默认值 ——
        #   这正是上一版 20 项断言的实证错误：断言的只是"全 event 接线"。
        con = sqlite3.connect(str(led_path))
        con.row_factory = sqlite3.Row
        rows_db = con.execute(
            "SELECT candidate_key, candidate_json FROM candidates"
            " WHERE route='eligible' ORDER BY candidate_key").fetchall()
        con.close()
        eligible = [dict(r) for r in rows_db]
        pending = led.pending_reviews()
        kind_hit = sum(1 for r in eligible if r["candidate_key"] in kind_map)
        print("   eligible %d 条，pending %d 条；人工 kind 表命中 %d 条"
              % (len(eligible), len(pending), kind_hit))
        ok &= check("eligible 数量为 75", len(eligible) == 75, len(eligible))
        ok &= check("pending 数量为 4", len(pending) == 4, len(pending))
        ok &= check("人工 kind 表**全部命中**（不再是零命中）",
                    kind_hit == len(eligible), "%d/%d" % (kind_hit, len(eligible)))
        ok &= check("pending 全部 eligible_for_kind_time=False",
                    all(not p.get("eligible_for_kind_time") for p in pending))
        ok &= check("pending 全部 write_authorized=False",
                    all(not p.get("write_authorized") for p in pending))

        head("1. eligible → kind/时间 → 记忆（gate_state=eligible）")
        by_kind = {"fact": [], "event": []}
        for r in eligible:
            c = json.loads(r["candidate_json"])
            k = kind_map[r["candidate_key"]]
            by_kind[k if k in by_kind else "event"].append(to_item(c, k))
        n_fact = sum(1 for r in eligible if kind_map[r["candidate_key"]] == "fact")
        print("   kind 分布：fact %d、event %d（人工 v2 标签）"
              % (n_fact, len(eligible) - n_fact))
        nf = ne = 0
        for k, items in by_kind.items():
            if not items:
                continue
            rows = load_rows([i for it in items for i in it["source_msg_ids"]])
            q, p, pr, fails = mem._ingest("facts" if k == "fact" else "events",
                                          items, rows, gate_state="eligible",
                                          trim=False)
            if k == "fact":
                nf = q
            else:
                ne = q
            print("   %s：新增 %d，隔离 %d，提升 %d，跳过 %d"
                  % (k, q, p, pr, len(fails)))
        view = mem._view()
        rec_all = R.recallable(view)
        ok &= check("记忆库写入 75 条", len(view) == 75, len(view))
        ok &= check("可召回 75 条", len(rec_all) == 75, len(rec_all))
        ok &= check("全部 gate_state=eligible",
                    all(x.get("gate_state") == "eligible" for x in view))
        with_time = [x for x in view if x.get("event_time")]
        ok &= check("有事件时间的记录存在", len(with_time) > 0, len(with_time))

        head("2. pending 隔离：写进去也必须召回不到")
        p_items = []
        for p in pending:
            c = p["candidate"]
            # ★ 必须用完整 candidate_key，不能用局部 cid：
            #   否则 A/c19 这类会查不到、静默回退成 event（实测踩过）。
            key = p.get("candidate_key") or ""
            kind = kind_map.get(key)
            if kind is None:
                raise SystemExit("pending 候选 %r 在人工 kind 表里查不到" % key)
            p_items.append(to_item(c, kind))
        rows = load_rows([i for it in p_items for i in it["source_msg_ids"]])
        for k in ("facts", "events"):
            sub = [it for it in p_items if it["_kind"] == ("fact" if k == "facts" else "event")]
            if sub:
                mem._ingest(k, sub, rows, gate_state="pending", trim=False)
        view2 = mem._view()
        rec2 = R.recallable(view2)
        p_texts = [it["text"] for it in p_items]
        rendered = mem.render()
        leaked = [t for t in p_texts if t and t in rendered]
        ok &= check("库里有 pending 记录", any(x.get("gate_state") == "pending" for x in view2),
                    sum(1 for x in view2 if x.get("gate_state") == "pending"))
        ok &= check("recallable 不含 pending",
                    not any(x.get("gate_state") == "pending" for x in rec2))
        ok &= check("render 里不出现 pending 正文", not leaked, leaked[:2])
        ok &= check("可召回数量仍为 75", len(rec2) == 75, len(rec2))

        head("3. 提交失败恢复：坏候选不得留半条")
        before = len(mem._view())
        bad = {"text": "<OWNER>要交材料", "source_msg_ids": [], "time_raw": ""}
        try:
            R.add_record(mem._view(), dict(bad), [], mem.data.get("last_mid", 0),
                         gate_state="eligible")
            ok &= check("无来源应被拒", False)
        except R.RecordError as e:
            ok &= check("无来源被拒", True, str(e)[:40])
        ok &= check("记忆库条数未变", len(mem._view()) == before,
                    "%d → %d" % (before, len(mem._view())))
        # 整批回滚语义：坏条目不影响同批好条目，但不写半条
        mix = [{"text": "<OWNER>有早八", "source_msg_ids": [396], "time_raw": "今天",
                "time_anchor_msg_id": 396, "certainty": "high", "_kind": "event"},
               {"text": "坏条目", "source_msg_ids": [999999], "time_raw": "",
                "certainty": "high", "_kind": "event"}]
        rows3 = load_rows([396, 999999])
        q3, pq3, pr3, fails3 = mem._ingest("events", mix, rows3, gate_state="eligible", trim=False)
        ok &= check("好条目入库、坏条目进隔离区",
                    q3 == 1 and pq3 == 1, "新增%d 隔离%d" % (q3, pq3))
        ok &= check("坏条目不在召回里",
                    not any("坏条目" in x.get("text", "") for x in R.recallable(mem._view())))

        head("4. 重放幂等：同一批再跑一次")
        n_before = len(mem._view())
        for k, items in by_kind.items():
            if not items:
                continue
            rows = load_rows([i for it in items for i in it["source_msg_ids"]])
            mem._ingest("facts" if k == "fact" else "events", items, rows, gate_state="eligible", trim=False)
        n_after = len(mem._view())
        ok &= check("重放后条数不变", n_after == n_before,
                    "%d → %d" % (n_before, n_after))

        head("5. 落盘与重载")
        mem.save()
        mem2 = M.FeizhiMemory(tmp / "feizhi_memory.json")
        ok &= check("重载后条数一致", len(mem2._view()) == len(mem._view()))
        ok &= check("gate_state 持久化",
                    all("gate_state" in x for x in mem2._view()))
        ok &= check("重载后 pending 仍不可召回",
                    not any(x.get("gate_state") == "pending"
                            for x in R.recallable(mem2._view())))
        led.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    head("结论：%d 通过 / %d 失败" % (RES["pass"], RES["fail"]))
    OUT.write_text(json.dumps({
        "_meta": {"ran_at": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"),
                  "ledger": str(LEDGER_SRC),
                  "kind_source": "gold_kind_v2.json（人工标签，模拟上游 kind 阶段）",
                  "note": "全程在临时副本上；未触碰生产记忆与数据库"},
        "results": RES}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已写入", OUT)
    return 0 if ok and RES["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
