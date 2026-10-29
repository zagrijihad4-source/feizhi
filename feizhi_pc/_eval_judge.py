# -*- coding: utf-8 -*-
"""第 1 步评分：对盲评文件逐条判定，三个维度分开记，**不合成总分**。

裁判模型：`claude-sonnet-4-6`（与生成用的 deepseek 不同厂商，减少自评偏置）。

三个维度（按 YG 要求拆开）：
    fact_correct       yes / partial / no   —— 是否准确表达「必须包含的事实」
    forbidden_violated [str]                —— 违反了哪些「禁止断言」（语义层面）
    approach_ok        yes / no / na        —— 无答案/需澄清时是否恰当承认或反问

评分时只读 `blind_*.json`（不含模式），聚合时才打开 `blind_*.key.json`。

用法:
    python _eval_judge.py            # 用最新 blind 文件
    python _eval_judge.py <blind.json>
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

EVAL = Path(r"<PROJECT_ROOT>\feizhi_pc\eval")
CASES = EVAL / "cases.json"
ENV_FILE = Path(r"D:\Hermes\.env")

BASE = "https://synapse-ai.uk/v1"
KEY_ENV = "SYNAPSE_CLAUDE_API_KEY"
MODEL = "claude-sonnet-4-6"
TIMEOUT = 120

SYSTEM = (
    "你是严格的答案评分员。只按给定标准判定，**不要因为语气、长度、修辞、"
    "角色扮演风格加减分**。输出必须是 JSON。"
)

PROMPT = """【问题】
{question}

【必须包含的事实】
{points}

【禁止出现的断言】
{forbidden}

【允许的行为】
{allowed}

【待评回答】
{output}

请判定并输出 JSON（不要代码块、不要解释额外文字）：
{{
  "fact_correct": "yes" | "partial" | "no",
  "forbidden_violated": ["原样写出违反了哪一条，未违反则为空数组"],
  "approach_ok": "yes" | "no" | "na",
  "reason": "一句话，指出依据"
}}

判定口径：
- fact_correct：是否准确表达了「必须包含的事实」。缺失关键事实或说错 = no；
  只说对了一部分 = partial；全部说对 = yes。**不要因为多说了无关内容就降级。**
