# -*- coding: utf-8 -*-
"""人工复核的盲评导出（gen-02 / gen-05 / gen-07 全部有效回答）。

按 YG 要求：
  * **三题全部有效回答**都进复核（不是只看差异句），避免各组受审范围不一致
  * 匿名混排，隐藏组名与旧标签
  * 生成失败单列，不按内容答错处理
  * 保留机器标签供事后对照（存在单独 key 里，复核时别看）
"""
from __future__ import annotations

import json
import random
from pathlib import Path

EVAL = Path(r"<PROJECT_ROOT>\feizhi_pc\eval")
TARGETS = ("gen-02", "gen-05", "gen-07")


def main() -> int:
    cases = {c["id"]: c for c in json.loads((EVAL / "cases.json").read_text(encoding="utf-8"))["cases"]}
    cands = sorted(p for p in EVAL.glob("answers_rerun3_*.json") if ".key." not in p.name)

    merged: dict[tuple, dict] = {}
    fails: list[dict] = []
    for f in cands:
        d = json.loads(f.read_text(encoding="utf-8"))
        for a in d["answers"]:
            cid = a["case_id"]
            if cid not in TARGETS:
                continue
            if a.get("question") != cases[cid]["question"]:
                continue                      # 旧问句版本，丢弃
            k = (cid, a["mode"], a.get("run", 1))
            if not a.get("ok"):
                fails.append({"case_id": cid, "mode": a["mode"],
                              "run": a.get("run", 1),
                              "error": (a.get("error") or "")[:80]})
                continue
            merged[k] = a

    rows = []
    for (cid, mode, run), a in merged.items():
        rows.append({"case_id": cid, "mode": mode, "run": run,
                     "question": cases[cid]["question"],
                     "points": cases[cid]["answer_points"],
                     "forbidden": cases[cid]["forbidden"],
                     "output": a.get("output") or "",
                     "machine_guard": a.get("guard_state")})
    rnd = random.Random(20261025)
    rnd.shuffle(rows)

    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    items, key = [], {}
    for r in rows:
        bid = "".join(rnd.choice(alphabet) for _ in range(5))
        while bid in key:
            bid = "".join(rnd.choice(alphabet) for _ in range(5))
        key[bid] = {"case_id": r["case_id"], "mode": r["mode"], "run": r["run"],
                    "machine_guard": r["machine_guard"]}
        items.append({"blind_id": bid, "case_id": r["case_id"],
                      "question": r["question"], "points": r["points"],
                      "forbidden": r["forbidden"], "output": r["output"]})

    out = EVAL / "review_batch.json"
    out.write_text(json.dumps({"items": items, "fails": fails,
                               "note": "按 blind_id 匿名；judgment 由人工填写"},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    (EVAL / "review_batch.key.json").write_text(
        json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")

    print("导出 %d 条有效回答（%d 组失败单列）" % (len(items), len(fails)))
    by = {}
    for r in rows:
        by[r["case_id"]] = by.get(r["case_id"], 0) + 1
    print("按题：", by)
    print("失败：", fails)
    print("盲评 ->", out.name)
    print("（key 单独存放，复核时不要看）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
