# -*- coding: utf-8 -*-
"""小样本双向核对：语义命中（双口径）+ 漏抽 + 时间分层 + 处置统计。

★ 两套口径，必须分开看：
  hit_loose  —— 只要 gold 的 must_contain 里有一个词出现在抽出正文里（旧口径）。
                这会把「<OWNER>有逃课回去补觉的习惯」算成命中「这次逃课」，
                使命中率虚高。
  hit_strict —— 在 loose 基础上，正文里不得出现 gold 预先写好的 forbid 词
                （习惯/总是/平时…）。用于回答"是否真的覆盖了这条事实"。

脚本只做机械筛选，语义判定留人工。

用法:
    python _review_sample.py                     # 默认 eval/sample_run.json
    python _review_sample.py sample_run_v1.json  # 指定某轮的原始输出
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
EVAL = HERE / "eval"
GOLD = EVAL / "gold_v1.json"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

TIME_KIND_CN = {"full": "完整日期", "month_day": "仅月日",
                "unknown": "无法确定", "none": "无需时间"}
NATURE_CN = {"one_off": "一次发生", "habit": "长期规律", "stable": "稳定属性"}


def hit(text: str, keys) -> bool:
    return any(k in (text or "") for k in (keys or []))


def date_precision(et) -> str:
    if not et:
        return "None"
    s = str(et)
    return "full" if len(s) == 10 else ("month_day" if len(s) == 5 else "?")


def main() -> int:
    run_file = EVAL / (sys.argv[1] if len(sys.argv) > 1 else "sample_run.json")
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    run = json.loads(run_file.read_text(encoding="utf-8"))
    runs = {b["id"]: b for b in run["batches"]}
    print("原始输出：", run_file.name, " 模型：", run["_meta"]["model"],
          " 跑批：", run["_meta"]["ran_at"])
    print()

    tot = {"gold": 0, "loose": 0, "strict": 0, "overshoot": 0}
    disp = {"added": 0, "quarantined": 0, "promoted": 0, "skip": 0, "partial": 0}
    tstat = {}
    overshoots = []
    misses = []

    for batch in gold["batches"]:
        bid = batch["id"]
        r = runs.get(bid)
        print("=" * 78)
        print("批 %s  %s" % (bid, batch["span"]))
        print("=" * 78)
        if not r or r.get("error"):
            print("  [无结果]", (r or {}).get("error"))
            continue
        added = r.get("added") or []
        res = r.get("result") or {}
        tot["added"] = tot.get("added", 0) + len(added)
        disp["added"] += len(added)
        disp["quarantined"] += int(res.get("quarantined_added") or 0)
        disp["promoted"] += int(res.get("promoted") or 0)
        disp["partial"] += 1 if res.get("partial") else 0
        disp["skip"] += len([f for f in (res.get("ingest_fails") or [])
                             if "重复跳过" in f])

        print("  [语义命中] loose=关键词出现 / strict=还要求事件性质不走样")
        for g in batch["gold"]:
            tot["gold"] += 1
            loose = [a for a in added if hit(a["text"], g.get("must_contain"))]
            forbid = g.get("forbid") or []
            # ★ 只要**任一**命中项出现禁止词就判泛化。
            #   取第一条会低估：同一 gold 若既有干净表述又有"习惯"表述，
            #   只看第一条就会放过后者（v2 的「有逃课回去补觉的习惯」就这么漏过）。
            dirty = [a for a in loose if hit(a["text"], forbid)]
            strict = [a for a in loose if a not in dirty]
            tot["loose"] += 1 if loose else 0
            # ★ strict 的语义 = 「这条事实被**干净地**覆盖」：
            #   只要存在任一条泛化表述，就不算覆盖（不能被另一条干净表述抵消）。
            tot["strict"] += 1 if (loose and not dirty) else 0
            if dirty:
                tot["overshoot"] += 1
                words = [w for w in forbid if hit(dirty[0]["text"], [w])]
                overshoots.append({"batch": bid, "gold": g["id"],
                                   "text": dirty[0]["text"], "words": words})
            if not loose:
                misses.append({"batch": bid, "gold": g["id"], "fact": g["fact"]})

            tk = g["time_kind"]
            slot = tstat.setdefault(tk, [0, 0, 0, 0, 0])
            # [总数, 命中, 日期值正确, 仅格式对, 不符或漏落]
            slot[0] += 1
            pick = strict or loose
            if pick:
                slot[1] += 1
            if tk != "none":
                if not pick:
                    slot[4] += 1
                else:
                    et = pick[0]["event_time"]
                    prec = date_precision(et)
                    want = g.get("expect_date")
                    if tk == "unknown":
                        fmt_ok = (et is None)
                        val_ok = fmt_ok
                    elif tk == "full":
                        fmt_ok = (prec == "full")
                        # ★ 必须和预标的**具体日期**比，不是只看是不是完整日期格式。
                        #   ⚠ 局限：若一条记录把**两个不同日期的事**合在一起
                        #   （如「十二点多就睡了，因为有早八」——睡觉是 10-19、早八是 10-20），
                        #   脚本会拿睡觉的日期去评早八，报成"仅格式对（值错）"。
                        #   这不是算错日期，而是**关联事件没有独立落时**。
                        #   这种要看人工，脚本给出的"值错"不能直接当结论。
                        val_ok = (str(et) == str(want)) if want else fmt_ok
                    else:
                        fmt_ok = prec in ("month_day", "full")
                        val_ok = fmt_ok
                    if val_ok:
                        slot[2] += 1
                    elif fmt_ok:
                        slot[3] += 1
                    else:
                        slot[4] += 1

            tag = "strict" if strict else ("**泛化**" if loose else "**漏抽**")
            pick = strict or loose
            et = pick[0]["event_time"] if pick else "-"
            print("    %-4s %-8s %-4s %s"
                  % (g["id"], NATURE_CN.get(g["nature"], "?"), tag, g["fact"][:40]))
            print("         时间层次=%-6s event_time=%r（应为 %r）"
                  % (TIME_KIND_CN[tk], et, g.get("expect_date")))
            if dirty:
                print("         泛化表述=%s" % dirty[0]["text"][:60])
                print("         命中禁止词=%s → 不算覆盖"
                      % [w for w in forbid if hit(dirty[0]["text"], [w])])
                if strict:
                    print("         （另有干净表述，但不能抵消上面这条）")

        matched = set()
        for g in batch["gold"]:
            for a in added:
                if hit(a["text"], g.get("must_contain")):
                    matched.add(a["id"] or a["text"])
        leftover = [a for a in added if (a["id"] or a["text"]) not in matched]
        print("  [多抽候选] 未匹配任何预标事实（是否该记由人判）")
        if not leftover:
            print("    （无）")
        for a in leftover:
            print("    %s [%s] %s" % (a["id"], a["kind"], a["text"][:64]))
        print()

    print("=" * 78)
    print("汇总")
    print("=" * 78)
    n = max(1, tot["gold"])
    print("  预标事实 %d 条" % tot["gold"])
    print("    covered  已覆盖（有关键词命中）       ：%d  （%.1f%%）"
          % (tot["loose"], 100.0 * tot["loose"] / n))
    print("    clean    无污染覆盖（另要求事件性质） ：%d  （%.1f%%）"
          % (tot["strict"], 100.0 * tot["strict"] / n))
    print("    polluted 已覆盖但夹带泛化             ：%d" % tot["overshoot"])
    print("    missed   连关键词都没命中             ：%d" % (tot["gold"] - tot["loose"]))
    print("    ★ clean 是「无污染覆盖」，不等于一般召回率；")
    print("      关键词 + 禁词仍是**粗筛**，不是语义判定，必须人工复核。")
    print("  抽出记录 %d 条；处置：新增 %d / 隔离 %d / 提升 %d / 重复跳过 %d / 截断批 %d"
          % (tot.get("added", 0), disp["added"], disp["quarantined"],
             disp["promoted"], disp["skip"], disp["partial"]))
    print()
    print("  时间分层（分母只算该层预标事实，用 strict 优先项）：")
    for k in ("full", "month_day", "unknown", "none"):
        if k not in tstat:
            continue
        cnt, got, val, fmt, bad = tstat[k]
        if k == "none":
            print("    %-6s 共 %d，strict 命中 %d（不参与时间统计）" % (TIME_KIND_CN[k], cnt, got))
        else:
            print("    %-6s 共 %d，strict 命中 %d，**日期值正确 %d**，"
                  "仅格式对 %d，不符/漏落 %d"
                  % (TIME_KIND_CN[k], cnt, got, val, fmt, bad))
    if overshoots:
        print()
        print("  泛化明细：")
        for o in overshoots:
            print("    %s/%s 命中词=%s  %s" % (o["batch"], o["gold"], o["words"], o["text"][:50]))
    if misses:
        print()
        print("  漏抽明细：")
        for m in misses:
            print("    %s/%s  %s" % (m["batch"], m["gold"], m["fact"][:50]))

    # ★ kind 粗筛：稳定事实却带了具体 event_time。
    #   ⚠ **这只是弱指标，不能当类型错分的总数。**
    #   它只能抓到"带日期的那部分"；「上次用 AI 列过提纲」这种**日期未知但仍是
    #   某次经历**的记录，因为没有 event_time，会整体逃过这道筛。
    #   实测：M1a 粗筛命中 0 条，人工判却有 6 条错分（全部不带日期）。
    #   真正的 kind 统计必须人工逐条判「来源表达的适用范围」。
    kind_bad = []
    for b in runs.values():
        for a in b.get("added") or []:
            if a.get("kind") == "fact" and a.get("event_time"):
                kind_bad.append("%s/%s [%s] %s"
                                % (b["id"], a["id"], a["event_time"],
                                   (a.get("text") or "")[:40]))
    print()
    print("  [kind 粗筛] 稳定事实却带具体日期（可能把单次事件放进 facts）")
    if kind_bad:
        for x in kind_bad:
            print("    " + x)
    else:
        print("    （无）")

    out = EVAL / ("review_" + run_file.stem + ".json")
    out.write_text(json.dumps({"source": run_file.name, "totals": tot,
                               "dispositions": disp, "time": tstat,
                               "overshoots": overshoots, "misses": misses,
                               "kind_suspects": kind_bad},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("明细已写入", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
