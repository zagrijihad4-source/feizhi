# -*- coding: utf-8 -*-
"""记录结构、时间契约与 CRUD 的离线验收（memrec v3.1）。**全程不调模型。**

用例分四组：

  A. YG 复现的五个反例（这一组是硬要求）
     A1 有效锚点 + 正文写「明天」 → 正文必须落成具体日期
     A2 无时间依据 + 正文写 2026-10-26 → 该日期必须被移除
     A3 来源写「大后天」而 time_raw 声称「后天」 → 必须拒绝（子串匹配会错两天）
     A4 来源写「13月40日」 → 必须拒绝（不是合法日历日）
     A5 只引用 user 消息、批次里还有 assistant → speaker 必须是<OWNER>

  B. v3 原有的四个反例（回归，不能修 A 组时把它们改坏）
     B1 正文自写日期、来源里没有 → 正文不能给自己作证
     B2 正文日期与来源不一致 → 以来源为准
     B3 unknown 却填了 event_time → 无条件置空
     B4 来源时间 "abc" → 不是有效锚点

  C. 归一化本身的边界
     C1 相等日期不得被「改写」（旧版 iso("10-22")=None 导致恒真不等 + 空日期假 note）
     C2 无年份写法 10-26 也要清（旧版只认 4 位年，漏删）
     C3 数值不当日期：体重10.26斤 必须原样保留
     C4 跨年：12月31日说「明天」→ 次年 1月1日
     C5 「1月2日」在 12月的消息里 → 补成下一年
     C6 来源无可用时间时，年份留空并标记复核
     C7 人工修正的时间不被复算推翻
     C8 人工修正的非法日期被置空
     C9 无来源可核验时 speaker 保留并标复核；引用混合角色时置空

  D. CRUD（add / patch / archive / restore）
     D1 add 自动分配 id 并推进 last_mid
     D2 add 撞 id 报错
     D3 patch 正文会重跑 validate（防止绕过时间校验改正文）
     D4 patch 时间必须给 reason
     D5 patch 时间转 manual 且永久 needs_review
     D6 patch 锁字段一律拒绝（id / source_msg_ids / archived…）
     D7 patch 未知字段拒绝
     D8 archive 是逻辑删除，不物理删，且幂等
     D9 restore 可撤销
     D10 review_queue 只收未归档且 needs_review 的

  F. YG 第二轮复现的五条（更新语义与 manual 入口）
     F1 普通 patch（只改 certainty）不得推翻已核验时间
     F2 改 time_raw = 按来源重算，basis 是 message_time 而非 manual
     F3 改 time_raw 但缺来源消息体 → 拒绝，不许半套来源硬算
     F4 add_record 不得接受自报 manual
     F5 add_manual_record 是唯一合法 manual 入口，必须给 reason

  Y. 年份处理（旧实现制造确定性错误）
     Y1 「10月25日说 10月20日交了材料」→ 年份不能猜成明年
     Y2 正文 2025-10-21 / 字段 2026-10-21 → 冲突必须被发现
     Y3 年份未知时返回 10-26 → needs_review 必须为 True

用法: python _test_memrec.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(r"<PROJECT_ROOT>\feizhi_pc")))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
import memrec as R  # noqa: E402

OK = "[ OK ]"
NG = "[FAIL]"


def ms(y, mo, d, h=21, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=R.BEIJING).timestamp() * 1000)


def msg(mid, role, text, sent):
    return {"id": mid, "role": role, "text": text, "sent_at_ms": sent}


_RESULT = {"pass": 0, "fail": 0}


def case(label, rec, src, expect, notes_has=None, notes_not=None):
    out, notes = R.validate(rec, src)
    blob = "; ".join(notes)
    ok = True
    for k, v in expect.items():
        got = out.get(k)
        good = bool(v(got)) if callable(v) else (got == v)
        ok &= good
        print("   %-14s %-30s %s" % (k, repr(got)[:30], OK if good else NG + " 期望不符"))
    for frag in (notes_has or []):
        good = frag in blob
        ok &= good
        print("   %-14s %-30s %s" % ("notes 必须含", frag[:30], OK if good else NG))
    for frag in (notes_not or []):
        good = frag not in blob
        ok &= good
        print("   %-14s %-30s %s" % ("notes 必须不含", frag[:30], OK if good else NG))
    print("   text:", out.get("text", "")[:60])
    if notes:
        print("   说明:", blob[:160])
    _RESULT["pass" if ok else "fail"] += 1
    print("   =>", OK if ok else NG, label)
    return ok


def head(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


BASE = dict(kind="event", certainty="high", created="2026-10-25")

SRC_REL = [msg(520, "user", "后天那个考试我有点慌", 0)]          # 没有可用时间
SRC_ABS = [msg(522, "user", "10月26日那个考试我有点慌", 0)]
ANCHOR_20 = msg(601, "user", "明天那个考试我有点慌", ms(2026, 10, 20))
ANCHOR_NY = msg(607, "user", "明天要交材料", ms(2026, 12, 31, 22))
ANCHOR_DEC = msg(608, "user", "1月2日交材料", ms(2026, 12, 31, 22))


def main() -> int:
    head("A1 有效锚点 + 正文写「明天」→ 必须落成具体日期")
    case("A1", R.new_record(1, text="<OWNER>明天要考试", time_raw="明天",
                            time_anchor_msg_id=601, source_msg_ids=[601], **BASE),
         [ANCHOR_20],
         {"event_time": "2026-10-21", "time_basis": R.TB_MESSAGE,
          "text": lambda t: "10月21日" in t and "明天" not in t},
         notes_has=["10月21日"])

    head("A2 无时间依据 + 正文写 2026-10-26 → 必须移除")
    case("A2", R.new_record(2, text="<OWNER>2026-10-26要早起交材料",
                            source_msg_ids=[603], **BASE),
         [msg(603, "user", "我要早起交材料", ms(2026, 10, 20))],
         {"event_time": None, "time_basis": R.TB_UNKNOWN, "needs_review": True,
          "text": lambda t: ("10-26" not in t and "10月26" not in t
                             and "2026" not in t
                             and "具体日期未确定" not in t)})

    head("A3 来源「大后天」而 time_raw 声称「后天」→ 必须拒绝")
    case("A3", R.new_record(3, text="<OWNER>后天要考试", time_raw="后天",
                            time_anchor_msg_id=602, source_msg_ids=[602], **BASE),
         [msg(602, "user", "大后天那个考试", ms(2026, 10, 20))],
         {"event_time": None, "time_basis": R.TB_UNKNOWN,
          "text": lambda t: "后天" not in t},
         notes_has=["大后天"])

    head("A4 来源「13月40日」→ 必须拒绝")
    case("A4", R.new_record(4, text="<OWNER>要考试", time_raw="13月40日",
                            time_anchor_msg_id=604, source_msg_ids=[604], **BASE),
         [msg(604, "user", "13月40日那个考试", ms(2026, 10, 20))],
         {"event_time": None, "time_basis": R.TB_UNKNOWN})

    head("A5 只引用 user 消息、批次里还有 assistant → speaker 必须是<OWNER>")
    case("A5", R.new_record(5, text="<OWNER>要早起", speaker="绯栀",
                            source_msg_ids=[605], **BASE),
         [msg(605, "user", "我要早起", ms(2026, 10, 20)),
          msg(606, "assistant", "那你早点睡", ms(2026, 10, 20) + 1000)],
         {"speaker": "<OWNER>"}, notes_has=["校正"])

    head("B1 正文自写日期、来源里没有 → 正文不能给自己作证")
    case("B1", R.new_record(6, text="<OWNER>10月26日有一场考试",
                            time_basis=R.TB_EXPLICIT, event_time="10月26日",
                            source_msg_ids=[520], time_raw="后天", **BASE),
         SRC_REL,
         {"time_basis": R.TB_UNKNOWN, "event_time": None,
          "text": lambda t: "10月26" not in t})

    head("B2 正文日期与来源不一致 → 以来源为准")
    case("B2", R.new_record(7, text="<OWNER>10月27日有一场考试",
                            time_basis=R.TB_EXPLICIT, event_time="10月27日",
                            source_msg_ids=[522], **BASE),
         SRC_ABS,
         {"time_basis": R.TB_EXPLICIT,
          "text": lambda t: "10月27" not in t and "10月26" in t})

    head("B3 unknown 却填了 event_time → 无条件置空（正文无时间则不加尾巴）")
    case("B3", R.new_record(8, text="<OWNER>要早起交材料",
                            time_basis=R.TB_UNKNOWN, event_time="10月21日",
                            source_msg_ids=[520], **BASE),
         SRC_REL,
         {"time_basis": R.TB_UNKNOWN, "event_time": None,
          "text": lambda t: "具体日期未确定" not in t})

    head("B4 来源时间 = 'abc' → 不是有效锚点")
    case("B4", R.new_record(9, text="<OWNER>后天要考试",
                            time_basis=R.TB_MESSAGE, event_time="10月22日",
                            source_msg_ids=[520], time_raw="后天",
                            time_anchor_msg_id=520, **BASE),
         [msg(520, "user", "后天那个考试", "abc")],
         {"time_basis": R.TB_UNKNOWN, "event_time": None,
          "text": lambda t: "后天" not in t})

    head("C1 相等日期不得被改写（旧版恒真不等 + 空日期假 note）")
    case("C1", R.new_record(10, text="<OWNER>10月21日要考试", time_raw="明天",
                            time_anchor_msg_id=601, source_msg_ids=[601], **BASE),
         [ANCHOR_20],
         {"event_time": "2026-10-21", "needs_review": False,
          "text": lambda t: t.count("10月21日") == 1},
         notes_not=["与核验结果不一致"])

    head("C2 无年份写法 10-26 也要清（旧版只认 4 位年，漏删）")
    case("C2", R.new_record(11, text="<OWNER>10-26要交材料",
                            source_msg_ids=[603], **BASE),
         [msg(603, "user", "我要交材料", ms(2026, 10, 20))],
         {"event_time": None, "needs_review": True,
          "text": lambda t: "10-26" not in t and "具体日期未确定" not in t})

    head("C3 数值不当日期：体重10.26斤 必须原样保留")
    case("C3", R.new_record(12, text="<OWNER>体重10.26斤",
                            source_msg_ids=[603], **BASE),
         [msg(603, "user", "我体重10.26斤", ms(2026, 10, 20))],
         {"text": lambda t: "10.26" in t})

    head("C4 跨年：12月31日说「明天」→ 次年 1月1日")
    case("C4", R.new_record(13, text="<OWNER>明天要交材料", time_raw="明天",
                            time_anchor_msg_id=607, source_msg_ids=[607], **BASE),
         [ANCHOR_NY],
         {"event_time": "2027-01-01",
          "text": lambda t: "1月1日" in t and "明天" not in t},
         notes_not=["与核验结果不一致"])

    head("C5 「1月2日」出现在 12月的消息里 → 年份无法确定，保留精度上的未知")
    case("C5", R.new_record(14, text="<OWNER>要交材料", time_raw="1月2日",
                            source_msg_ids=[608], **BASE),
         [ANCHOR_DEC],
         {"event_time": "01-02", "time_basis": R.TB_EXPLICIT, "needs_review": True},
         notes_has=["年份未定"])

    head("C6 来源无可用时间时，年份留空并标记复核")
    case("C6", R.new_record(15, text="<OWNER>要考试", time_raw="10月26日",
                            source_msg_ids=[522], **BASE),
         SRC_ABS,
         {"time_basis": R.TB_EXPLICIT, "event_time": "10-26", "needs_review": True},
         notes_has=["年份未定"])

    head("C7 人工修正的时间不被复算推翻")
    manual = R.new_record(16, text="<OWNER>11月5日要交材料",
                          source_msg_ids=[603], **BASE)
    manual["time_basis"] = R.TB_MANUAL
    manual["event_time"] = "2026-11-05"
    case("C7", manual, [msg(603, "user", "我要交材料", ms(2026, 10, 20))],
         {"event_time": "2026-11-05", "time_basis": R.TB_MANUAL,
          "needs_review": True},
         notes_has=["人工修正"])

    head("C8 人工修正的非法日期被置空")
    bad = {"id": "m0017", "kind": "event", "text": "<OWNER>要交材料",
           "source_msg_ids": [], "event_time": "13月40日",
           "time_basis": R.TB_MANUAL, "time_raw": "", "speaker": "",
           "certainty": "", "created": "2026-10-25", "needs_review": False,
           "archived": False}
    case("C8", bad, [],
         {"event_time": None, "time_basis": R.TB_UNKNOWN},
         notes_has=["不合法"])

    head("C9 speaker：无来源则保留并标复核；引用混合角色则置空")
    case("C9a", R.new_record(18, text="两人聊了早起", speaker="绯栀",
                             source_msg_ids=[], **BASE), [],
         {"speaker": "绯栀", "needs_review": True})
    case("C9b", R.new_record(19, text="两人聊了早起", speaker="绯栀",
                             source_msg_ids=[520, 521], **BASE),
         [msg(520, "user", "我要早起", ms(2026, 10, 20)),
          msg(521, "assistant", "那你早点睡", ms(2026, 10, 20) + 1000)],
         {"speaker": "", "needs_review": True})

    head("C9c 正文显式提到双方 = 双人互动，speaker 空但**不**标复核")
    case("C9c", R.new_record(23, text="绯栀追问<OWNER>发的链接是干嘛的，<OWNER>说那只是梯子",
                             source_msg_ids=[520, 521], **BASE),
         [msg(520, "assistant", "那个链接你没说清楚", ms(2026, 10, 23)),
          msg(521, "user", "那就个梯子，已经没用了", ms(2026, 10, 23) + 1000)],
         {"speaker": "", "needs_review": False},
         notes_has=["双人互动"])

    head("C10 「昨晚」按整段识别并可换算（旧版不支持，时间会整条丢掉）")
    case("C10", R.new_record(40, text="绯栀比<OWNER>睡得晚", time_raw="昨晚",
                             time_anchor_msg_id=640, source_msg_ids=[640], **BASE),
         [msg(640, "user", "我昨晚比你晚睡", ms(2026, 10, 20, 8))],
         {"event_time": "2026-10-19", "time_basis": R.TB_MESSAGE})

    head("C11 歧义时间词保留原文（删掉会产生「本20点前」这种残句）")
    case("C11", R.new_record(41, text="<OWNER>要交作品，本周末20点前交",
                             time_raw="本周末20点前",
                             source_msg_ids=[641], **BASE),
         [msg(641, "user", "本周末20点前交作品", ms(2026, 10, 15, 21))],
         {"event_time": None, "needs_review": True,
          "text": lambda t: "本周末20点前" in t and "本20点前" not in t})

    head("C12 「今天下午」= 支持词+时段修饰，不能整串掉成 unknown")
    case("C12", R.new_record(42, text="绯栀画了一下午作业", time_raw="今天下午",
                             time_anchor_msg_id=642, source_msg_ids=[642], **BASE),
         [msg(642, "user", "今天下午画了一整个下午的作业", ms(2026, 10, 15, 20))],
         {"event_time": "2026-10-15", "time_basis": R.TB_MESSAGE})

    head("C13 但含两个支持词时不得挑一个（「明天还是后天」不可确定）")
    case("C13", R.new_record(43, text="<OWNER>要考试", time_raw="明天还是后天",
                             time_anchor_msg_id=643, source_msg_ids=[643], **BASE),
         [msg(643, "user", "明天还是后天考试来着", ms(2026, 10, 15, 20))],
         {"event_time": None, "time_basis": R.TB_UNKNOWN})

    head("C14 正文含多个不同相对词 → 不许压成同一日期（会造出错误日期）")
    case("C14", R.new_record(44, text="绯栀问他昨天是不是还气游戏输了，今天缓过来没",
                             time_raw="昨天", time_basis=R.TB_MESSAGE,
                             time_anchor_msg_id=644, source_msg_ids=[644], **BASE),
         [msg(644, "user", "你晚上干嘛啦，昨天不是还气游戏输了，今天缓过来没",
              ms(2026, 10, 15, 20))],
         {"event_time": "2026-10-14", "needs_review": True,
          "text": lambda t: t.count("10月14日") <= 1 and "今天" in t},
         notes_has=["多个相对词"])

    # ------------------------------------------------------------ D. CRUD
    head("D1 add 自动分配 id 并推进 last_mid（记忆编号序列）")
    recs, stored, notes, last = R.add_record(
        [], {"kind": "fact", "text": "<OWNER>不吃香菜", "certainty": "high",
             "created": "2026-10-25", "source_msg_ids": [605]},
        [msg(605, "user", "我不吃香菜", ms(2026, 10, 20))], last_mid=10)
    ok_d1 = stored["id"] == "m0011" and last == 11 and len(recs) == 1
    print("   id=%r last_mid=%r n=%d %s" % (stored["id"], last, len(recs), OK if ok_d1 else NG))
    _RESULT["pass" if ok_d1 else "fail"] += 1
    ok = ok_d1

    head("D2 add 撞 id 报错")
    try:
        R.add_record(recs, {"id": "m0011", "kind": "fact", "text": "重复",
                            "source_msg_ids": []}, [], last_mid=11)
        print("   ", NG, "本应抛 RecordError")
        ok = False
        _RESULT["fail"] += 1
    except R.RecordError as e:
        print("   ", OK, "如预期拒绝：", e)
        _RESULT["pass"] += 1

    head("D3 patch 正文会重跑 validate（防止绕过时间校验改正文），且不清空溯源码")
    recs2, before, after, pn = R.patch_record(
        recs, "m0011", {"text": "<OWNER>2026-10-26不吃香菜"}, [], reason="")
    ok_d3 = ("10-26" not in after["text"] and "2026" not in after["text"]
             and "具体日期未确定" not in after["text"]
             and after["source_msg_ids"] == [605])
    print("   text=%r src=%r %s"
          % (after["text"], after["source_msg_ids"], OK if ok_d3 else NG))
    print("   说明:", "; ".join(pn)[:120])
    _RESULT["pass" if ok_d3 else "fail"] += 1
    ok &= ok_d3

    head("D4 patch 时间必须给 reason")
    try:
        R.patch_record(recs2, "m0011", {"event_time": "2026-11-05"})
        print("   ", NG, "本应抛 RecordError")
        ok = False
        _RESULT["fail"] += 1
    except R.RecordError as e:
        print("   ", OK, "如预期拒绝：", e)
        _RESULT["pass"] += 1

    head("D5 patch 时间转 manual 且永久 needs_review")
    recs3, _b, after3, pn3 = R.patch_record(
        recs2, "m0011", {"event_time": "2026-11-05"}, [],
        reason="本人确认过是11月5日")
    ok_d5 = (after3["event_time"] == "2026-11-05"
             and after3["time_basis"] == R.TB_MANUAL
             and after3["needs_review"] is True)
    print("   et=%r basis=%r review=%r %s"
          % (after3["event_time"], after3["time_basis"], after3["needs_review"],
             OK if ok_d5 else NG))
    print("   说明:", "; ".join(pn3)[:120])
    _RESULT["pass" if ok_d5 else "fail"] += 1
    ok &= ok_d5

    head("D6 patch 锁字段一律拒绝")
    for fld, val in (("id", "m0099"), ("source_msg_ids", [1, 2]),
                     ("archived", True), ("created", "2020-01-01"),
                     ("time_basis", R.TB_EXPLICIT)):
        try:
            R.patch_record(recs3, "m0011", {fld: val})
            print("   %-16s %s 本应拒绝" % (fld, NG))
            ok = False
            _RESULT["fail"] += 1
        except R.RecordError:
            print("   %-16s %s 已拒绝" % (fld, OK))
            _RESULT["pass"] += 1

    head("D7 patch 未知字段拒绝")
    try:
        R.patch_record(recs3, "m0011", {"whatever": 1})
        print("   ", NG, "本应拒绝")
        ok = False
        _RESULT["fail"] += 1
    except R.RecordError as e:
        print("   ", OK, "已拒绝：", e)
        _RESULT["pass"] += 1

    head("D8 archive 是逻辑删除，不物理删，且幂等")
    recs4, arc = R.archive_record(recs3, "m0011", "他说记错了", "2026-10-25")
    ok_d8 = (arc["archived"] is True and len(recs4) == len(recs3)
             and arc["archive_reason"] == "他说记错了"
             and all(r["id"] != "m0011" for r in R.active_records(recs4)))
    recs5, arc2 = R.archive_record(recs4, "m0011", "再来一次", "2026-10-26")
    ok_d8 = ok_d8 and arc2["archived_at"] == arc["archived_at"] and len(recs5) == len(recs4)
    print("   archived=%r at=%r n=%d/%d %s"
          % (arc["archived"], arc["archived_at"], len(recs4), len(recs3),
             OK if ok_d8 else NG))
    _RESULT["pass" if ok_d8 else "fail"] += 1
    ok &= ok_d8

    head("D9 restore 可撤销")
    recs6, back = R.restore_record(recs5, "m0011")
    ok_d9 = back["archived"] is False and back["archive_reason"] == "" \
        and any(r["id"] == "m0011" for r in R.active_records(recs6))
    print("   archived=%r %s" % (back["archived"], OK if ok_d9 else NG))
    _RESULT["pass" if ok_d9 else "fail"] += 1
    ok &= ok_d9

    head("D10 review_queue 只收未归档且 needs_review 的")
    q = R.review_queue(recs6)
    ok_d10 = all(r["needs_review"] and not r["archived"] for r in q) and len(q) == 1
    print("   队列长度=%d ids=%s %s"
          % (len(q), [r["id"] for r in q], OK if ok_d10 else NG))
    _RESULT["pass" if ok_d10 else "fail"] += 1
    ok &= ok_d10

    def say(label, cond, detail=""):
        _RESULT["pass" if cond else "fail"] += 1
        print("   %s %-46s %s" % (OK if cond else NG, label, str(detail)[:60]))
        return cond

    F_SRC = [msg(610, "user", "明天那个考试", ms(2026, 10, 20))]
    RECALC_SRC = [msg(610, "user", "明天考试，后天交材料", ms(2026, 10, 20))]

    head("F1 普通 patch（只改 certainty）不得推翻已核验时间")
    recs0, s0, _n0, _m0 = R.add_record(
        [], R.new_record(100, text="<OWNER>明天要考试", time_raw="明天",
                         time_anchor_msg_id=610, source_msg_ids=[610], **BASE),
        F_SRC, 100)
    rid0 = s0["id"]
    print("   建好：", s0["event_time"], s0["time_basis"], s0["text"])
    _r1, _b1, a1, _x1 = R.patch_record(recs0, rid0, {"certainty": "mid"})
    print("   只改 certainty：", a1["event_time"], a1["time_basis"], a1["text"])
    ok &= say("event_time 仍是 2026-10-21", a1["event_time"] == "2026-10-21",
              a1["event_time"])
    ok &= say("basis 仍是 message_time", a1["time_basis"] == R.TB_MESSAGE,
              a1["time_basis"])
    ok &= say("正文仍含 10月21日", "10月21日" in a1["text"], a1["text"])
    ok &= say("来源仍是 [610]", a1["source_msg_ids"] == [610], a1["source_msg_ids"])

    head("F2 改 time_raw = 按来源重算（不是 manual）")
    recs2b, _b2, a2, _x2 = R.patch_record(recs0, rid0, {"time_raw": "后天"},
                                          RECALC_SRC)
    print("   改为「后天」：", a2["event_time"], a2["time_basis"], a2["text"])
    ok &= say("event_time 重算为 2026-10-22", a2["event_time"] == "2026-10-22",
              a2["event_time"])
    ok &= say("basis 是 message_time 而非 manual",
              a2["time_basis"] == R.TB_MESSAGE, a2["time_basis"])
    ok &= say("正文跟着改成 10月22日", "10月22日" in a2["text"], a2["text"])

    head("F3 改 time_raw 但缺来源消息体 → 拒绝（不许半套来源硬算）")
    try:
        R.patch_record(recs0, rid0, {"time_raw": "后天"}, [])
        ok &= say("缺来源应被拒", False)
    except R.RecordError as e:
        ok &= say("缺来源被拒", True, str(e)[:50])

    head("F4 add_record 不得接受自报 manual（模型可绕过来源核验）")
    SRC611 = [msg(611, "user", "我要早起", ms(2026, 10, 20))]
    try:
        R.add_record([], {"kind": "event", "text": "<OWNER>11月5日要交材料",
                          "time_basis": "manual", "event_time": "2026-11-05",
                          "source_msg_ids": [611]}, SRC611, 0)
        ok &= say("自报 manual 应被拒", False)
    except R.RecordError as e:
        ok &= say("自报 manual 被拒", True, str(e)[:50])

    head("F5 add_manual_record 是唯一合法 manual 入口，且必须给 reason")
    try:
        R.add_manual_record([], {"kind": "event", "text": "<OWNER>要交材料",
                                 "event_time": "2026-11-05",
                                 "source_msg_ids": [611]}, SRC611, 0)
        ok &= say("无 reason 应被拒", False)
    except R.RecordError as e:
        ok &= say("无 reason 被拒", True, str(e)[:40])
    try:
        _rm, sm, _nm, _mm = R.add_manual_record(
            [], {"kind": "event", "text": "<OWNER>要交材料",
                "event_time": "2026-11-05", "source_msg_ids": [611]},
            SRC611, 0, reason="他本人说的")
        ok &= say("有 reason 则生效", sm["event_time"] == "2026-11-05"
                  and sm["time_basis"] == R.TB_MANUAL, sm["time_basis"])
        ok &= say("人工新增必定待复核", sm["needs_review"] is True, "")
    except R.RecordError as e:
        ok &= say("有 reason 应成功", False, str(e)[:50])

    head("Y1 「10月25日说 10月20日交了材料」→ 年份不能猜成明年")
    case("Y1", R.new_record(20, text="<OWNER>要交材料", time_raw="10月20日",
                            source_msg_ids=[620], **BASE),
         [msg(620, "user", "10月20日交了材料", ms(2026, 10, 25))],
         {"event_time": "10-20", "needs_review": True},
         notes_has=["年份未定"])

    head("Y2 正文写 2025-10-21、字段核验 2026-10-21 → 冲突必须被发现")
    case("Y2", R.new_record(21, text="<OWNER>2025-10-21要考试", time_raw="明天",
                            time_anchor_msg_id=621, source_msg_ids=[621], **BASE),
         [msg(621, "user", "明天考试", ms(2026, 10, 20))],
         {"event_time": "2026-10-21", "needs_review": True,
          "text": lambda t: "2025" not in t and "10月21日" in t})

    head("Y3 年份未知时返回 10-26，needs_review 必须为 True")
    case("Y3", R.new_record(22, text="<OWNER>要考试", time_raw="10月26日",
                            source_msg_ids=[622], **BASE),
         [msg(622, "user", "10月26日考试", 0)],
         {"event_time": "10-26", "needs_review": True},
         notes_has=["年份未定"])

    head("A6 自动新增：来源 id 无效 → 必须拒绝（不能剔除来源后照收）")
    try:
        R.add_record([], {"kind": "event", "text": "<OWNER>要考试",
                          "source_msg_ids": [999]},
                     [msg(1, "user", "随便聊聊", ms(2026, 10, 20))], 0)
        ok &= say("无效来源应被拒", False)
    except R.RecordError as e:
        ok &= say("无效来源被拒", True, str(e)[:48])

    head("A7 自动新增：来源为空 → 必须拒绝（历史迁移才有无来源例外）")
    try:
        R.add_record([], {"kind": "event", "text": "<OWNER>要考试",
                          "source_msg_ids": []},
                     [msg(1, "user", "随便聊聊", ms(2026, 10, 20))], 0)
        ok &= say("空来源应被拒", False)
    except R.RecordError as e:
        ok &= say("空来源被拒", True, str(e)[:48])

    head("Y4 来源「去年11月2日」→ 暂不支持，且不能截取月日后宣布核验成功")
    case("Y4", R.new_record(30, text="<OWNER>参加了比赛", time_raw="去年11月2日",
                            source_msg_ids=[630], **BASE),
         [msg(630, "user", "去年11月2日参加了比赛", ms(2026, 10, 25))],
         {"event_time": None, "time_basis": R.TB_UNKNOWN,
          "text": lambda t: "11月2" not in t and "去年" not in t},
         notes_has=["相对年份"])

    head("Y5 来源「2025年11月2日」→ 必须识别原文写明的中文年份")
    case("Y5", R.new_record(31, text="<OWNER>参加了比赛", time_raw="2025年11月2日",
                            source_msg_ids=[631], **BASE),
         [msg(631, "user", "2025年11月2日参加了比赛", ms(2026, 10, 25))],
         {"event_time": "2025-11-02", "time_basis": R.TB_EXPLICIT})

    head("Y6 缺年份「11月2日」→ 保留 MM-DD，不靠月日先后补年")
    case("Y6", R.new_record(32, text="<OWNER>要参加比赛", time_raw="11月2日",
                            source_msg_ids=[632], **BASE),
         [msg(632, "user", "11月2日参加比赛", ms(2026, 10, 25))],
         {"event_time": "11-02", "time_basis": R.TB_EXPLICIT,
          "needs_review": True},
         notes_has=["年份未定"])

    head("E1 旧数据迁移（稳定 id、added→created、不补造来源）")
    migrated, lastmid = R.migrate_legacy(
        [{"text": "<OWNER>明天9点有课", "added": "2026-10-16"},
         {"text": "绯栀养了一只叫糊糊的宠物", "certainty": "high", "added": "2026-10-16"}],
        100, "2026-10-25")
    for r in migrated:
        print("   %s | %s | created=%s | src=%s | basis=%s"
              % (r["id"], r["text"][:22], r["created"], r["source_msg_ids"],
                 r["time_basis"]))
    ok_e = ([r["id"] for r in migrated] == ["m0101", "m0102"]
            and all(r["source_msg_ids"] == [] and r["created"] == "2026-10-16"
                    for r in migrated))
    _RESULT["pass" if ok_e else "fail"] += 1
    ok &= ok_e
    print("   ", OK if ok_e else NG)

    head("结论：%d 通过 / %d 失败" % (_RESULT["pass"], _RESULT["fail"]))
    return 0 if ok and _RESULT["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
