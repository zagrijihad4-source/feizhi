# -*- coding: utf-8 -*-
"""写入端输入修复的验证 v2（固定绝对时间 + 语义明确的用例）。

v1 的三个问题（已核实并修正）：
  1. 时间用「运行时刻 - 2 天」拼出来，导致实际时间是 10-24 19:10 而不是注释里写的
     23:58→00:03，**跨午夜场景根本没构造**。→ 现在全部用**固定绝对时间**，可复现。
  2. 「糊糊又钻进**我**晾的衣服里」这条本来就是 `role=user`（<OWNER>）说的，
     抽成「<OWNER>晾的衣服」符合输入，不能判主体错位。
     → 拆成：复述过去 / 明确再次发生 / 不同说话者用「我」三个独立场景。
  3. 「时间未知」不等于「事件时间必然未知」：原文若明确写「10月26日考试」，
     即使消息时间缺失，该日期仍有直接依据。→ 单独成一个场景。

场景（全部固定时间，北京时间）：

  批 1 · 时间
    T1 跨午夜     10-20 23:58 <OWNER>「明天要早起交材料」 → 期望日期 10-21
    T2 无锚点     时间=0    <OWNER>「后天那个考试我有点慌」 → **不应出现任何日期**
    T3 原文有日期 时间=0    <OWNER>「10月26日那个考试我有点慌」 → **允许 10-26**

  批 2 · 重复与归属
    D1 复述过去   10-22 20:00 绯栀「我上次讲糊糊钻晾衣堆那事，你还笑我」
                  → 已有 F21/E02，**不应新增**
    D2 明确再次   10-22 20:10 绯栀「糊糊今天又钻进我晾的衣服里了」
                  → 新发生，**允许新增**，且晾衣者=绯栀
    D3 说话者=<OWNER> 10-22 20:20 <OWNER>「我今天晾衣服，糊糊又钻进去了」
                  → 允许新增，晾衣者=**<OWNER>**（与 D2 对照）

隔离：每个批次重建沙箱副本，不碰生产状态，不推进抽取水位。

用法:
    python _test_memory_input.py
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

FEIZHI = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(FEIZHI))

import memory as M  # noqa: E402
from store import ContextStore  # noqa: E402
from llm import LLMClient  # noqa: E402

SNAP = FEIZHI / "eval" / "snapshots" / "20261025-132233"
SANDBOX = FEIZHI / "eval" / "tmp_sandbox"
PEER = "<WXID_FRIEND_A>"
BJ = timezone(timedelta(hours=8))


def ts(y, mo, d, h, mi) -> int:
    return int(datetime(y, mo, d, h, mi, tzinfo=BJ).timestamp() * 1000)


# 固定绝对时间（北京时间）
BATCHES = {
    "T-时间": [
        # (sent_at_ms, role, text)
        (ts(2026, 10, 20, 23, 58), "user",      "明天要早起交材料"),
        (ts(2026, 10, 21, 0, 3),   "assistant", "那你早点睡啊，别熬了"),
        (0,                        "user",      "后天那个考试我有点慌"),          # T2 无锚点
        (0,                        "user",      "10月26日那个考试我有点慌"),      # T3 原文有日期
    ],
    # T2 必须单独一批：它和 T3 都含「考试」，混在一起无法分辨哪条新增对应哪个场景
    "T2-单独(无锚点)": [
        (0, "user", "后天那个考试我有点慌"),
    ],
    "D-重复与归属": [
        (ts(2026, 10, 22, 20, 0),  "assistant", "我上次跟你讲糊糊钻进晾衣堆那事，你还笑我"),  # D1 复述
        (ts(2026, 10, 22, 20, 10), "assistant", "糊糊今天又钻进我晾的衣服里了"),            # D2 绯栀的衣
        (ts(2026, 10, 22, 20, 20), "user",      "我今天晾衣服，糊糊又钻进去了"),            # D3 <OWNER>的衣
    ],
}


def reset_sandbox() -> tuple[Path, Path]:
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir(parents=True)
    mem = SANDBOX / "feizhi_memory.json"
    db = SANDBOX / "context.sqlite3"
    shutil.copy2(SNAP / "feizhi_memory.json", mem)
    shutil.copy2(SNAP / "context.sqlite3", db)
    return mem, db


def static_checks(mem: M.FeizhiMemory) -> bool:
    print("=" * 78)
    print("A. 输入构造（静态）")
    print("=" * 78)
    ok = True
    f, e = mem.facts(), mem.events()
    blob = mem.render_existing()
    miss_f = [i for i, x in enumerate(f, 1) if x.get("text") and x["text"] not in blob]
    miss_e = [i for i, x in enumerate(e, 1) if x.get("text") and x["text"] not in blob]
    print("已有记忆 facts %d / events %d；render_existing %d 字符" % (len(f), len(e), len(blob)))
    print("  未出现 facts: %s ｜ 未出现 events: %s" % (miss_f or "无", miss_e or "无"))
    print("  含「入库日」说明: %s" % ("入库日" in blob))
    ok &= not miss_f and not miss_e

    print("\n  时间渲染：")
    for label, v in [("23:58", ts(2026, 10, 20, 23, 58)), ("00:03", ts(2026, 10, 21, 0, 3)),
                     ("None", None), ("0", 0), ("'abc'", "abc")]:
        print("    %-8s -> %s" % (label, M.fmt_msg_time(v)))
    ok &= M.fmt_msg_time(None) == "未知" and M.fmt_msg_time(0) == "未知"
    return ok


def run_batch(name: str, msgs: list) -> dict:
    mem_path, db_path = reset_sandbox()
    mem = M.FeizhiMemory(mem_path)
    store = ContextStore(db_path)

    # ★ 关键：快照里有 511~519 九条**未处理积压**（记忆水位 last_id=510）。
    #   不把水位追上，它们每批都会重新进入 fresh，和测试消息一起被抽取 ——
    #   上一版报告把它们误当成"模型额外补记历史"。
    #   这里只在**副本**里把水位推到插入前的最大 id，生产水位不动。
    con0 = sqlite3.connect(str(db_path))
    mx = con0.execute("SELECT COALESCE(MAX(id),0) FROM messages WHERE peer_wxid=?",
                      (PEER,)).fetchone()[0]
    con0.close()
    mem.data["last_id"] = int(mx)
    mem.save()

    for i, (ms, role, text) in enumerate(msgs):
        key = "test:%s:%d" % (name, i)
        # ★ store.add 里是 `ts = sent_at_ms or now`，传 0 会被换成当前时间，
        #   所以先用哨兵 1 插入，再 UPDATE 成真实值（含 0=未知）。
        store.add(PEER, role, text, "test", key, sent_at_ms=ms or 1)

    con = sqlite3.connect(str(db_path))
    for i, (ms, role, text) in enumerate(msgs):
        con.execute("UPDATE messages SET sent_at_ms=? WHERE dedupe_key=?",
                    (ms, "test:%s:%d" % (name, i)))
    con.commit()
    rows = con.execute("SELECT id, role, text, sent_at_ms FROM messages "
                       "WHERE source='test' ORDER BY id").fetchall()
    con.close()

    print("\n" + "=" * 78)
    print("批 %s：输入 %d 条" % (name, len(rows)))
    print("=" * 78)
    for i, role, t, ms in rows:
        print("  id=%d %-9s %-16s %s"
              % (i, "<OWNER>" if role == "user" else "绯栀", M.fmt_msg_time(ms), t[:40]))

    before = {"facts": [x.get("text", "") for x in mem.facts()],
              "events": [x.get("text", "") for x in mem.events()]}
    res = mem.maybe_extract(store, PEER, LLMClient(), min_new=1, min_interval=0.0)
    store.close()      # ★ 抽取之后关连接：否则下一次 reset_sandbox 的 rmtree 会 PermissionError
    print("  抽取:", json.dumps(res, ensure_ascii=False))

    mem2 = M.FeizhiMemory(mem_path)
    bf, be = set(before["facts"]), set(before["events"])
    new = ([x for x in mem2.facts() if x.get("text") not in bf]
           + [x for x in mem2.events() if x.get("text") not in be])
    print("  本次新增 %d 条：" % len(new))
    for x in new:
        print("     -", x.get("text", ""), "|", x.get("certainty", ""))
    return {"res": res, "new": [x.get("text", "") for x in new]}


def check_T(out: dict) -> dict:
    new = "\n".join(out["new"])
    import re
    has_date = re.findall(r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]", new)
    return {
        "T1 跨午夜换算(期望出现10月21日)": "10月21" in new or "10-21" in new,
        "T3 原文日期保留(期望有10月26)": any("考试" in t and ("10月26" in t) for t in out["new"]),
        "_所有日期样本": has_date,
    }


def check_D(out: dict) -> dict:
    new_items = out["new"]
    cat = [t for t in new_items if "糊糊" in t and ("衣" in t or "晾" in t)]
    # D1 复述不该新增：看有没有把"我上次讲…"当新事件
    复述 = [t for t in cat if ("上次" in t or "讲过" in t or "讲了" in t)]
    # D3：<OWNER>说的"我晾衣服"应归属<OWNER>
    <OWNER>衣 = [t for t in cat if "<OWNER>" in t]
    绯栀衣 = [t for t in cat if "绯栀" in t]
    return {
        "D1 复述未重复新增": not 复述,
        "D2/D3 新增条数(允许1-2)": len(cat),
        "归属记录": {"<OWNER>": <OWNER>衣, "绯栀": 绯栀衣},
        "_样本": cat,
    }


def main() -> int:
    mem_path, _ = reset_sandbox()
    ok_static = static_checks(M.FeizhiMemory(mem_path))

    t = run_batch("T-时间", BATCHES["T-时间"])
    ct = check_T(t)
    t2 = run_batch("T2-单独(无锚点)", BATCHES["T2-单独(无锚点)"])
    import re as _re
    ct2 = {"T2 无锚点未猜日期(期望无日期)": not any(
        "考试" in t and _re.search(r"\d{1,2}\s*月", t) for t in t2["new"])}
    d = run_batch("D-重复与归属", BATCHES["D-重复与归属"])
    cd = check_D(d)

    print("\n" + "=" * 78)
    print("C. 判定")
    print("=" * 78)
    ok = ok_static
    for k, v in list(ct.items()) + list(ct2.items()) + list(cd.items()):
        if k.startswith("_"):
            continue
        if isinstance(v, bool):
            print("   %-34s %s" % (k, "✓" if v else "✗"))
            ok &= v
        else:
            print("   %-34s %s" % (k, v))
    print("\n   静态输入构造:", "通过" if ok_static else "需复核")
    print("   生产状态未改动；沙箱:", SANDBOX)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
