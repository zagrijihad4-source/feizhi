# -*- coding: utf-8 -*-
"""重复实验的合并与聚合。

子命令：
    python _eval_repeat.py merge       合并 run1/2/3 → 统一盲评文件（210 条）
    python _eval_repeat.py aggregate   读 judged_* 按 (case, mode) 汇总 3 次结果

聚合输出（每格 3 次）：
    fact:  yes/partial/no 的**次数**（例 "2/1/0"）
    viol:  出现禁止断言的次数
    不合成总分；另列逐题矩阵，便于人工复核分歧题。
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

EVAL = Path(r"<PROJECT_ROOT>\feizhi_pc\eval")
MODES = ("none", "truncate", "full_orig", "full_rerank", "topk8")


def _pick_run1() -> Path:
    """首轮结果（已 extract 的那份）。"""
    c = [p for p in EVAL.glob("answers_fixed_*.json") if ".key." not in p.name]
    return sorted(c)[-1]


def _pick_repeat() -> Path:
    c = [p for p in EVAL.glob("answers_repeat*_*.json") if ".key." not in p.name]
    return sorted(c)[-1]


def _extract(s: str) -> str:
    s = (s or "").strip()
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return s
    try:
        obj = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return s
    if not isinstance(obj, dict) or not isinstance(obj.get("messages"), list):
        return s
    parts = [str(x["text"]) for x in obj["messages"]
             if isinstance(x, dict) and x.get("text")]
    return "".join(parts).strip() or s


def cmd_merge() -> int:
    new_only = "--new-only" in sys.argv
    rp = json.loads(_pick_repeat().read_text(encoding="utf-8"))["answers"]

    merged: dict[tuple, dict] = {}
    if not new_only:
        r1 = json.loads(_pick_run1().read_text(encoding="utf-8"))["answers"]
        for a in r1:
            if not a.get("ok"):
                continue
            merged[(a["case_id"], a["mode"], 1)] = {
                "run": 1, "case_id": a["case_id"], "mode": a["mode"],
                "question": a["question"],
                "output": a.get("output") or _extract(a.get("output_raw", "")),
            }
    for a in rp:
        if not a.get("ok"):
            continue
        merged[(a["case_id"], a["mode"], a.get("run", 2))] = {
            "run": a.get("run", 2), "case_id": a["case_id"], "mode": a["mode"],
            "question": a["question"],
            "output": a.get("output") or _extract(a.get("output_raw", "")),
        }

    recs = [v for v in merged.values() if v["output"]]
    runs = sorted({v["run"] for v in recs})
    cases = sorted({v["case_id"] for v in recs})
    print("合并后 %d 条 | 轮次 %s | 用例 %d | 模式 %d"
          % (len(recs), runs, len(cases), len(MODES)), flush=True)

    # 完整性检查：每题每组应有 len(runs) 条
    need = len(cases) * len(MODES) * len(runs)
    if len(recs) != need:
        miss = defaultdict(int)
        for c in cases:
            for m in MODES:
                have = sum(1 for v in recs if v["case_id"] == c and v["mode"] == m)
                if have != len(runs):
                    miss[(c, m)] = have
        print("⚠ 不完整：应有 %d 条，实有 %d 条；缺的 (case,mode,现有次数)：" % (need, len(recs)))
        for (c, m), h in list(miss.items())[:12]:
            print("   %-9s %-12s %d/%d" % (c, m, h, len(runs)))

    rnd = random.Random(20261025)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    items, key = [], {}
    for v in recs:
        bid = "".join(rnd.choice(alphabet) for _ in range(6))
        key[bid] = {"case_id": v["case_id"], "mode": v["mode"], "run": v["run"]}
        items.append({"blind_id": bid, "case_id": v["case_id"], "output": v["output"]})
    rnd.shuffle(items)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    bf = EVAL / ("blind_repeat_%s.json" % stamp)
    bf.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    (EVAL / ("blind_repeat_%s.key.json" % stamp)).write_text(
        json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")
    print("盲评 ->", bf.name, "(%d 条)" % len(items))
    print("下一步：python _eval_judge.py %s" % bf.name)
    return 0


def _load_judged(jf: Path, default_run: int = 1) -> list[dict]:
    kf = EVAL / (jf.stem.replace("judged", "blind") + ".key.json")
    J = json.loads(jf.read_text(encoding="utf-8"))
    K = json.loads(kf.read_text(encoding="utf-8"))
    out = []
    for r in J:
        if r.get("error"):
            continue
        meta = K.get(r["blind_id"])
        if not meta:
            continue
        out.append({"case_id": meta["case_id"], "mode": meta["mode"],
                    "run": meta.get("run", default_run),
                    "fact_correct": r.get("fact_correct"),
                    "forbidden_violated": r.get("forbidden_violated") or [],
                    "reason": r.get("reason", "")})
    return out


def cmd_aggregate() -> int:
    """合并 run1（judged_fixed_*）与 run2/3（judged_repeat_*）。"""
    parts: list[dict] = []
    f1 = [p for p in EVAL.glob("judged_fixed_*.json") if ".key." not in p.name]
    if f1:
        rows = _load_judged(sorted(f1)[-1], default_run=1)
        print("run1 来源 %s：%d 条" % (sorted(f1)[-1].name, len(rows)))
        parts += rows
    fr = [p for p in EVAL.glob("judged_repeat_*.json") if ".key." not in p.name]
    if not fr:
        print("缺 judged_repeat_*.json，先跑 _eval_judge.py")
        return 1
    rows2 = _load_judged(sorted(fr)[-1], default_run=2)
    print("run2/3 来源 %s：%d 条" % (sorted(fr)[-1].name, len(rows2)))
    parts += rows2

    per = defaultdict(lambda: {"yes": 0, "partial": 0, "no": 0, "viol": 0, "n": 0})
    runs_seen = defaultdict(set)
    for r in parts:
        k = (r["case_id"], r["mode"])
        d = per[k]
        d["n"] += 1
        runs_seen[k].add(r["run"])
        fc = r.get("fact_correct")
        if fc in ("yes", "partial", "no"):
            d[fc] += 1
        if r.get("forbidden_violated"):
            d["viol"] += 1

    cases = sorted({k[0] for k in per})
    print()
    print("=== 逐题 × 模式（每格 yes/partial/no 次数，v=违禁次数）===")
    print("%-9s %s" % ("case", " ".join("%-14s" % m[:12] for m in MODES)))
    for cid in cases:
        line = "%-9s" % cid
        for m in MODES:
            d = per.get((cid, m))
            if not d or not d["n"]:
                line += " %-14s" % "-"
                continue
            line += " %-14s" % ("%d/%d/%d v%d" % (d["yes"], d["partial"], d["no"], d["viol"]))
        print(line)

    print()
    print("=== 模式总计 ===")
    print("%-12s %5s %5s %5s %5s %6s %6s" % ("mode", "yes", "part", "no", "viol", "n", "满次"))
    for m in MODES:
        y = sum(per[(c, m)]["yes"] for c in cases)
        p = sum(per[(c, m)]["partial"] for c in cases)
        n = sum(per[(c, m)]["no"] for c in cases)
        v = sum(per[(c, m)]["viol"] for c in cases)
        cnt = sum(per[(c, m)]["n"] for c in cases)
        full = sum(1 for c in cases if len(runs_seen[(c, m)]) >= 3)
        print("%-12s %5d %5d %5d %5d %6d %5d/14" % (m, y, p, n, v, cnt, full))

    print()
    print("=== 组内稳定性（同一输入 3 次判定是否一致）===")
    unstable = {m: 0 for m in MODES}
    for cid in cases:
        for m in MODES:
            d = per.get((cid, m))
            if not d or d["n"] < 2:
                continue
            if max(d["yes"], d["partial"], d["no"]) != d["n"]:
                unstable[m] += 1
    for m in MODES:
        print("  %-12s %2d / %d 题存在组内不一致" % (m, unstable[m], len(cases)))

    out = EVAL / ("repeat_total_%s.json" % time.strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps(
        {"per_case_mode": {"%s|%s" % k: v for k, v in per.items()},
         "runs_seen": {"%s|%s" % k: sorted(v) for k, v in runs_seen.items()},
         "unstable": unstable},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("汇总 ->", out.name)
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "merge"
    raise SystemExit(cmd_merge() if cmd == "merge" else cmd_aggregate())
