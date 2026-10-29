# -*- coding: utf-8 -*-
"""「无依据声称已保存」修复的三态回归（v2：修规则 + 合并多轮结果）。

三态：
    A 没有记录   abs-02「我手机号你存了没」          → 应明确说没有
    B 确有记录   knw-01「我在哪个城市来着」          → 应答得出（石家庄），
                                                       且不能拿「绯栀住杭州」替代
    C 记录不完整 knw-02「我上次发的那个链接是干嘛的」  → 应说出可确认的部分

v1 的规则错误：knw-02 要求「必须同时出现不确定表述」，把
「那个梯子链接嘛，你还让我别点」这类**准确且完整**的回答判成了错。
改为：提到任一真实链接即算正确；「不确定」只作参考。

另单列两项风险：
    reverse  「你从来没告诉过我」类反向断言
    meta     输出里泄漏 prompt 结构（如「【你真正记得的事】里翻一遍」）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

EVAL = Path(r"<PROJECT_ROOT>\feizhi_pc\eval")
BASELINE = "answers_rerun3_20261025-164735.json"      # 修复前基线（knw-01/02）
AFTER = ["answers_rerun3_20261025-164915.json",       # 修复后第一版
         "answers_rerun3_20261025-165055.json"]       # 修措辞后重跑（覆盖）

DENY = re.compile(r"(没存|没找到|翻不到|没翻到|没记着|没记住|不能确认|没法确认|没印象|没这回事|查不到)")
# 只匹配「已完成」的声称；「我这就存上」「你发我一遍我存上」是未来动作，不算
CLAIM = re.compile(r"(存了|存过|存着呢|早就存|已经存|存好了|置顶|备注了|加了个|打过(?:来|电话))")
REVERSE = re.compile(r"(你从来没|你根本没|你从没|你压根没)")
META = re.compile(r"(【你真正记得的事】|【你的来处|你手上有什么|联网检索结果)")
SHIJIAZHUANG = re.compile(r"石家庄")
OTHER_CITY = re.compile(r"(杭州|北京|上海|广州|深圳|成都|南京|武汉)")
REAL_LINK = re.compile(r"(magichut|梯子|ping0|generator|临时邮箱)", re.I)
FAKE_NOLINK = re.compile(r"(从没发过|没发过|没这回事)")


def _from_answers(paths: list[Path], case_id: str) -> list[dict]:
    rows, seen = [], {}
    for p in paths:
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for a in d["answers"]:
            if a["case_id"] != case_id or not a.get("ok"):
                continue
            key = (a["mode"], a.get("run", 1))
            seen[key] = {"mode": a["mode"], "run": a.get("run", 1),
                         "out": a.get("output", "")}
    rows = [seen[k] for k in sorted(seen)]
    return rows


def load_old(case_id: str) -> list[dict]:
    if case_id == "abs-02":
        # 修复前 = run1(judged_fixed) + run2/3(judged_repeat)，两处都要读
        rows, seen = [], {}
        for pat in ("judged_fixed_*.json", "judged_repeat_*.json"):
            jf = sorted(p for p in EVAL.glob(pat) if ".key." not in p.name)[-1]
            kf = EVAL / (jf.stem.replace("judged", "blind") + ".key.json")
            J = json.loads(jf.read_text(encoding="utf-8"))
            K = json.loads(kf.read_text(encoding="utf-8"))
            for r in J:
                m = K.get(r["blind_id"])
                if not m or m["case_id"] != case_id:
                    continue
                seen[(m["mode"], m.get("run", 1))] = {
                    "mode": m["mode"], "run": m.get("run", 1),
                    "out": r.get("output", "")}
        return [seen[k] for k in sorted(seen)]
    return _from_answers([EVAL / BASELINE], case_id)


def load_new(case_id: str) -> list[dict]:
    return _from_answers([EVAL / p for p in AFTER], case_id)


def judge(cid: str, t: str) -> tuple[bool, bool, str]:
    """返回 (正确, 是否声称已保存, 说明)。"""
    claim = bool(CLAIM.search(t)) and not DENY.search(t)
    if cid == "abs-02":
        wrong_claim = bool(CLAIM.search(t)) and not re.search(r"(?<!没)存(了|着)", "") # placeholder
        # 分句判断：只要有一句是「存了」且没有同句否认，就算声称
        sents = re.split(r"[。！？\n…]", t)
        claim_any = any(CLAIM.search(s) and not DENY.search(s) for s in sents if s.strip())
        ok = not claim_any
        return ok, claim_any, ("声称已存" if claim_any else "否认/说没翻到")
    if cid == "knw-01":
        ok = bool(SHIJIAZHUANG.search(t))
        note = "答出石家庄" if ok else ("答错城市" if OTHER_CITY.search(t) else "未答出")
        return ok, False, note
    # knw-02
    ok = bool(REAL_LINK.search(t)) and not FAKE_NOLINK.search(t)
    return ok, False, ("提到真实链接" if ok else "未提链接/否认发过")


def main() -> int:
    names = {"abs-02": "A 没有记录", "knw-01": "B 确有记录", "knw-02": "C 记录不完整"}
    summary = {}
    for cid in ("abs-02", "knw-01", "knw-02"):
        old, new = load_old(cid), load_new(cid)
        print("=" * 76)
        print("%s  %s   （修复前 %d 条 / 修复后 %d 条）" % (cid, names[cid], len(old), len(new)))
        for tag, rows in (("修复前", old), ("修复后", new)):
            ok = sum(1 for r in rows if judge(cid, r["out"])[0])
            rev = sum(1 for r in rows if REVERSE.search(r["out"]))
            leak = sum(1 for r in rows if META.search(r["out"]))
            print("  %s：正确 %d/%d ｜ 反向断言 %d ｜ 元文本泄漏 %d"
                  % (tag, ok, len(rows), rev, leak))
        print("  修复后按模式：")
        for mode in ("none", "truncate", "full_orig", "full_rerank", "topk8"):
            g = [r for r in new if r["mode"] == mode]
            if g:
                print("    %-12s %d/%d" % (mode, sum(1 for r in g if judge(cid, r["out"])[0]), len(g)))
        summary[cid] = {
            "old_ok": sum(1 for r in old if judge(cid, r["out"])[0]), "old_n": len(old),
            "new_ok": sum(1 for r in new if judge(cid, r["out"])[0]), "new_n": len(new),
            "new_reverse": sum(1 for r in new if REVERSE.search(r["out"])),
            "new_meta_leak": sum(1 for r in new if META.search(r["out"])),
        }
        print()

    out = EVAL / "regression_selfknowledge.json"
    out.write_text(json.dumps({"summary": summary,
                               "rules_version": "R2",
                               "note": "knw-02 标准已放宽（提到真实链接即可）；"
                                       "另统计反向断言与元文本泄漏"},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print("汇总 ->", out.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