- forbidden_violated：是否在**语义层面**出现了「禁止出现的断言」中的任何一条。
- approach_ok：当「必须包含的事实」为空（即问题无可靠答案）时，
  回答是否恰当承认不知道/记不清/反问；有明确答案时填 "na"。"""


def load_key() -> str:
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith(KEY_ENV + "="):
            return line.split("=", 1)[1].strip()
    return ""


def judge(item: dict, spec: dict, key: str) -> dict:
    # question 以用例表为准：盲评文件不一定带它（merge 生成的那份就不带）
    prompt = PROMPT.format(
        question=spec.get("question") or item.get("question") or "",
        points="；".join(spec.get("answer_points") or []) or "（无，本题无可靠答案）",
        forbidden="；".join(spec.get("forbidden") or []) or "（无）",
        allowed="；".join(spec.get("allowed") or []) or "（无）",
        output=item["output"],
    )
    t0 = time.time()
    last = ""
    for attempt in range(3):
        try:
            r = requests.post(
                BASE + "/chat/completions",
                headers={"Authorization": "Bearer " + key,
                         "Content-Type": "application/json"},
                json={"model": MODEL, "max_tokens": 400, "temperature": 0,
                      "messages": [{"role": "system", "content": SYSTEM},
                                   {"role": "user", "content": prompt}]},
                timeout=TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            last = "%s %s" % (type(exc).__name__, exc)
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code != 200:
            last = "HTTP %s %s" % (r.status_code, r.text[:160])
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2.0 * (attempt + 1))
                continue
            return {"error": last}
        txt = r.json()["choices"][0]["message"].get("content") or ""
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            last = "no json: " + txt[:160]
            time.sleep(0.8)
            continue
        try:
            obj = json.loads(m.group(0))
        except Exception as exc:  # noqa: BLE001
            last = "bad json: %s %s" % (exc, txt[:120])
            time.sleep(0.8)
            continue
        obj["latency_s"] = round(time.time() - t0, 2)
        return obj
    return {"error": last or "unknown"}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1].endswith(".json"):
        blind = Path(sys.argv[1])
    else:
        cands = [p for p in EVAL.glob("blind_*.json") if ".key." not in p.name]
        blind = sorted(cands)[-1]
    keyf = blind.with_suffix(".key.json")
    items = json.loads(blind.read_text(encoding="utf-8"))["items"]
    cases = {c["id"]: c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"]}
    key = load_key()
    if not key:
        print("缺 %s，无法评分" % KEY_ENV)
        return 1

    jf = blind.with_name(blind.stem.replace("blind", "judged") + ".json")

    # --fill：只补评上次失败的条目，与已完成结果合并
    prev_ok: list[dict] = []
    if "--fill" in sys.argv and jf.exists():
        prev = json.loads(jf.read_text(encoding="utf-8"))
        prev_ok = [r for r in prev if not r.get("error")]
        done = {r["blind_id"] for r in prev_ok}
        todo = [it for it in items if it["blind_id"] not in done]
        print("补评：已完成 %d 条，待补 %d 条" % (len(done), len(todo)), flush=True)
        items = todo

    print("盲评文件 %s（本次评 %d 条）" % (blind.name, len(items)), flush=True)
    out = []
    for i, it in enumerate(items, 1):
        spec = cases[it["case_id"]]
        res = judge(it, spec, key)
        out.append({"blind_id": it["blind_id"], "case_id": it["case_id"],
                    "question": spec.get("question") or it.get("question", ""),
                    "output": it["output"], **res})
        flag = "ERR" if res.get("error") else res.get("fact_correct", "?")
        print("[%2d/%d] %-9s %-6s %s" % (i, len(items), it["case_id"], flag,
                                         (res.get("reason") or res.get("error") or "")[:60]),
              flush=True)

    if prev_ok:
        merged = {r["blind_id"]: r for r in prev_ok}
        for r in out:
            merged[r["blind_id"]] = r
        out = list(merged.values())
        n_ok = sum(1 for r in out if not r.get("error"))
        print("合并后 %d 条，其中成功 %d 条" % (len(out), n_ok), flush=True)

    jf.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # 聚合（此时才读 key）
    kmap = json.loads(keyf.read_text(encoding="utf-8"))
    agg: dict[str, dict] = {}
    for r in out:
        if r.get("error"):
            continue
        mode = kmap[r["blind_id"]]["mode"]
        a = agg.setdefault(mode, {"n": 0, "yes": 0, "partial": 0, "no": 0,
                                  "viol": 0, "appr_ok": 0, "appr_tot": 0})
        a["n"] += 1
        fc = r.get("fact_correct", "")
        if fc in ("yes", "partial", "no"):
            a[fc] += 1
        if r.get("forbidden_violated"):
            a["viol"] += 1
        if r.get("approach_ok") in ("yes", "no"):
            a["appr_tot"] += 1
            if r["approach_ok"] == "yes":
                a["appr_ok"] += 1

    print()
    print("=== 按模式聚合（三维度分开，不合成总分）===")
    print("%-12s %4s %5s %7s %5s %8s %s" % ("mode", "n", "yes", "partial", "no", "viol", "approach"))
    for mode in ("none", "truncate", "full_orig", "full_rerank", "topk8"):
        a = agg.get(mode)
        if not a:
            continue
        appr = ("%d/%d" % (a["appr_ok"], a["appr_tot"])) if a["appr_tot"] else "-"
        print("%-12s %4d %5d %7d %5d %8d %s"
              % (mode, a["n"], a["yes"], a["partial"], a["no"], a["viol"], appr))

    summary = blind.with_name(blind.stem.replace("blind", "summary") + ".json")
    summary.write_text(json.dumps({"by_mode": agg, "judgments": len(out)},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("逐条判定 ->", jf)
    print("聚合 ->", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
