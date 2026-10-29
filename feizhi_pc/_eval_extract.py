# -*- coding: utf-8 -*-
"""修正：把模型原始输出还原成「她实际会发出的文本」。

★ 这是 v1 评测器的严重缺陷：生产链路是
      generate_plan() → _parse_plan(raw) → ReplyPlan(messages[])
  模型**有时**按 plan 格式输出 JSON（含 messages/think_before_ms/typing_ms），
  有时直接输出纯文本。v1 把原始串直接交给裁判，于是大量"答案"其实是
  `{"messages":[{"text":"…","think_before_ms":650}],"media":null}` ——
  裁判在评 JSON 结构，判定全部失真。

本脚本离线重算（不重新调 API）：从 answers_*.json 里取原始 output，
按生产的解析规则还原成纯文本，重新生成 answers / blind 供评分。

用法:
    python _eval_extract.py
"""
from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path

EVAL = Path(r"<PROJECT_ROOT>\feizhi_pc\eval")


def extract_text(raw: str) -> tuple[str, bool]:
    """返回 (纯文本, 是否为 plan JSON)。"""
    s = raw or ""
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return s.strip(), False
    try:
        obj = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return s.strip(), False
    if not isinstance(obj, dict):
        return s.strip(), False
    msgs = obj.get("messages")
    if not isinstance(msgs, list):
        return s.strip(), False
    parts = []
    for x in msgs:
        if isinstance(x, dict) and x.get("text"):
            parts.append(str(x["text"]))
        elif isinstance(x, str):
            parts.append(x)
    text = "".join(parts).strip()
    return (text or s.strip()), True


def main() -> int:
    cands = [p for p in EVAL.glob("answers_*.json") if ".key." not in p.name]
    src = sorted(cands)[-1]
    doc = json.loads(src.read_text(encoding="utf-8"))
    answers = doc["answers"]

    n_plan = 0
    out = []
    for a in answers:
        if not a.get("ok"):
            out.append(a)
            continue
        text, was_plan = extract_text(a.get("output", ""))
        if was_plan:
            n_plan += 1
        rec = dict(a)
        rec["output_raw"] = a.get("output", "")
        rec["output"] = text
        rec["was_plan_json"] = was_plan
        out.append(rec)

    ok = [a for a in out if a.get("ok")]
    print("来源", src.name)
    print("总 %d 条，成功 %d 条，其中按 plan JSON 输出 %d 条（%.0f%%）"
          % (len(out), len(ok), n_plan, 100.0 * n_plan / max(1, len(ok))))

    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = EVAL / ("answers_fixed_%s.json" % stamp)
    dst.write_text(json.dumps({**{k: v for k, v in doc.items() if k != "answers"},
                              "extracted_from": src.name, "answers": out},
                             ensure_ascii=False, indent=2), encoding="utf-8")

    # 重新生成盲评
    rnd = random.Random(20261025)
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    blind_items, key = [], {}
    for rec in ok:
        if not rec.get("output"):
            continue
        bid = "".join(rnd.choice(alphabet) for _ in range(6))
        key[bid] = {"case_id": rec["case_id"], "mode": rec["mode"]}
        blind_items.append({"blind_id": bid, "case_id": rec["case_id"],
                            "question": rec["question"], "output": rec["output"]})
    rnd.shuffle(blind_items)
    bf = EVAL / ("blind_fixed_%s.json" % stamp)
    bf.write_text(json.dumps({"items": blind_items}, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    kf = EVAL / ("blind_fixed_%s.key.json" % stamp)
    kf.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")

    print("已修正 ->", dst.name)
    print("盲评   ->", bf.name, "（%d 条）" % len(blind_items))
    print()
    print("--- 抽样：修正前后的差异 ---")
    shown = 0
    for a in out:
        if a.get("was_plan_json") and shown < 3:
            shown += 1
            print()
            print("原始:", (a.get("output_raw") or "")[:120])
            print("还原:", (a.get("output") or "")[:120])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
