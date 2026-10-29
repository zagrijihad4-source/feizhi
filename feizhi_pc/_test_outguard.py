# -*- coding: utf-8 -*-
"""输出检查回归（按 YG 指定的四类样本 + 全量回放）。

四类固定样本：
    1. 已出现的 1428 字符泄漏（从真实回答里取，不手写）
    2. 「【你真正记得的事】里……」这类元文本引用
    3. 正常自我介绍（必须不被拦）
    4. 正常引用记忆的回答（必须不被拦）

另外做**全量回放**：把主实验里 210 条真实回答全部过一遍 outguard，
统计误拦率——这是「正常回答是否被误拦」的唯一可靠证据。

验收三项：泄漏被阻止 / 正常回答不误拦 / 异常恢复可用。

用法:
    python _test_outguard.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FEIZHI = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(FEIZHI))
import outguard  # noqa: E402

EVAL = FEIZHI / "eval"


def real_leak() -> tuple[str, str]:
    """从真实回答里找那条 1428 字符的泄漏。"""
    f = sorted(EVAL.glob("answers_rerun3_20261025-164623.json"))[-1]
    d = json.loads(f.read_text(encoding="utf-8"))
    best = max((a for a in d["answers"] if a.get("ok")),
               key=lambda a: len(a.get("output") or ""))
    return "真实泄漏（%d 字符, %s/%s）" % (len(best["output"]), best["case_id"], best["mode"]), best["output"]


def main() -> int:
    print("=" * 78)
    print("一、四类固定样本")
    print("=" * 78)

    name, leak = real_leak()
    samples = [
        (name, leak, "severe"),
        ("元文本引用", "【你真正记得的事】里翻一遍……没有他手机号这条。我这儿没翻到啊，你再给我手机号？", "light"),
        ("正常自我介绍", "我是绯栀啊，19岁，美院视觉传达大二的，杭州人。你问这个干嘛[白眼]", "ok"),
        ("正常引用记忆", "石家庄啊，你自己说的，还问我那边多少度来着。怎么突然问这个？", "ok"),
        # ★ 长段记忆复述：记忆条目最长约 33 字，正常复述不能被判泄漏
        ("复述长记忆(33字)", "你不是说<OWNER>把猫粮倒多了吗——绯栀给糊糊倒猫粮手抖倒多了，糊糊吃十分钟撑得趴地上，吓了她半天。", "ok"),
        ("复述长记忆(短)", "<OWNER>夸你海报是低奢配色，像苹果牌子的质感，你当时还挺受用的。", "ok"),
        # ★ 长段聊天原文复述：同样不能判泄漏
        ("复述聊天原文", "你自己说的啊，你刚睡醒那会儿不是讲「好困啊，我逃课了，回去睡觉去了」，我还劝你别低头看手机。", "ok"),
    ]

    ok = True
    for cname, text, expect in samples:
        v = outguard.inspect(text)
        good = v["level"] == expect
        ok &= good
        print("%-26s 期望 %-7s 实际 %-7s %s"
              % (cname, expect, v["level"], "✓" if good else "✗"))
        if v["level"] != "ok":
            g, st = outguard.guard(text, log=lambda m: None)
            print("%-26s -> [%s] %s" % ("", st, (g or "(不发)")[:70]))

    print()
    print("=" * 78)
    print("二、异常恢复：严重样本必须被「阻止」而不是「删掉标题后继续发」")
    print("=" * 78)
    g, st = outguard.guard(leak, log=lambda m: None)
    no_partial = (g == outguard.FALLBACK_TEXT)
    print("状态=%s  文本是否等于短兜底=%s" % (st, no_partial))
    print("兜底文本：", g)
    ok &= no_partial

    print()
    print("=" * 78)
    print("三、全量回放：主实验 210 条 + rerun 文件的全部回答")
    print("=" * 78)

    def replay(pattern: str, label: str) -> tuple[int, list, list]:
        total, blocked, rewritten = 0, [], []
        for f in sorted(p for p in EVAL.glob(pattern) if ".key." not in p.name):
            d = json.loads(f.read_text(encoding="utf-8"))
            for a in d["answers"]:
                t = a.get("output") or ""
                if not a.get("ok") or not t.strip():
                    continue
                total += 1
                v = outguard.inspect(t)
                if v["level"] == "severe":
                    blocked.append((f.name, a["case_id"], a["mode"], v["reasons"], t[:60]))
                elif v["level"] == "light":
                    rewritten.append((f.name, a["case_id"], a["mode"], v["reasons"], t[:60]))
        print("%-22s 回放 %3d 条：严重 %d，轻微 %d，通过 %d"
              % (label, total, len(blocked), len(rewritten), total - len(blocked) - len(rewritten)))
        return total, blocked, rewritten

    t_main, b_main, r_main = replay("answers_fixed_*.json", "主实验 run1")
    t_rep, b_rep, r_rep = replay("answers_repeat2_*.json", "主实验 run2/3")
    t_rer, b_rer, r_rer = replay("answers_rerun3_*.json", "rerun（含已知泄漏）")

    main_total = t_main + t_rep
    main_bad = len(b_main) + len(b_rep)
    print()
    print("主实验合计 %d 条，其中被拦 %d 条 —— **误拦率 %.1f%%**"
          % (main_total, main_bad, 100.0 * main_bad / max(1, main_total)))
    for tag, lst in (("主实验被拦", b_main + b_rep), ("rerun 被拦", b_rer),
                     ("被改写", r_main + r_rer)):
        for src, cid, mode, why, head in lst[:8]:
            print("  [%s] %-9s %-12s %s | %s"
                  % (tag, cid, mode, "; ".join(why), head.replace("\n", " ")))

    # rerun 里那条 1428 字泄漏必须被拦
    caught = any("提示词原文重合" in "; ".join(w) for *_, w, _h in b_rer)
    print()
    print("已知泄漏是否被捕获：%s" % ("是" if caught else "**否**"))
    ok &= caught and (main_bad == 0)

    print()
    print("=" * 78)
    print("结论：", "通过" if ok else "需复核")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
