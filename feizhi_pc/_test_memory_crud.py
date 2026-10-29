# -*- coding: utf-8 -*-
"""持久层 CRUD 与迁移的离线验收。**全程不调模型、不碰生产文件。**

覆盖：
  M1 旧格式（无 id）→ migrate 分配 id，幂等，不补造来源
  M2 _add 产出 id/kind/created/archived
  M3 add_record 走完整时间校验（正文瞎写的日期被清）
  M4 update_record 改文案会重校验，且不清空溯源码
  M5 update_record 改时间：无 reason 拒绝；有 reason 转 manual
  M6 archive：render 不再包含、stats 计数变化、落盘可重载、不物理删
  M7 restore 撤销归档
  M8 超出上限时归档最旧的，不物理删除
  M9 落盘后重新加载，结构与归档状态都还在

用法: python _test_memory_crud.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(r"<PROJECT_ROOT>\feizhi_pc")))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
import memrec as R          # noqa: E402
import memory as M          # noqa: E402

OK, NG = "[ OK ]", "[FAIL]"
_RES = {"pass": 0, "fail": 0}


def check(label, cond, detail=""):
    _RES["pass" if cond else "fail"] += 1
    print("   %s %-52s %s" % (OK if cond else NG, label, detail))
    return cond


def ms(y, mo, d, h=21):
    return int(datetime(y, mo, d, h, tzinfo=R.BEIJING).timestamp() * 1000)


def head(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="feizhi_mem_"))
    path = tmp / "feizhi_memory.json"
    ok = True
    try:
        head("M1 旧格式（无 id）→ migrate 分配 id，幂等，不补造来源")
        legacy = {"facts": [{"text": "<OWNER>不吃香菜", "certainty": "high",
                             "added": "2026-10-16"},
                            {"text": "<OWNER>在写代码", "added": "2026-10-17"}],
                  "events": [{"text": "<OWNER>10月20日考试", "certainty": "mid",
                              "added": "2026-10-20"}],
                  "last_id": 0}
        path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        m = M.FeizhiMemory(path)
        r1 = m.migrate()
        ids = [x["id"] for x in m._view()]
        ok &= check("三条都拿到 id", ids == ["m0001", "m0002", "m0003"], str(ids))
        # ★ 旧版本这里断言的是「last_id 推进到 3」—— 那是错的：
        #   last_id 是**消息抽取水位**，记忆编号必须用自己的序列 last_mid。
        ok &= check("last_id（消息水位）**不变**", m.data["last_id"] == 0,
                    str(m.data["last_id"]))
        ok &= check("last_mid（记忆编号）推进到 3", m.data["last_mid"] == 3,
                    str(m.data["last_mid"]))
        ok &= check("不补造来源", all(x["source_msg_ids"] == [] for x in m._view()))
        ok &= check("added 不被当成事件时间",
                    all(x["event_time"] is None for x in m._view()))
        ok &= check("kind 分清 fact/event",
                    [x["kind"] for x in m._view()] == ["fact", "fact", "event"])
        r2 = m.migrate()
        ok &= check("幂等：第二次不再分配 id", r2["touched"] == 0, str(r2))

        head("M1b 迁移不得吞掉未抽取的消息（水位与编号必须独立）")
        m1b = M.FeizhiMemory(tmp / "watermark.json")
        m1b.data["last_id"] = 510
        m1b.data["facts"] = [{"text": "旧事实%d号内容" % i, "added": "2026-10-16"}
                             for i in range(96)]
        m1b.save()
        m1b.migrate()
        ok &= check("迁移后消息水位仍是 510", m1b.data["last_id"] == 510,
                    str(m1b.data["last_id"]))
        ok &= check("记忆编号走独立序列", m1b.data["last_mid"] == 96,
                    str(m1b.data["last_mid"]))
        pending = [i for i in range(511, 520)
                   if i > int(m1b.data.get("last_id", 0))]
        ok &= check("消息 511-519 仍算未抽取", pending == list(range(511, 520)),
                    str(pending))
        m1b.add_fact("再记一条")
        ok &= check("add_fact 不推进消息水位", m1b.data["last_id"] == 510,
                    str(m1b.data["last_id"]))
        ok &= check("add_fact 推进记忆编号", m1b.data["last_mid"] == 97,
                    str(m1b.data["last_mid"]))

        head("M2 _add 产出 id/kind/created/archived")
        m._add("facts", [{"text": "<OWNER>养了只猫叫糊糊", "certainty": "high"}], M.MAX_FACTS)
        m.save()
        new = [x for x in m.facts() if "糊糊" in x.get("text", "")][0]
        ok &= check("有新 id", new["id"] == "m0004", new["id"])
        ok &= check("kind=fact", new["kind"] == "fact")
        ok &= check("created 有值", bool(new["created"]), new["created"])
        ok &= check("archived=False", new["archived"] is False)

        head("M3 add_record 走完整时间校验")
        out = m.add_record(
            {"kind": "event", "text": "<OWNER>2026-10-26要交材料", "certainty": "high",
             "source_msg_ids": [900]},
            [{"id": 900, "role": "user", "text": "我要交材料", "sent_at_ms": ms(2026, 10, 20)}])
        rec = out["record"]
        ok &= check("正文里的日期被清", "10-26" not in rec["text"]
                    and "2026" not in rec["text"], rec["text"])
        ok &= check("来源被保留", rec["source_msg_ids"] == [900], str(rec["source_msg_ids"]))
        ok &= check("id 连续", rec["id"] == "m0005", rec["id"])

        head("M4 update_record 改文案会重校验，且不清空溯源码")
        up = m.update_record("m0005", {"text": "<OWNER>10月27日要交材料"})
        ok &= check("改完仍被清掉日期", "10月27" not in up["record"]["text"],
                    up["record"]["text"])
        ok &= check("溯源码没被清空", up["record"]["source_msg_ids"] == [900],
                    str(up["record"]["source_msg_ids"]))

        head("M5 update_record 改时间：无 reason 拒绝；有 reason 转 manual")
        try:
            m.update_record("m0005", {"event_time": "2026-11-05"})
            ok &= check("无 reason 应被拒", False)
        except R.RecordError as e:
            ok &= check("无 reason 被拒", True, str(e)[:40])
        up2 = m.update_record("m0005", {"event_time": "2026-11-05"},
                              reason="<OWNER>本人确认")
        ok &= check("event_time 落地", up2["record"]["event_time"] == "2026-11-05")
        ok &= check("basis=manual", up2["record"]["time_basis"] == R.TB_MANUAL)
        ok &= check("永久待复核", up2["record"]["needs_review"] is True)

        head("M6 archive：render 不再包含、计数变化、落盘可重载、不物理删")
        before_n = len(m._view())
        rendered_before = m.render()
        arc = m.archive_record("m0005", "他说记错了")
        ok &= check("archived=True", arc["archived"] is True)
        ok &= check("原因已记", arc["archive_reason"] == "他说记错了")
        ok &= check("记录仍在（不物理删）", len(m._view()) == before_n,
                    "%d→%d" % (before_n, len(m._view())))
        ok &= check("render 里不再出现", "要交材料" not in m.render(),
                    "before 含=%s" % ("要交材料" in rendered_before))
        st = m.stats()
        ok &= check("stats 记了 archived", st["archived"] == 1, str(st))
        m2 = M.FeizhiMemory(path)
        kept = [x for x in m2._view() if x["id"] == "m0005"]
        ok &= check("重载后归档状态还在", kept and kept[0]["archived"] is True)
        ok &= check("重载后 ID 还在",
                    [x["id"] for x in m2._view()] == [x["id"] for x in m._view()])

        head("M7 restore 撤销归档")
        back = m2.restore_record("m0005")
        ok &= check("archived 复原", back["archived"] is False)
        ok &= check("原因清空", back["archive_reason"] == "")
        ok &= check("render 里又出现", "要交材料" in m2.render())

        head("M8 超出上限时归档最旧的，不物理删除")
        m3 = M.FeizhiMemory(tmp / "trim.json")
        for i in range(M.MAX_FACTS + 5):
            m3._add("facts", ["事实编号%03d号内容" % i], M.MAX_FACTS)
        m3.save()
        live = [x for x in m3.facts() if not x.get("archived")]
        alln = len(m3.facts())
        ok &= check("未归档数不超上限", len(live) <= M.MAX_FACTS, str(len(live)))
        ok &= check("总数未减少（没物理删）", alln == M.MAX_FACTS + 5, str(alln))
        ok &= check("自动归档有原因",
                    all(x["archive_reason"] for x in m3.facts() if x.get("archived")))

        head("M9 结构完整性抽查")
        need = ("id", "kind", "text", "created", "source_msg_ids", "speaker",
                "event_time", "time_basis", "time_raw", "time_anchor_msg_id",
                "needs_review", "archived", "archived_at", "archive_reason")
        missing = [(x.get("id"), k) for x in m2._view() for k in need if k not in x]
        ok &= check("所有记录字段齐全", not missing, str(missing[:3]))
        ok &= check("id 全局唯一",
                    len({x["id"] for x in m2._view()}) == len(m2._view()))
        head("M10 未迁移数据（无 id 无 kind）不得错分桶")
        m10 = M.FeizhiMemory(tmp / "legacy_bucket.json")
        m10.data["facts"] = [{"text": "旧事实%02d号内容" % i, "added": "2026-10-16"}
                             for i in range(56)]
        m10.data["events"] = [{"text": "旧事件%02d号内容" % i, "added": "2026-10-16"}
                              for i in range(40)]
        m10.data["last_id"] = 510
        m10.save()
        view10 = m10._view()
        ok &= check("视图里 kind 全部补齐", all(x.get("kind") for x in view10))
        ok &= check("fact/event 数量正确",
                    sum(1 for x in view10 if x["kind"] == "fact") == 56
                    and sum(1 for x in view10 if x["kind"] == "event") == 40,
                    "%d/%d" % (sum(1 for x in view10 if x["kind"] == "fact"),
                               sum(1 for x in view10 if x["kind"] == "event")))
        r10 = m10.render()
        ok &= check("render 同时含事实与事件",
                    "旧事实55" in r10 and "旧事件39" in r10, "len=%d" % len(r10))
        m10.add_record({"kind": "fact", "text": "<OWNER>不吃香菜",
                        "source_msg_ids": [1]},
                       [{"id": 1, "role": "user", "text": "我不吃香菜",
                         "sent_at_ms": ms(2026, 10, 20)}])
        ok &= check("events 桶仍是 40 条", len(m10.data["events"]) == 40,
                    len(m10.data["events"]))
        ok &= check("facts 桶 57 条", len(m10.data["facts"]) == 57,
                    len(m10.data["facts"]))
        ok &= check("没有连带自动归档",
                    sum(1 for x in m10.data["facts"] + m10.data["events"]
                        if x.get("archived")) == 0)

        head("M11 隔离项不得挤占有效记忆配额")
        m11 = M.FeizhiMemory(tmp / "quarantine_trim.json")
        b11 = [{"id": 700 + i, "role": "user", "text": "某事%d" % i,
                "sent_at_ms": ms(2026, 10, 20)} for i in range(60)]
        for i in range(M.MAX_EVENTS):
            m11._ingest("events", [{"text": "有效事件%02d" % i, "source_msg_ids": [700 + i]}], b11, gate_state="legacy")
        before11 = len(R.recallable(m11._view()))
        m11._ingest("events", [{"text": "隔离事件内容", "source_msg_ids": [999]}], b11, gate_state="legacy")
        after11 = len(R.recallable(m11._view()))
        ok &= check("可召回事件数不变",
                    before11 == after11 == M.MAX_EVENTS,
                    "%d → %d" % (before11, after11))
        ok &= check("隔离项确实已隔离",
                    any(x.get("quarantined") for x in m11._view()))
        ok &= check("没有有效事件被连带归档",
                    sum(1 for x in m11._view()
                        if x.get("archived") and not x.get("quarantined")) == 0)

        head("M12 隔离区有自己的上限")
        m12 = M.FeizhiMemory(tmp / "quarantine_cap.json")
        b12 = [{"id": 900, "role": "user", "text": "x",
                "sent_at_ms": ms(2026, 10, 20)}]
        for i in range(8):
            m12._ingest("facts", [{"text": "隔离事实%02d" % i, "source_msg_ids": [999]}], b12, gate_state="legacy")
        n_before12 = len([x for x in m12._view() if x.get("quarantined")])
        m12._trim_quarantine("facts", 5)
        live_q = [x for x in m12._view()
                  if x.get("quarantined") and not x.get("archived")]
        ok &= check("隔离数被压到 5", len(live_q) == 5,
                    "%d → %d" % (n_before12, len(live_q)))
        ok &= check("归档原因写明", any(
            x.get("archive_reason") == "隔离区超上限，归档" for x in m12._view()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    head("结论：%d 通过 / %d 失败" % (_RES["pass"], _RES["fail"]))
    return 0 if ok and _RES["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
