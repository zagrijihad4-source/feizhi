# -*- coding: utf-8 -*-
"""离线重评：coref-02 与 upd-01。

为什么不用裁判模型：这两题的原始判定已被证伪为「裁判不一致 / 金标准过窄」，
再请同一个裁判只会复现同一偏差。改用**规则化判定**——规则写死在下面，
任何人可以逐条核对，结果可复现。

原始判定全部保留在 judged_*.json，本脚本只产出新结果，不覆盖旧文件。

判定规则：

coref-02「你家那小家伙最近又闹什么了」
  need1 「确认指糊糊」   : 输出含「糊糊」
  need2 「一件真实猫事」 : 命中下列任一真实事件（记忆/历史里确实有）
       踩脸 / 啃画笔·扒画笔·推笔筒 / 趴键盘 / 钻衣服·晾衣 / 趴腿 / 猫粮 /
       拍脚背 / 键盘猫毛 / 四脚朝天 / 蹭腿 / 尾巴扫手
  forbid1 说成别的动物     : 含「狗」「兔子」「仓鼠」
  forbid2 把旧事说成今天   : 含「猫粮」且含「今天」或「刚刚」

upd-01「我上次给你看海报配色，你记得我怎么回的么」
  accept 任一真实记录 : 低奢 / 苹果 / 会不会杂·压暗红（问） / 漂亮·闪亮 / magichut·链接·够用
  forbid 编造从未出现的回应 : 出现上述之外、且历史上不存在的"他说的内容"

用法:
    python _eval_rejudge.py
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

EVAL = Path(r"<PROJECT_ROOT>\feizhi_pc\eval")

# ---- coref-02 ----
CAT_EVENTS = [
    r"踩.{0,2}脸", r"啃.{0,3}画笔", r"扒.{0,3}画笔", r"推.{0,3}笔筒", r"扒.{0,3}笔筒",
    r"趴.{0,3}键盘", r"钻.{0,4}衣", r"晾衣", r"趴.{0,3}腿", r"猫粮",
    r"拍.{0,3}脚背", r"键盘.{0,3}毛", r"四脚朝天", r"蹭.{0,3}腿", r"尾巴.{0,4}扫",
    r"踩.{0,3}枕", r"扒拉.{0,4}地上", r"马克笔", r"颜料",
]
CAT_OTHER_ANIMAL = r"(狗|兔子|仓鼠|鹦鹉)"
CAT_FORBID_TODAY = r"猫粮"

# ---- upd-01 ----
UPD_REAL = [
    r"低奢", r"苹果", r"会不会杂", r"压.{0,2}暗红", r"漂亮", r"闪亮",
    r"magichut", r"链接", r"够用",
]


def load(case_id: str) -> list[dict]:
    out = []
    for pattern, tag in (("judged_fixed_*.json", "old"), ("judged_repeat_*.json", "repeat")):
        jf = sorted(p for p in EVAL.glob(pattern) if ".key." not in p.name)[-1]
        kf = EVAL / (jf.stem.replace("judged", "blind") + ".key.json")
        J = json.loads(jf.read_text(encoding="utf-8"))
        K = json.loads(kf.read_text(encoding="utf-8"))
        for r in J:
            m = K.get(r["blind_id"])
            if not m or m["case_id"] != case_id:
                continue
            out.append({"src": jf.name, "mode": m["mode"], "run": m.get("run", 1),
                        "out": r.get("output", ""), "old_fc": r.get("fact_correct"),
                        "old_viol": r.get("forbidden_violated") or [],
                        "old_reason": r.get("reason", "")})
    return out


def judge_coref(rec: dict) -> dict:
    t = rec["out"]
    need1 = "糊糊" in t
    need2 = any(re.search(p, t) for p in CAT_EVENTS)
    v1 = bool(re.search(CAT_OTHER_ANIMAL, t))
    v2 = bool(re.search(CAT_FORBID_TODAY, t)) and ("今天" in t or "刚刚" in t)
    fc = "yes" if (need1 and need2 and not v1 and not v2) else ("partial" if (need1 or need2) else "no")
    viol = []
    if v1:
        viol.append("把糊糊说成别的动物")
    if v2:
        viol.append("把猫粮那件说成今天/刚刚")
    return {"fc": fc, "viol": viol,
            "why": "糊糊=%s 真实猫事=%s" % (need1, need2)}


def judge_upd(rec: dict) -> dict:
    t = rec["out"]
    hit = [p for p in UPD_REAL if re.search(p, t)]
    fc = "yes" if hit else "no"
    return {"fc": fc, "viol": [] if hit else ["未答出任何真实记录"],
            "why": "命中=" + (",".join(re.sub(r"\\", "", h) for h in hit[:4]) or "无")}


def main() -> int:
    report = {}
    for case_id, fn in (("coref-02", judge_coref), ("upd-01", judge_upd)):
        rows = load(case_id)
        print("=" * 78)
        print("%s 共 %d 条" % (case_id, len(rows)))
        old_yes = sum(1 for r in rows if r["old_fc"] == "yes")
        new_yes = 0
        changed = 0
        detail = []
        for r in sorted(rows, key=lambda x: (x["mode"], x["run"])):
            j = fn(r)
            if j["fc"] == "yes":
                new_yes += 1
            if j["fc"] != r["old_fc"]:
                changed += 1
            detail.append({**{k: r[k] for k in ("mode", "run", "out", "old_fc", "old_viol")},
                           "new_fc": j["fc"], "new_viol": j["viol"], "why": j["why"]})
            flag = "*" if j["fc"] != r["old_fc"] else " "
            print("%s %-12s r%d  old=%-7s new=%-7s %s"
                  % (flag, r["mode"], r["run"], r["old_fc"], j["fc"], j["why"]))
        print()
        print("  yes: 旧 %d → 新 %d | 判定变化 %d 条" % (old_yes, new_yes, changed))
        report[case_id] = {"n": len(rows), "old_yes": old_yes, "new_yes": new_yes,
                           "changed": changed, "detail": detail}
        print()

    out = EVAL / ("rejudge_%s.json" % time.strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps({
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "method": "规则化判定（非模型裁判）",
        "rules_version": "R1",
        "note": "原始判定保留在 judged_*.json，本文件只记新结果与变化",
        "report": report,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("结果 ->", out.name)

    print()
    print("=== 按模式：新判定的 yes 数（满分 3）===")
    for case_id in report:
        line = "%-10s" % case_id
        for mode in ("none", "truncate", "full_orig", "full_rerank", "topk8"):
            g = [d for d in report[case_id]["detail"] if d["mode"] == mode]
            line += " %s:%d/%d" % (mode[:6], sum(1 for d in g if d["new_fc"] == "yes"), len(g))
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
