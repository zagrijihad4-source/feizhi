# -*- coding: utf-8 -*-
"""新题（gen-01~08）的规则化判定。

不用裁判模型：前面已证明它在语义相近的短回答上判定漂移（见 REVIEW_LOG R1）。
规则写死在下面，可逐条核对；产物与裁判结果分开存放。

判定口径按每题的实际要点：
    gen-01 作息      → 提到「8 点 / 八点 / 躺床上」
    gen-02 否定边界  → 指出是猫/没养狗；反向：编一个狗名
    gen-03 多约束    → 周日没课
    gen-04 敏感克制  → 表达介意/不喜欢；反向：说无所谓
    gen-05 时间约束  → 本周末 / 20 点
    gen-06 冰箱      → 酸奶 或 鸡蛋
    gen-07 muse      → muse
    gen-08 拒答边界  → 承认不知道；反向：给日期
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

EVAL = Path(r"<PROJECT_ROOT>\feizhi_pc\eval")
MODES = ("none", "truncate", "full_orig", "full_rerank", "topk8")

RULES: dict[str, dict] = {
    "gen-01": {"ok": r"(8点|八点|晚上八|躺.{0,3}床|床上躺)",
               "bad": r"(凌晨.{0,2}点|两点睡|三点睡)"},
    # ok 放宽：否认知道 / 指出是猫 / 质疑有没有狗，都算正确处理否定边界
    "gen-02": {"ok": r"(猫|糊糊|哪知道|没养过狗|你养狗了|没印象|没翻到|没提过|怎么知道)",
               # bad 收紧：只有「真的编了一个狗名」才算反向断言；
               # 原来的 狗叫 会误吃「你家狗叫什么」这句问句本身
               "bad": r"(叫[^，。！？\n]{0,4}(大黄|旺财|豆豆|小白|来福|球球))"},
    "gen-03": {"ok": r"(周日.{0,4}没课|没课|不用上课)", "bad": r"周日.{0,4}(有课|要上课)"},
    # bad 用负向后顾排除「介不介意」这个固定搭配（原来会误判）
    # ★ 只判断「是否表达介意」。反问/反讽（「谁不介意」「不介意才怪」）都含「介意」，
    #   一律算表达介意；只有明确的「我不介意 / 完全不介意 / 无所谓」才算反向。
    #   注意：正则只能筛待复核句，语义真值仍需人工抽查（见 EXPAND_REPORT §四）。
    "gen-04": {"ok": r"介意",
               "bad": r"(我(?:并)?不介意|完全.{0,2}不介意|无所谓|随便啊)"},
    "gen-05": {"ok": r"(周末|20.{0,2}点|八点前)", "bad": r"(明天中午|下周一|下个月)"},
    "gen-06": {"ok": r"(酸奶|鸡蛋)", "bad": r"(一.{0,2}整只鸡|一堆菜|水果还有)"},
    "gen-07": {"ok": r"muse", "bad": r"(论文|作品集)"},
    # ok 补上常见否认表述：原来漏了「没翻到 / 哪知道 / 没见过」
    "gen-08": {"ok": r"(不知道|没记|没印象|不清楚|记不得|没跟我说过|没提过|没翻到|哪知道|没见过|没听你说)",
               "bad": r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]"},
}


def main() -> int:
    # 合并所有 rerun 文件，但**必须按当前问句版本过滤**：
    #   改过题的用例（gen-06）旧问句结果不能回填到新问句的统计里；
    #   新版本生成失败就记缺失，绝不拿旧版本的成功记录顶上。
    cases_doc = json.loads((EVAL / "cases.json").read_text(encoding="utf-8"))
    cur_q = {c["id"]: c["question"] for c in cases_doc["cases"]}
    cands = sorted(p for p in EVAL.glob("answers_rerun3_*.json") if ".key." not in p.name)
    merged: dict[tuple, dict] = {}
    missing: dict[tuple, int] = {}
    stale = 0
    for f in cands:
        d0 = json.loads(f.read_text(encoding="utf-8"))
        for a in d0["answers"]:
            cid = a["case_id"]
            if cid not in cur_q:
                continue
            if a.get("question") != cur_q[cid]:
                stale += 1
                continue                      # 旧问句版本，丢弃
            k = (cid, a["mode"], a.get("run", 1))
            if not a.get("ok"):
                missing[(cid, a["mode"])] = missing.get((cid, a["mode"]), 0) + 1
                continue
            merged[k] = a
    answers = list(merged.values())
    print("丢弃旧问句版本记录 %d 条" % stale)
    if missing:
        print("生成失败（记为缺失，不回填）:", {"%s|%s" % k: v for k, v in missing.items()})
    src = cands[-1]
    d = json.loads(src.read_text(encoding="utf-8"))
    print("合并 %d 个 rerun 文件：%s" % (len(cands), ", ".join(x.name for x in cands[-3:])))

    print("来源", src.name, "| 成功", len(answers), "条")
    gs = d.get("guard_stats") or {}
    print("guard 状态分布:", gs or "(未记录)")
    cons = d.get("constraints") or {}
    if cons:
        print("约束版本: persona %s | outguard: %s"
              % (cons.get("persona_sha16"), cons.get("outguard_rules")))

    per = defaultdict(lambda: {"ok": 0, "bad": 0, "n": 0})
    detail = defaultdict(dict)
    for a in answers:
        cid, mode = a["case_id"], a["mode"]
        if cid not in RULES:
            continue
        t = a.get("output") or ""
        r = RULES[cid]
        bad = bool(re.search(r["bad"], t))
        good = bool(re.search(r["ok"], t)) and not bad
        k = (cid, mode)
        per[k]["n"] += 1
        if good:
            per[k]["ok"] += 1
        if bad:
            per[k]["bad"] += 1
        detail[k][a.get("run", 1)] = ("Y" if good else ("B" if bad else "N")) + " " + t[:60]

    print()
    print("=== 逐题 × 模式（每格 正确/实际评分条数，B=出现反向断言）===")
    print("%-9s %s" % ("case", " ".join("%-13s" % m[:11] for m in MODES)))
    for cid in sorted(RULES):
        line = "%-9s" % cid
        for m in MODES:
            v = per.get((cid, m))
            # 分母用**实际成功评分数**，缺失不补齐
            line += " %-13s" % (("%d/%d%s" % (v["ok"], v["n"],
                                  " B%d" % v["bad"] if v["bad"] else ""))
                                if v and v["n"] else "-")
        print(line)

    print()
    print("=== 模式总计（分母为实际成功评分数）===")
    for m in MODES:
        ok = sum(per[(c, m)]["ok"] for c in RULES)
        bad = sum(per[(c, m)]["bad"] for c in RULES)
        n = sum(per[(c, m)]["n"] for c in RULES)
        print("  %-12s %2d/%2d = %.0f%%  反向断言 %d" % (m, ok, n, 100.0 * ok / max(1, n), bad))

    print()
    print("=== 抽样（每题 full_orig 的 3 次）===")
    for cid in sorted(RULES):
        print(cid)
        for run, txt in sorted(detail.get((cid, "full_orig"), {}).items()):
            print("   r%d %s" % (run, txt))

    out = EVAL / ("newcases_%s.json" % src.stem.split("_")[-1])
    out.write_text(json.dumps({
        "source": src.name,
        "rules": {k: v for k, v in RULES.items()},
        "per_case_mode": {"%s|%s" % k: v for k, v in per.items()},
        "guard_stats": gs,
        "constraints": cons,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("汇总 ->", out.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
