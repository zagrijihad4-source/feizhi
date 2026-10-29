# -*- coding: utf-8 -*-
"""按 kind 标签 v2 重评已保存的输出（**0 次模型调用**）。

只做离线重评：从 `stage2_with_source.json` 里已存的 raw 解析 labels，
分别按 v1 / v2 两套冻结标签算准确率，用于独立复算交接报告的数字。

用法: python _reval_kind_v2.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
EVAL = HERE / "eval"
RUN = EVAL / "stage2_with_source.json"
V1 = EVAL / "gold_kind_v1.json"
V2 = EVAL / "gold_kind_v2.json"
OUT = EVAL / "reval_kind_v2.json"
BJ = timezone(timedelta(hours=8))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def parse_labels(raw: str):
    i, j = raw.find("{"), raw.rfind("}")
    if i < 0 or j <= i:
        return None
    txt = raw[i:j + 1]
    try:
        return json.loads(txt).get("labels") or []
    except Exception:  # noqa: BLE001
        return None


def load_ref(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for r in d["rows"]:
        # v1 用 ref=="ambiguous" 表示歧义；v2 用 status
        status = r.get("status") or ("ambiguous" if r.get("ref") == "ambiguous" else "decided")
        out[r["cid"]] = {"ref": r["ref"], "status": status}
    return out


def score(labels, ref: dict, bid: str) -> dict:
    lab = {"%s/%s" % (bid, str(x.get("cid"))): x.get("kind") for x in labels}
    ok = bad = 0
    e2f = f2e = 0
    miss = []
    wrong = []
    for cid, r in ref.items():
        if not cid.startswith(bid + "/"):
            continue
        if r["status"] != "decided":
            continue
        got = lab.get(cid)
        if got is None:
            miss.append(cid)
            continue
        if got == r["ref"]:
            ok += 1
        else:
            bad += 1
            wrong.append(cid)
            if r["ref"] == "event" and got == "fact":
                e2f += 1
            elif r["ref"] == "fact" and got == "event":
                f2e += 1
    return {"ok": ok, "bad": bad, "miss": miss, "wrong": wrong,
            "event_to_fact": e2f, "fact_to_event": f2e}


def main() -> int:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    r1, r2 = load_ref(V1), load_ref(V2)
    print("复算：只读已保存的 raw，不调用模型")
    print("v2 标签 sha256：", hashlib.sha256(V2.read_bytes()).hexdigest()[:16])
    print()

    out = {"_meta": {"ran_at": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"),
                     "source": RUN.name,
                     "v2_sha256": hashlib.sha256(V2.read_bytes()).hexdigest(),
                     "model_calls": 0}, "arms": {}}

    hdr = "%-4s %-4s | %-14s | %-14s" % ("臂", "轮", "v1 (82 可判)", "v2 (83 可判)")
    print(hdr)
    print("-" * len(hdr))
    for arm in ("A", "B"):
        rows = run["arms"].get(arm) or []
        out["arms"][arm] = []
        for r in rows:
            agg = {"v1": {"ok": 0, "bad": 0, "e2f": 0, "f2e": 0, "wrong": []},
                   "v2": {"ok": 0, "bad": 0, "e2f": 0, "f2e": 0, "wrong": []}}
            for b in r["batches"]:
                labels = parse_labels(b["raw"])
                if labels is None:
                    print("  [无法解析] %s 轮%s 批%s" % (arm, r["round"], b["id"]))
                    continue
                for tag, ref in (("v1", r1), ("v2", r2)):
                    s = score(labels, ref, b["id"])
                    agg[tag]["ok"] += s["ok"]
                    agg[tag]["bad"] += s["bad"]
                    agg[tag]["e2f"] += s["event_to_fact"]
                    agg[tag]["f2e"] += s["fact_to_event"]
                    agg[tag]["wrong"] += s["wrong"]
            line = {}
            for tag in ("v1", "v2"):
                a = agg[tag]
                scored = a["ok"] + a["bad"]
                line[tag] = {"ok": a["ok"], "scored": scored,
                             "acc": round(100.0 * a["ok"] / scored, 2) if scored else 0.0,
                             "event_to_fact": a["e2f"], "fact_to_event": a["f2e"],
                             "wrong": sorted(a["wrong"])}
            out["arms"][arm].append({"round": r["round"], **line})
            print("%-4s %-4s | %2d/%2d = %5.2f%% | %2d/%2d = %5.2f%%"
                  % (arm, r["round"],
                     line["v1"]["ok"], line["v1"]["scored"], line["v1"]["acc"],
                     line["v2"]["ok"], line["v2"]["scored"], line["v2"]["acc"]))

    print()
    for tag, key in (("v1", "v1_avg"), ("v2", "v2_avg")):
        for arm in ("A", "B"):
            rs = out["arms"][arm]
            # ★ 加权口径：总正确 / 总题数。轮次算术平均会因舍入产生 0.01pp 偏差，
            #   与交接报告用的口径对齐后才能逐位对比。
            ok_sum = sum(x[tag]["ok"] for x in rs)
            sc_sum = sum(x[tag]["scored"] for x in rs)
            avg = round(100.0 * ok_sum / sc_sum, 2) if sc_sum else 0.0
            out["_meta"][key] = out["_meta"].get(key, {})
            out["_meta"][key][arm] = avg
            out["_meta"].setdefault("weighted_detail", {}).setdefault(tag, {})[arm] = {
                "ok": ok_sum, "scored": sc_sum, "acc": avg}
    print("按 v1 加权平均：A %.2f%%  B %.2f%%"
          % (out["_meta"]["v1_avg"]["A"], out["_meta"]["v1_avg"]["B"]))
    print("按 v2 加权平均：A %.2f%%  B %.2f%%"
          % (out["_meta"]["v2_avg"]["A"], out["_meta"]["v2_avg"]["B"]))
    print()
    print("v2 口径下仍错的项（各轮并集）：")
    for arm in ("A", "B"):
        w = sorted({x for r in out["arms"][arm] for x in r["v2"]["wrong"]})
        print("  %s: %s" % (arm, w))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("已写入", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
