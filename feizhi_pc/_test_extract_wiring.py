# -*- coding: utf-8 -*-
"""抽取端接通的离线验收：提示词契约 → 解析器 → 校验入口，三段都要通。

用假的 llm 与假的 store，**不调任何模型**。

覆盖：
  W1 解析器保留 source_msg_ids / time_raw / time_anchor_msg_id
  W2 有效来源 + 相对时间 → 走校验入口算出 2026-10-21，正文里模型自写的日期被改写
  W3 来源无效 → 进隔离区：不入 render、进 review_queue、记录仍保留
  W4 来源缺失（模型没给）→ 同样隔离，不是静默丢弃
  W5 水位推进到批末尾（last_id），记忆编号走独立序列（last_mid）
  W6 重复文本与在库记录比对后跳过
  W7 提示词契约：禁止模型写日期、要求填来源

用法: python _test_extract_wiring.py
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
# 隔离/重复会走 LOG.warning，落到 stderr 会被 PowerShell 误判成命令失败
logging.getLogger("feizhi_pc.memory").setLevel(logging.CRITICAL)
import memrec as R      # noqa: E402
import memory as M      # noqa: E402

OK, NG = "[ OK ]", "[FAIL]"
_RES = {"pass": 0, "fail": 0}
PEER = "wxid_test"


def check(label, cond, detail=""):
    _RES["pass" if cond else "fail"] += 1
    print("   %s %-44s %s" % (OK if cond else NG, label, str(detail)[:56]))
    return cond


def head(t):
    print()
    print("=" * 76)
    print(t)
    print("=" * 76)


def ms(y, mo, d, h=21):
    return int(datetime(y, mo, d, h, tzinfo=R.BEIJING).timestamp() * 1000)


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def recent(self, limit=120):
        return list(self.rows)


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.last_user = ""

    def chat(self, system, user, **kw):
        self.last_user = user
        return self.payload


def rows_from(specs):
    out = []
    for (mid, role, text, sent) in specs:
        out.append({"id": mid, "role": role, "text": text,
                    "sent_at_ms": sent, "peer_wxid": PEER})
    return out


BASE_ROWS = rows_from([
    (501, "user", "我不吃香菜", ms(2026, 10, 18)),
    (502, "user", "明天那个考试我有点慌", ms(2026, 10, 20)),
    (503, "assistant", "那你早点睡", ms(2026, 10, 20)),
    (504, "user", "好", ms(2026, 10, 20)),
    (505, "user", "今天加班到十点", ms(2026, 10, 21)),
    (506, "assistant", "累不累", ms(2026, 10, 21)),
    (507, "user", "还行", ms(2026, 10, 21)),
    (508, "user", "我先睡啦", ms(2026, 10, 21)),
])


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="feizhi_wire_"))
    ok = True
    try:
        head("W7 提示词契约")
        sysmsg = M.EXTRACT_SYSTEM
        ok &= check("明确禁止正文写日期", "不要出现任何日期或相对时间" in sysmsg)
        ok &= check("要求 time_raw", "time_raw" in sysmsg)
        ok &= check("要求 source_msg_ids 且至少一条",
                    "source_msg_ids" in sysmsg and "至少一条" in sysmsg)
        ok &= check("要求 time_anchor_msg_id", "time_anchor_msg_id" in sysmsg)
        ok &= check("说明换算由程序做", "换算是程序的事" in sysmsg)
        ok &= check("不再要求模型自己换算日期",
                    "要**按那条消息自己的发送时间**换算成具体日期" not in sysmsg)

        head("W1-W2 解析器保留新字段，写入走校验入口")
        payload = json.dumps({
            "facts": [{"text": "<OWNER>不吃香菜", "certainty": "high",
                       "source_msg_ids": [501], "time_raw": "",
                       "time_anchor_msg_id": None}],
            "events": [{"text": "<OWNER>2026-10-26要考试", "certainty": "high",
                        "source_msg_ids": [502], "time_raw": "明天",
                        "time_anchor_msg_id": 502}],
        }, ensure_ascii=False)
        m = M.FeizhiMemory(tmp / "w1.json")
        llm = FakeLLM(payload)
        res = m.maybe_extract(FakeStore(BASE_ROWS), PEER, llm)
        print("   ", res)
        ok &= check("抽取没有报错", "error" not in res, res.get("error"))
        view = m._view()
        ev = [x for x in view if x.get("kind") == "event"]
        ok &= check("event 入库一条", len(ev) == 1, len(ev))
        if ev:
            e = ev[0]
            ok &= check("来源被解析保留", e["source_msg_ids"] == [502],
                        e["source_msg_ids"])
            ok &= check("time_raw 被保留", e["time_raw"] == "明天", e["time_raw"])
            ok &= check("锚点被保留", e["time_anchor_msg_id"] == 502,
                        e["time_anchor_msg_id"])
            ok &= check("程序算出 2026-10-21",
                        e["event_time"] == "2026-10-21", e["event_time"])
            ok &= check("basis=message_time", e["time_basis"] == R.TB_MESSAGE,
                        e["time_basis"])
            ok &= check("正文里模型自写的日期被改写",
                        "2026-10-26" not in e["text"] and "10月21日" in e["text"],
                        e["text"])
        fa = [x for x in view if x.get("kind") == "fact"]
        ok &= check("fact 入库一条", len(fa) == 1, len(fa))
        ok &= check("无时间的事实不被加尾巴",
                    fa and "具体日期未确定" not in fa[0]["text"],
                    fa[0]["text"] if fa else "")

        head("W3 来源无效 → 隔离区，不入 render，进 review_queue")
        bad = json.dumps({"facts": [], "events": [
            {"text": "<OWNER>要出国", "certainty": "high",
             "source_msg_ids": [999], "time_raw": "", "time_anchor_msg_id": None}]},
            ensure_ascii=False)
        m3 = M.FeizhiMemory(tmp / "w3.json")
        r3 = m3.maybe_extract(FakeStore(BASE_ROWS), PEER, FakeLLM(bad))
        print("   ", r3)
        v3 = m3._view()
        q = [x for x in v3 if x.get("quarantined")]
        ok &= check("记录被隔离而不是丢弃", len(q) == 1, len(v3))
        ok &= check("隔离项标记待复核", q and q[0]["needs_review"] is True)
        ok &= check("隔离项不进 render", "出国" not in m3.render())
        ok &= check("隔离项进 review_queue",
                    any("出国" in x["text"] for x in m3.review_queue()))
        ok &= check("隔离项来源被清空", q and q[0]["source_msg_ids"] == [],
                    q[0]["source_msg_ids"] if q else "")
        ok &= check("隔离项不算「新增生效」",
                    r3.get("events_added") == 0 and r3.get("quarantined_added") == 1,
                    "added=%s q=%s" % (r3.get("events_added"),
                                       r3.get("quarantined_added")))

        head("W4 来源缺失 → 同样隔离")
        nose = json.dumps({"facts": [{"text": "<OWNER>在写小说", "certainty": "mid",
                                      "time_raw": ""}], "events": []},
                          ensure_ascii=False)
        m4 = M.FeizhiMemory(tmp / "w4.json")
        r4 = m4.maybe_extract(FakeStore(BASE_ROWS), PEER, FakeLLM(nose))
        print("   ", r4)
        v4 = m4._view()
        ok &= check("无来源记录被隔离",
                    len(v4) == 1 and v4[0].get("quarantined") is True, len(v4))
        ok &= check("无来源记录不进 render", "写小说" not in m4.render())
        ok &= check("无来源记录仍在文件里（可复查）",
                    "写小说" in (m4.render_existing() + json.dumps(v4, ensure_ascii=False)))
        ok &= check("无来源不算「新增生效」",
                    r4.get("facts_added") == 0 and r4.get("quarantined_added") == 1,
                    "added=%s q=%s" % (r4.get("facts_added"),
                                       r4.get("quarantined_added")))

        head("W5 水位与编号各走各的")
        ok &= check("last_id 推进到批末尾 508", m.data["last_id"] == 508,
                    m.data["last_id"])
        ok &= check("last_mid 独立为 2", m.data["last_mid"] == 2,
                    m.data["last_mid"])
        ok &= check("两者不相等（证明没共用）",
                    m.data["last_id"] != m.data["last_mid"])

        head("W6 重复文本跳过（必须用**新消息**再触发一次，否则被水位挡掉）")
        m6 = M.FeizhiMemory(tmp / "w6.json")
        dup = json.dumps({"facts": [{"text": "<OWNER>不吃香菜", "certainty": "high",
                                     "source_msg_ids": [501], "time_raw": ""}],
                          "events": []}, ensure_ascii=False)
        m6.maybe_extract(FakeStore(BASE_ROWS), PEER, FakeLLM(dup))
        ok &= check("第一次入库一条", len(m6._view()) == 1, len(m6._view()))
        m6.data["last_extract_ts"] = 0
        rows2 = BASE_ROWS + rows_from([(509 + i, "user", "后面又聊了点%d" % i,
                                        ms(2026, 10, 22)) for i in range(8)])
        r6 = m6.maybe_extract(FakeStore(rows2), PEER, FakeLLM(dup))
        print("   ", r6)
        ok &= check("没有因为 not_enough_new 被跳过",
                    "skipped" not in r6, r6.get("skipped"))
        ok &= check("第二次同文本未重复入库",
                    r6.get("facts_added") == 0 and len(m6._view()) == 1,
                    "条数=%d" % len(m6._view()))

        head("W9 先隔离、后有效来源 → 提升同一条，不新建重复")
        m9 = M.FeizhiMemory(tmp / "w9.json")
        bad9 = json.dumps({"facts": [{"text": "<OWNER>在写小说", "certainty": "mid",
                                      "source_msg_ids": [999], "time_raw": ""}],
                           "events": []}, ensure_ascii=False)
        m9.maybe_extract(FakeStore(BASE_ROWS), PEER, FakeLLM(bad9))
        v9a = m9._view()
        ok &= check("第一次被隔离而不是丢弃",
                    len(v9a) == 1 and v9a[0].get("quarantined") is True, len(v9a))
        ok &= check("此时不可召回", "写小说" not in m9.render())
        m9.data["last_extract_ts"] = 0
        rows9 = BASE_ROWS + rows_from([(509 + i, "user", "后来%d" % i,
                                        ms(2026, 10, 22)) for i in range(8)])
        good9 = json.dumps({"facts": [{"text": "<OWNER>在写小说", "certainty": "mid",
                                       "source_msg_ids": [509], "time_raw": ""}],
                            "events": []}, ensure_ascii=False)
        r9 = m9.maybe_extract(FakeStore(rows9), PEER, FakeLLM(good9))
        print("   ", r9)
        v9 = m9._view()
        ok &= check("报告里记了提升", r9.get("promoted") == 1, r9.get("promoted"))
        ok &= check("没有产生重复记录", len(v9) == 1, len(v9))
        ok &= check("已移出隔离区", v9 and v9[0].get("quarantined") is False)
        ok &= check("来源已补上", v9 and v9[0]["source_msg_ids"] == [509],
                    v9[0]["source_msg_ids"] if v9 else "")
        # ★ 2026-10-28 闸门接线后行为变了：补来源只把它移出隔离区，
        #   **不等于语义批准**（memrec.promote_quarantined 的矩阵明写
        #   「旧 pending / rejected → 保持阻断」）。以前这条能过，是因为
        #   抽取链路把 gate 硬编码成 legacy，绕过了矩阵 —— 那正是要修的缺陷。
        #   现在提升后仍 pending，需要闸门放行才召回。
        ok &= check("提升后仍是 pending（补来源≠批准）",
                    v9 and v9[0].get("gate_state") == "pending",
                    v9[0].get("gate_state") if v9 else "")
        ok &= check("此时还不可召回", "写小说" not in m9.render())
        ok &= check("带复核标记（缺时间依据）", bool(v9 and v9[0].get("needs_review")))
        with m9._mutation() as w9:
            recs9, _, _ = R.approve_pending(w9._view(), by="human")
            if recs9 is not None:
                w9._replace_all(recs9)
        ok &= check("人工放行后进入召回", "写小说" in m9.render())

        head("W10 隔离项不得挡住后续有效写入（去重只看可召回）")
        m10 = M.FeizhiMemory(tmp / "w10.json")
        badA = json.dumps({"facts": [], "events": [
            {"text": "<OWNER>要换工作", "certainty": "high",
             "source_msg_ids": [999], "time_raw": ""}]}, ensure_ascii=False)
        m10.maybe_extract(FakeStore(BASE_ROWS), PEER, FakeLLM(badA))
        ok &= check("先隔离一条", len(m10._view()) == 1
                    and m10._view()[0].get("quarantined") is True)
        m10.data["last_extract_ts"] = 0
        rowsA = BASE_ROWS + rows_from([(520 + i, "user", "又聊了%d" % i,
                                        ms(2026, 10, 23)) for i in range(8)])
        goodA = json.dumps({"facts": [], "events": [
            {"text": "<OWNER>要换工作", "certainty": "high",
             "source_msg_ids": [520], "time_raw": ""}]}, ensure_ascii=False)
        rA = m10.maybe_extract(FakeStore(rowsA), PEER, FakeLLM(goodA))
        print("   ", rA)
        ok &= check("第二次没被判「重复跳过」",
                    "重复跳过" not in " ".join(rA.get("ingest_fails") or []),
                    rA.get("ingest_fails"))
        ok &= check("现在有可召回记录",
                    any(x["text"] == "<OWNER>要换工作"
                        for x in R.recallable(m10._view())))

        head("W11 输出被截断 → 标 partial，水位不推进，下一轮重抽")
        m11 = M.FeizhiMemory(tmp / "w11.json")
        truncated = ('{"facts": [{"text": "<OWNER>不吃香菜", "certainty": "high", '
                     '"source_msg_ids": [501], "time_raw": "", '
                     '"time_anchor_msg_id": null}, {"text": "半截条目", "certainty": "hi')
        r11 = m11.maybe_extract(FakeStore(BASE_ROWS), PEER, FakeLLM(truncated))
        print("   ", r11)
        ok &= check("标记为 partial", r11.get("partial") is True, r11.get("partial"))
        ok &= check("水位**没有**推进", m11.data.get("last_id", 0) == 0,
                    m11.data.get("last_id"))
        ok &= check("救回的完整条目仍然入库", len(m11._view()) == 1,
                    len(m11._view()))
        m11.data["last_extract_ts"] = 0
        full11 = json.dumps({"facts": [
            {"text": "<OWNER>不吃香菜", "certainty": "high",
             "source_msg_ids": [501], "time_raw": ""},
            {"text": "<OWNER>在写小说", "certainty": "mid",
             "source_msg_ids": [502], "time_raw": ""}], "events": []},
            ensure_ascii=False)
        r11b = m11.maybe_extract(FakeStore(BASE_ROWS), PEER, FakeLLM(full11))
        print("   ", r11b)
        ok &= check("同一批能被重抽（没被水位挡掉）", "skipped" not in r11b,
                    r11b.get("skipped"))
        ok &= check("重抽补齐了被截断丢掉的那条", len(m11._view()) == 2,
                    len(m11._view()))
        ok &= check("重抽没写重复记录",
                    len([x for x in m11._view()
                         if x["text"] == "<OWNER>不吃香菜"]) == 1)

        head("W12 歧义时间的锚点必须是**原话发送时间**，不是入库日")
        m12 = M.FeizhiMemory(tmp / "w12.json")
        m12.add_record({"kind": "event", "text": "<OWNER>要交大赛作品",
                        "time_raw": "本周末20点前", "source_msg_ids": [501],
                        "time_anchor_msg_id": 501},
                       [{"id": 501, "role": "user", "text": "本周末20点前交",
                         "sent_at_ms": ms(2026, 10, 15)}])
        t12 = m12.render()
        print("   ", [ln for ln in t12.splitlines() if ln.startswith("- ")])
        ok &= check("渲染保留原话时间", "本周末20点前" in t12)
        ok &= check("锚点是来源消息的 2026-10-15", "2026-10-15" in t12)
        ok &= check("没有拿入库日冒充",
                    "这条记于" not in t12, "旧实现会写「这条记于 <入库日>」")
        ok &= check("正文已说明日期未定，不重复", t12.count("日期未") == 1,
                    t12.count("日期未"))

        head("W13 已核验日期必须出现在召回文本里")
        m13 = M.FeizhiMemory(tmp / "w13.json")
        m13.add_record({"kind": "event", "text": "<OWNER>要上课", "time_raw": "明天",
                        "time_anchor_msg_id": 501, "source_msg_ids": [501]},
                       [{"id": 501, "role": "user", "text": "明天上课",
                         "sent_at_ms": ms(2026, 10, 15)}])
        line13 = [ln for ln in m13.render().splitlines() if ln.startswith("- ")][0]
        print("   ", line13)
        ok &= check("渲染出已核验的 10月16日", "10月16日" in line13, line13)

        head("W14 重放幂等：同一模型输出两次不得重复入库（去重在校验之后）")
        m14 = M.FeizhiMemory(tmp / "w14.json")
        same = json.dumps({"facts": [{"text": "<OWNER>明天交材料", "certainty": "high",
                                      "source_msg_ids": [501], "time_raw": "明天",
                                      "time_anchor_msg_id": 501}], "events": []},
                          ensure_ascii=False)
        rows14 = [{"id": 501 + i,
                   "role": "user" if i % 2 == 0 else "assistant",
                   "text": ("明天交材料" if i == 0 else "随便聊点%d" % i),
                   "sent_at_ms": ms(2026, 10, 15), "peer_wxid": PEER}
                  for i in range(8)]
        m14.maybe_extract(FakeStore(rows14), PEER, FakeLLM(same))
        n1 = len(m14._view())
        first = m14._view()[0]["text"] if n1 else ""
        # 模拟截断后重抽：水位没推进，同一批再来一次
        m14.data["last_extract_ts"] = 0
        m14.data["last_id"] = 0
        m14.maybe_extract(FakeStore(rows14), PEER, FakeLLM(same))
        n2 = len(m14._view())
        print("   首次=%d 条（%s）；重放后=%d 条" % (n1, first, n2))
        ok &= check("首次入库 1 条", n1 == 1, n1)
        ok &= check("规范化正文写进了 10月16日", "10月16日" in first, first)
        ok &= check("重放后仍是 1 条", n2 == 1, n2)

        head("W15 同一正文、不同日期的事件必须都入库（去重纳入结构化日期）")
        m15 = M.FeizhiMemory(tmp / "w15.json")
        pay15 = json.dumps({"facts": [], "events": [
            {"text": "<OWNER>去医院抽血", "certainty": "high",
             "source_msg_ids": [601], "time_raw": "",
             "time_anchor_msg_id": None}]}, ensure_ascii=False)
        rows15a = [{"id": 601 + i, "role": "user",
                    "text": ("2026年10月16日去医院抽血" if i == 0 else "随便聊%d" % i),
                    "sent_at_ms": ms(2026, 10, 15), "peer_wxid": PEER}
                   for i in range(8)]
        m15.maybe_extract(FakeStore(rows15a), PEER, FakeLLM(pay15))
        pay15b = json.dumps({"facts": [], "events": [
            {"text": "<OWNER>去医院抽血", "certainty": "high",
             "source_msg_ids": [701], "time_raw": "",
             "time_anchor_msg_id": None}]}, ensure_ascii=False)
        rows15b = [{"id": 701 + i, "role": "user",
                    "text": ("2026年11月16日又去医院抽血" if i == 0 else "随便聊%d" % i),
                    "sent_at_ms": ms(2026, 11, 15), "peer_wxid": PEER}
                   for i in range(8)]
        m15.data["last_extract_ts"] = 0
        m15.maybe_extract(FakeStore(rows15b), PEER, FakeLLM(pay15b))
        ev15 = [x for x in m15._view() if x.get("kind") == "event"]
        print("   ", [(x["text"], x["event_time"]) for x in ev15])
        ok &= check("两次发生都入库", len(ev15) == 2, len(ev15))
        ok &= check("日期确实是两个",
                    {x["event_time"] for x in ev15}
                    == {"2026-10-16", "2026-11-16"},
                    [x["event_time"] for x in ev15])
        ok &= check("正文相同（证明靠日期区分）",
                    len({x["text"] for x in ev15}) == 1)

        head("W16 锚点必须是有效来源、且原文含该时间表达")
        rows16 = [{"id": 801, "role": "user", "text": "本周末20点前交作品",
                   "sent_at_ms": ms(2026, 10, 15), "peer_wxid": PEER},
                  {"id": 802, "role": "user", "text": "今天好热啊",
                   "sent_at_ms": ms(2026, 11, 15), "peer_wxid": PEER}]
        base16 = dict(kind="event", text="<OWNER>要交作品", time_raw="本周末20点前")
        o16a, _ = R.validate(R.new_record(90, time_anchor_msg_id=802,
                                          source_msg_ids=[801], **base16), rows16)
        ok &= check("(a) 锚点不属于引用来源 → 置空", o16a["time_raw_at_ms"] is None,
                    o16a["time_raw_at_ms"])
        o16b, _ = R.validate(R.new_record(91, time_anchor_msg_id=802,
                                          source_msg_ids=[801, 802], **base16), rows16)
        ok &= check("(b) 锚点原文不含该表达 → 置空", o16b["time_raw_at_ms"] is None,
                    o16b["time_raw_at_ms"])
        o16c, _ = R.validate(R.new_record(92, time_anchor_msg_id=801,
                                          source_msg_ids=[801], **base16), rows16)
        ok &= check("(c) 条件齐备 → 取锚点发送时间",
                    o16c["time_raw_at_ms"] == ms(2026, 10, 15),
                    o16c["time_raw_at_ms"])

        head("W17 相对词不得子串匹配：time_raw=后天 vs 原文「大后天考试」")
        rows17 = [
            {"id": 901, "role": "user", "text": "大后天考试了", "sent_at_ms": ms(2026, 10, 15),
             "peer_wxid": PEER},
            {"id": 902, "role": "user", "text": "今天下午画了一整个下午的作业",
             "sent_at_ms": ms(2026, 10, 15), "peer_wxid": PEER},
        ]
        o17a, n17a = R.validate(R.new_record(95, kind="event", text="<OWNER>要考试",
                                             time_raw="后天",
                                             time_anchor_msg_id=901,
                                             source_msg_ids=[901]), rows17)
        ok &= check("(a) 日期正确拒绝", o17a["event_time"] is None, o17a["event_time"])
        ok &= check("(a) 原话时间也置空（不能把「后天」当原话）",
                    o17a["time_raw_at_ms"] is None, o17a["time_raw_at_ms"])
        o17b, _ = R.validate(R.new_record(96, kind="event", text="绯栀画作业",
                                          time_raw="今天下午",
                                          time_anchor_msg_id=902,
                                          source_msg_ids=[902]), rows17)
        ok &= check("(b) 「今天下午」按完整词比对通过",
                    o17b["time_raw_at_ms"] == ms(2026, 10, 15),
                    o17b["time_raw_at_ms"])
        ok &= check("(b) 日期也算出来了", o17b["event_time"] == "2026-10-15",
                    o17b["event_time"])

        head("W7b 提示词确实要求不写日期（检查发给模型的 user 里带消息 ID）")
        ok &= check("user prompt 带 #消息ID", "#501" in llm.last_user)

        head("W8 _add 仍是裸写入（只给 add_fact/add_event 这类内部工具）")
        m8 = M.FeizhiMemory(tmp / "w8.json")
        m8.add_fact("测试用的无来源事实")
        v8 = m8._view()
        ok &= check("add_fact 仍可无来源写入", len(v8) == 1, len(v8))
        ok &= check("add_fact 的记录没有隔离标记",
                    v8 and not v8[0].get("quarantined"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    head("结论：%d 通过 / %d 失败" % (_RES["pass"], _RES["fail"]))
    return 0 if ok and _RES["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
