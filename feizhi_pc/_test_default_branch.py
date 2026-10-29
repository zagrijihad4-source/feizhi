# -*- coding: utf-8 -*-
"""默认分支自查的定向回归：两个 P1 + 一个 P2。**全程离线。**

P1-a 非法抽取结果（`{}` 或缺 facts/events）推进水位 → 永久漏抽
P1-b 记忆文件读取失败后退回空库 → 后续写入覆盖原文件
P2   非法引用被强转成真实 ID（`true`→1、`1.9`→1）

用法: python _test_default_branch.py
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
RES = {"pass": 0, "fail": 0}


def check(label, cond, detail=""):
    RES["pass" if cond else "fail"] += 1
    print("   %s %-48s %s" % ("[ OK ]" if cond else "[FAIL]", label, str(detail)[:50]))
    return cond


def head(t):
    print()
    print("=" * 76)
    print(t)
    print("=" * 76)


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def recent(self, limit=120):
        return list(self.rows)


class FakeLLM:
    def __init__(self, out):
        self.out = out

    def chat(self, system, user, **kw):
        return self.out


def rows(mid, n=8):
    return [{"id": mid + i, "role": "user", "text": "消息%d" % i,
             "sent_at_ms": 1792000000000 + i * 1000, "peer_wxid": PEER}
            for i in range(n)]


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="default_branch_"))
    ok = True
    try:
        head("P1-a 非法抽取结果不得推进水位")
        for payload, label, want_err in (
                ("{}", "空对象 {}", True),
                ('{"other": []}', "缺少 facts/events", True),
                ('{"facts": [], "events": []}', "合法空结果", False)):
            m = M.FeizhiMemory(tmp / ("p1a_%d.json" % abs(hash(label))))
            r = m.maybe_extract(FakeStore(rows(100)), PEER, FakeLLM(payload),
                                min_new=8, min_interval=0.0)
            err = r.get("error")
            ok &= check("%s → %s" % (label, "报错且不推进" if want_err else "正常推进"),
                        (err == "invalid_shape") if want_err else (err is None),
                        err or "ok")
            if want_err:
                ok &= check("  水位仍为 0（那批没被跳过）",
                            m.data.get("last_id", 0) == 0, m.data.get("last_id"))
            else:
                ok &= check("  合法空结果照常推进", m.data.get("last_id", 0) > 0,
                            m.data.get("last_id"))

        head("P1-b 读取失败后不得覆盖原文件")
        bad = tmp / "corrupt.json"
        bad.write_text('{"facts": [{"text": "<OWNER>不吃香菜"}, BROKEN', encoding="utf-8")
        orig_bytes = bad.read_bytes()
        m2 = M.FeizhiMemory(bad)
        ok &= check("记录到读取失败", bool(getattr(m2, "_load_error", "")),
                    (getattr(m2, "_load_error", "") or "")[:40])
        baks = list(bad.parent.glob("corrupt.json.corrupt-*"))
        ok &= check("原文件已备份", bool(baks), [b.name for b in baks])
        ok &= check("原文件本身没被改", bad.read_bytes() == orig_bytes)
        try:
            m2.save()
            ok &= check("保护态 save() 应抛错", False)
        except M.MemoryLoadError as e:
            ok &= check("保护态 save() 抛 MemoryLoadError", True, str(e)[:40])
        ok &= check("原文件仍未变", bad.read_bytes() == orig_bytes)
        m2.save(override_load_error=True)
        ok &= check("显式 override 后可写", True)

        head("P2 非法引用不得被强转成真实 ID")
        b = rows(1, 8)
        cases = [
            ([True], "bool true", False),
            ([1.9], "float 1.9", False),
            (["1"], "字符串 \"1\"", True),
            ([1], "正常整数 1", True),
            ([-3], "负数 -3", False),
            ([0], "零 0", False),
        ]
        for src, label, should_accept in cases:
            try:
                recs, stored, _n, _m = R.add_record(
                    [], {"kind": "event", "text": "测试%d" % abs(hash(label)),
                         "source_msg_ids": src}, b, 0, gate_state="eligible")
                accepted = True
                got = stored.get("source_msg_ids")
            except R.RecordError as e:
                accepted = False
                got = str(e)[:24]
            ok &= check("来源 %-12s → %s" % (label, "接受" if should_accept else "拒绝"),
                        accepted == should_accept, got)

        head("P2-b 锚点不得被强转")
        b2 = rows(1, 8)
        b2[0]["text"] = "明天那个考试"
        for anchor, label, want_none in ((True, "bool true", True),
                                         (1.9, "float 1.9", True),
                                         (1, "整数 1", False)):
            o, _ = R.validate(R.new_record(9, kind="event", text="<OWNER>要考试",
                                           time_raw="明天", time_anchor_msg_id=anchor,
                                           source_msg_ids=[1]), b2)
            got_none = o.get("time_raw_at_ms") is None
            ok &= check("锚点 %-12s → 原话时间%s" % (label, "为空" if want_none else "有效"),
                        got_none == want_none,
                        "gate=%s" % (o.get("time_raw_at_ms"),))

        head("P2-c 提升入口同样不得强转")
        try:
            R.promote_quarantined(
                [{"id": "m0001", "kind": "event", "text": "测试", "source_msg_ids": [],
                  "quarantined": True, "archived": False, "gate_state": "eligible",
                  "created": "2026-10-26"}],
                "m0001", [True], b2, gate_state="eligible")
            ok &= check("bool 来源应被拒", False)
        except R.RecordError as e:
            ok &= check("bool 来源被拒", True, str(e)[:40])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    head("结论：%d 通过 / %d 失败" % (RES["pass"], RES["fail"]))
    return 0 if ok and RES["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
