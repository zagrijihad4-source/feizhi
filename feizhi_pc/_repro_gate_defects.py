# -*- coding: utf-8 -*-
"""复现 YG 指出的闸门接线缺陷（全部离线，临时目录）。

D1 cid 前缀混用：人工 kind 表用 `A/c1`，账本导出的是 `c1` → 零命中，全走默认
D2 `_trim` 把 pending 算进容量 → 加一条 pending 会归档一条 eligible
D3 pending 重放会增长（去重集合只含 recallable，不含 pending）
D4 反向提升漏洞：旧 eligible 的隔离项，本次以 pending 补来源提权后仍进召回

用法: python _repro_gate_defects.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

import memrec as R      # noqa: E402
import memory as M      # noqa: E402

PEER = "<WXID_FRIEND_A>"
RES = {"reproduced": 0, "clean": 0}


def say(tag, repro, detail=""):
    RES["reproduced" if repro else "clean"] += 1
    print("   %-8s %s  %s" % ("[复现]" if repro else "[未复现]", tag, detail[:60]))


def rows(mid, n=1):
    return [{"id": mid + i, "role": "user", "text": "消息%d" % i,
             "sent_at_ms": 1792000000000 + i * 1000, "peer_wxid": PEER}
            for i in range(n)]


def main() -> int:
    kmeta = json.loads((HERE / "eval" / "gold_kind_v2.json").read_text(encoding="utf-8"))
    kind_keys = {r["cid"] for r in kmeta["rows"]}
    tmp = Path(tempfile.mkdtemp(prefix="gate_repro_"))
    try:
        print("=" * 76)
        print("D1 cid 前缀混用")
        print("=" * 76)
        ledger_cids = {"c1", "c2", "c17"}          # 账本导出的局部 cid 形态
        hit = ledger_cids & kind_keys
        say("局部 cid 在人工表里的命中数", len(hit) == 0,
            "命中 %d 条（0 = 我的接线确实零命中）" % len(hit))

        print()
        print("=" * 76)
        print("D2 `_trim` 把 pending 算进容量")
        print("=" * 76)
        m2 = M.FeizhiMemory(tmp / "d2.json")
        b2 = rows(700, 60)
        for i in range(M.MAX_EVENTS):
            m2._ingest("events", [{"text": "有效事件%02d" % i,
                                   "source_msg_ids": [700 + i]}], b2,
                       gate_state="eligible", trim=False)
        before = len(R.recallable(m2._view()))
        # 加一条 pending，然后手动跑一次 trim（模拟下一次新抽取）
        # 合法 pending（来源有效，不会变成隔离项），才会真的占配额
        m2._ingest("events", [{"text": "待复核事件", "source_msg_ids": [701]}], b2,
                   gate_state="pending", trim=False)
        m2._trim("events", M.MAX_EVENTS)
        after = len(R.recallable(m2._view()))
        q = [x for x in m2._view() if x.get("gate_state") == "pending"]
        archived = [x for x in m2._view()
                    if x.get("archived") and x.get("gate_state") != "pending"]
        say("加 pending 后 eligible 被归档", after < before,
            "可召回 %d → %d，pending=%d，归档 eligible=%d"
            % (before, after, len(q), len(archived)))

        print()
        print("=" * 76)
        print("D3 pending 重放增长")
        print("=" * 76)
        m3 = M.FeizhiMemory(tmp / "d3.json")
        b3 = rows(800, 10)
        item = [{"text": "<OWNER>要交材料", "source_msg_ids": [800], "time_raw": ""}]
        m3._ingest("events", item, b3, gate_state="pending", trim=False)
        n1 = len(m3._view())
        m3._ingest("events", item, b3, gate_state="pending", trim=False)
        n2 = len(m3._view())
        say("同一条 pending 重放后条数增长", n2 > n1, "%d → %d" % (n1, n2))

        print()
        print("=" * 76)
        print("D4 反向提升旁路（两种形态 + 反向保护）")
        print("=" * 76)

        # D4a：fact 用**纯正文**做去重键，隔离/提升键必然相同 → 走得到提升分支
        m4 = M.FeizhiMemory(tmp / "d4a.json")
        b4 = rows(900, 10)
        m4._ingest("facts", [{"text": "<OWNER>不吃香菜", "source_msg_ids": [999999]}], b4,
                   gate_state="eligible", trim=False)
        q1 = [x for x in m4._view() if x.get("quarantined")]
        m4._ingest("facts", [{"text": "<OWNER>不吃香菜", "source_msg_ids": [901]}], b4,
                   gate_state="pending", trim=False)
        hit4a = [x for x in R.recallable(m4._view())
                 if x.get("text") == "<OWNER>不吃香菜"]
        gates4a = sorted({x.get("gate_state") for x in m4._view()})
        say("(a) fact：旧 eligible 隔离项被本次 pending 提升后进入召回",
            bool(hit4a), "隔离时 gate=%s，提升后 gate=%s，可召回=%d"
            % (q1[0].get("gate_state") if q1 else "?", gates4a, len(hit4a)))

        # D4b：event 混合来源 [1,999] → 隔离时剔除 999 变 [1]，提升时也是 [1] → 键相同
        m4b = M.FeizhiMemory(tmp / "d4b.json")
        b4b = rows(1, 1) + rows(900, 10)
        m4b._ingest("events", [{"text": "<OWNER>去抽血", "source_msg_ids": [1, 999999]}], b4b,
                    gate_state="eligible", trim=False)
        q2 = [x for x in m4b._view() if x.get("quarantined")]
        m4b._ingest("events", [{"text": "<OWNER>去抽血", "source_msg_ids": [1]}], b4b,
                    gate_state="pending", trim=False)
        hit4b = [x for x in R.recallable(m4b._view()) if x.get("text") == "<OWNER>去抽血"]
        say("(b) event 混合来源：剔除后的键与提升键相同 → 进召回",
            bool(hit4b), "隔离时 gate=%s，可召回=%d"
            % (q2[0].get("gate_state") if q2 else "?", len(hit4b)))

        # D4c 反向保护：旧的 pending/rejected 隔离项，即便本次以 eligible 提升也必须保持阻断
        m4c = M.FeizhiMemory(tmp / "d4c.json")
        m4c._ingest("facts", [{"text": "<OWNER>养了只猫", "source_msg_ids": [999999]}], b4,
                    gate_state="pending", trim=False)
        m4c._ingest("facts", [{"text": "<OWNER>养了只猫", "source_msg_ids": [902]}], b4,
                    gate_state="eligible", trim=False)
        kept = [x for x in m4c._view() if x.get("text") == "<OWNER>养了只猫"]
        hit4c = [x for x in R.recallable(m4c._view()) if x.get("text") == "<OWNER>养了只猫"]
        # 注意 say(repro=...) 的语义是「缺陷是否复现」，所以这里要传"保护失效"的条件
        say("(c) 旧 pending 隔离项被 eligible 提升后仍被阻断",
            bool(hit4c) or not kept or kept[0].get("gate_state") != "pending",
            "提升后 gate=%s，可召回=%d"
            % (kept[0].get("gate_state") if kept else "?", len(hit4c)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("=" * 76)
    print("D5 空值边界：显式 \"\" / None / False / 0 不得当 legacy 放行")
    print("=" * 76)
    cases = [("字段缺失（旧记录兼容）", {}, True),
             ("显式空串", {"gate_state": ""}, False),
             ("显式 None", {"gate_state": None}, False),
             ("显式 False", {"gate_state": False}, False),
             ("显式 0", {"gate_state": 0}, False),
             ("空白串", {"gate_state": "   "}, False),
             ("合法 eligible", {"gate_state": "eligible"}, True),
             ("合法 legacy", {"gate_state": "legacy"}, True),
             ("非法串 unknown", {"gate_state": "unknown"}, False)]
    for label, extra, should_pass in cases:
        rec = {"id": "m0001", "kind": "event", "text": "测试记录",
               "archived": False, "quarantined": False}
        rec.update(extra)
        got = bool(R.recallable([rec]))
        # 缺陷 = 与预期相反
        say("recallable：%s → %s" % (label, "放行" if got else "阻断"),
            got != should_pass,
            "gate_of=%r 期望=%s 实际=%s"
            % (R.gate_of(rec), "放行" if should_pass else "阻断",
               "放行" if got else "阻断"))

    print()
    print("=" * 76)
    print("D6 helper 省略 gate 或传 None 不得继承旧 eligible")
    print("=" * 76)

    def mk(old_gate):
        return {"id": "m0001", "kind": "event", "text": "<OWNER>不吃香菜",
                "source_msg_ids": [], "quarantined": True, "archived": False,
                "gate_state": old_gate, "created": "2026-10-26"}

    bmsgs = rows(1, 3)
    for old_gate, req, want in (
            ("eligible", "<省略>", "pending"),
            ("eligible", None, "pending"),
            ("eligible", "eligible", "eligible"),
            ("eligible", "pending", "pending"),
            ("legacy", "<省略>", "pending"),
            ("pending", "eligible", "pending"),
            ("rejected", "eligible", "rejected"),
            ("bogus", "eligible", "pending")):
        recs = [mk(old_gate)]
        try:
            if req == "<省略>":
                out, got, _notes = R.promote_quarantined(recs, "m0001", [1], bmsgs)
            else:
                out, got, _notes = R.promote_quarantined(recs, "m0001", [1], bmsgs,
                                                         gate_state=req)
            actual = got.get("gate_state")
            say("旧 %-8s + 请求 %-9s → %s（应为 %s）"
                % (old_gate, req, actual, want), actual != want,
                "可召回=%d" % bool(R.recallable(out)))
        except Exception as e:  # noqa: BLE001
            say("旧 %s + 请求 %s 抛错" % (old_gate, req), True, str(e)[:40])

    print()
    print("=" * 76)
    print("复现 %d 项，未复现 %d 项"
          % (RES["reproduced"], RES["clean"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
