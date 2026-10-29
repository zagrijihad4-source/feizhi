"""反思层单测：构造数据，逐条验证判据。

重点不是「跑通」，而是钉住几件容易悄悄变坏的事：
  * **绝不修改 memory** —— 这是反思层的硬约束，用字节比对钉死。
  * F/E 编号与 `render_existing()` 一致 —— 否则报告指错记录。
  * 相对词的最长匹配 —— 「大后天」不能被当成「后天」。
  * 已知假阳性（「刚刚好」「没回家」「现在住…」）不许复现。

跑法：<PYTHON_HOME>\\Python313\\python.exe _test_reflect.py
"""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

import reflect  # noqa: E402
from memory import FeizhiMemory  # noqa: E402

TODAY = date(2026, 10, 27)
OK = 0
FAIL = []


def check(name, cond, detail=""):
    global OK
    if cond:
        OK += 1
    else:
        FAIL.append("%s%s" % (name, (" :: " + detail) if detail else ""))


def make_mem(tmp, facts=None, events=None):
    p = Path(tmp) / "mem.json"
    p.write_text(json.dumps({"facts": facts or [], "events": events or []},
                            ensure_ascii=False), encoding="utf-8")
    return FeizhiMemory(path=p)


def find(rep, check_name, ref):
    for f in rep["findings"]:
        if f["check"] == check_name and ref in f["refs"]:
            return f
    return None


with tempfile.TemporaryDirectory() as td:
    # ---------- 1. 编号与判据 ----------
    mem = make_mem(
        td,
        facts=[
            {"text": "<OWNER>明天9点有课", "created": "2026-10-16"},      # F01 过期
            {"text": "<OWNER>在石家庄", "created": "2026-10-16"},          # F02 无时间词
            {"text": "绯栀现在住石家庄", "created": "2026-10-16"},      # F03 降级复核
        ],
        events=[
            {"text": "绯栀给<OWNER>唱了歌", "created": "2026-10-20"},      # E01 干净
            {"text": "绯栀问配色行不行，<OWNER>还没回", "created": "2026-10-20"},  # E02 瞬时
        ])
    before = mem.path.read_bytes()
    rep = reflect.scan(mem, today=TODAY)
    after = mem.path.read_bytes()

    check("不改动 memory 文件", before == after)
    check("scanned 计数", rep["scanned"] == 5, str(rep["scanned"]))

    f01 = find(rep, "time_leak", "F01")
    check("F01 判出过期", f01 is not None)
    if f01:
        check("F01 action=archive", f01["action"] == "archive", f01["action"])
        check("F01 auto_ok", f01["auto_ok"] is True)
        check("F01 severity=high", f01["severity"] == "high", f01["severity"])
        check("F01 指向 10-17", "2026-10-17" in f01["evidence"], f01["evidence"])

    check("F02 无时间词不报", find(rep, "time_leak", "F02") is None)

    f03 = find(rep, "time_leak", "F03")
    check("F03「现在」被检出", f03 is not None)
    if f03:
        check("F03「现在」只复核不归档",
              f03["action"] == "review" and f03["auto_ok"] is False,
              "%s/%s" % (f03["action"], f03["auto_ok"]))

    check("E01 干净不报", find(rep, "time_leak", "E01") is None
          and find(rep, "transient", "E01") is None)

    e02 = find(rep, "transient", "E02")
    check("E02「还没回」判出瞬时", e02 is not None)
    if e02:
        check("E02 event 不自动归档", e02["auto_ok"] is False)

    # ---------- 2. 相对词偏移 ----------
    with tempfile.TemporaryDirectory() as td2:
        m2 = make_mem(td2, facts=[
            {"text": "<OWNER>大后天要走", "created": "2026-10-20"},   # 最长匹配 → 10-23
            {"text": "<OWNER>后天要走", "created": "2026-10-20"},     # 10-22
        ])
        r2 = reflect.scan(m2, today=TODAY)
        a = find(r2, "time_leak", "F01")
        check("「大后天」按 +3 算",
              a is not None and "2026-10-23" in a["evidence"],
              a["evidence"] if a else "未检出")

    # ---------- 3. 未到期不归档 ----------
    with tempfile.TemporaryDirectory() as td3:
        m3 = make_mem(td3, facts=[{"text": "<OWNER>明天9点有课", "created": "2026-10-27"}])
        r3 = reflect.scan(m3, today=TODAY)
        f = find(r3, "time_leak", "F01")
        check("今天说的「明天」不归档",
              f is not None and f["action"] == "keep",
              "%s" % (f["action"] if f else "未检出"))

    # ---------- 4. 缺入库日 → 复核 ----------
    with tempfile.TemporaryDirectory() as td4:
        m4 = make_mem(td4, facts=[{"text": "<OWNER>明天9点有课"}])
        r4 = reflect.scan(m4, today=TODAY)
        f = find(r4, "time_leak", "F01")
        check("缺入库日只复核",
              f is not None and f["action"] == "review" and f["auto_ok"] is False,
              "%s" % (f["action"] if f else "未检出"))

    # ---------- 5. 跨周词 → 复核 ----------
    with tempfile.TemporaryDirectory() as td5:
        m5 = make_mem(td5, facts=[{"text": "<OWNER>本周末交材料", "created": "2026-10-16"}])
        r5 = reflect.scan(m5, today=TODAY)
        f = find(r5, "time_leak", "F01")
        check("「本周末」只复核",
              f is not None and f["action"] == "review" and f["auto_ok"] is False,
              "%s" % (f["action"] if f else "未检出"))

    # ---------- 6. 已知假阳性不许复现 ----------
    with tempfile.TemporaryDirectory() as td6:
        m6 = make_mem(td6, facts=[
            {"text": "绯栀觉得构图刚刚好", "created": "2026-10-18"},
            {"text": "<OWNER>还没回家", "created": "2026-10-20"},
        ])
        r6 = reflect.scan(m6, today=TODAY)
        check("「刚刚好」不算时间词", find(r6, "time_leak", "F01") is None)
        check("「没回家」不算瞬时状态", find(r6, "transient", "F02") is None)

    # ---------- 7. 重复检测 ----------
    with tempfile.TemporaryDirectory() as td7:
        m7 = make_mem(td7, facts=[
            {"text": "<OWNER>周日没有课", "created": "2026-10-17"},
            {"text": "<OWNER>周日没课，绯栀让他别打游戏太晚", "created": "2026-10-18"},
            {"text": "糊糊", "created": "2026-10-18"},
        ])
        r7 = reflect.scan(m7, today=TODAY)
        dup = [f for f in r7["findings"] if f["check"] == "duplicate"]
        check("剥虚词后判出重复", len(dup) == 1, "得到 %d 组" % len(dup))
        if dup:
            check("重复保留更长的那条", dup[0]["keep"] == "F02", dup[0]["keep"])
            check("重复对涉及两条", dup[0]["refs"] == ["F01", "F02"], str(dup[0]["refs"]))
            check("重复不自动执行", dup[0]["auto_ok"] is False)
        check("过短文本不参与判重",
              not any("F03" in f["refs"] for f in dup))

    # ---------- 8. 跨 kind 重复 ----------
    with tempfile.TemporaryDirectory() as td8:
        m8 = make_mem(
            td8,
            facts=[{"text": "<OWNER>中午吃的是辣椒炒肉", "created": "2026-10-20"}],
            events=[{"text": "绯栀追问<OWNER>中午吃了没，<OWNER>答吃了辣椒炒肉",
                     "created": "2026-10-20"}])
        r8 = reflect.scan(m8, today=TODAY)
        dup = [f for f in r8["findings"] if f["check"] == "duplicate"]
        check("同一件事记在 fact 和 event 也能检出", len(dup) == 1,
              "得到 %d 组" % len(dup))

    # ---------- 9. 归档记录不参与体检 ----------
    with tempfile.TemporaryDirectory() as td9:
        m9 = make_mem(td9, facts=[
            {"text": "<OWNER>明天9点有课", "created": "2026-10-16", "archived": True},
        ])
        r9 = reflect.scan(m9, today=TODAY)
        check("归档记录不进体检", r9["scanned"] == 0, str(r9["scanned"]))

    # ---------- 10. 报告落盘与间隔跳过 ----------
    with tempfile.TemporaryDirectory() as td10:
        m10 = make_mem(td10, facts=[{"text": "<OWNER>在石家庄", "created": "2026-10-16"}])
        rp = Path(td10) / "reflection.json"
        res = reflect.maybe_reflect(m10, path=rp)
        check("首次体检写报告", res.get("ok") is True, str(res))
        check("报告可解析", json.loads(rp.read_text(encoding="utf-8"))["scanned"] == 1)
        check("无残留 .tmp", not rp.with_suffix(".json.tmp").exists())

        res2 = reflect.maybe_reflect(m10, path=rp)
        check("间隔内跳过", res2.get("skipped") == "too_soon", str(res2))

        # 报告损坏后应能自愈重跑，而不是整天静默
        rp.write_text("{ broken", encoding="utf-8")
        res3 = reflect.maybe_reflect(m10, path=rp)
        check("报告损坏后重跑", res3.get("ok") is True, str(res3))

print("通过 %d 项" % OK)
if FAIL:
    print("失败 %d 项：" % len(FAIL))
    for f in FAIL:
        print("  - " + f)
    sys.exit(1)
print("全部通过")
