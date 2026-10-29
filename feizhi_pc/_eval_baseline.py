# -*- coding: utf-8 -*-
"""第 0 步（修正版 v3）：记忆通道证据基线。

v3 相对 v2 的修正：
  1. 证据结构改为「按答案要点分组」(evidence: [{need, mem_any_of}])。
     v2 把不同事实塞进同一个任选组，任一条单独存在就算整体通过 —— 完整率会虚高。
  2. 新增 `none` 组：不注入长期记忆、保留相同历史与人格。
     用来回答「在原始历史完整保留时，长期记忆模块到底提供了多少额外证据」。
  3. 输出标签统一为「**记忆通道**证据完整率」——
     历史通道目前只做关键词粗筛，不参与完整率计算。
  4. 不再使用"收益天花板"之类的因果表述：字符占比只约束"能省多少输入"，
     不约束"对回答质量影响多大"。

★ 本脚本**不生成回答**。它只回答"这条 remember 通道有没有覆盖该要点"。
  回答质量必须另跑（_eval_answer.py）。

用法:
    python _eval_baseline.py
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

EVAL = Path(r"<PROJECT_ROOT>\feizhi_pc\eval")
SNAP = EVAL / "snapshots" / "20261025-132233"
CASES = EVAL / "cases.json"
PEER = "<WXID_FRIEND_A>"

CERT_W = {"high": 1.0, "mid": 0.8, "low": 0.6}
DEFAULT_CERT = 0.9
TODAY = datetime(2026, 10, 25)

_CJK = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]+")

TEMPLATE = (
    "【你真正记得的事 —— 这不是设定，是你自己攒下来的记忆】\n"
    "{items}\n"
    "用法：像真人一样自然地想起来就用，别一次全倒出来，也别复述成清单；"
    "他提到相关的事时你自然会接上。没把握的细节不要编，宁可说记不清。"
)


def bigrams(s: str) -> set[str]:
    s = _CJK.sub("", s or "")
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else ({s} if s else set())


def coverage(query: str, text: str) -> float:
    q, t = bigrams(query), bigrams(text)
    if not q or not t:
        return 0.0
    return len(q & t) / len(q)


def recency(added: str) -> float:
    try:
        d = datetime.strptime(added, "%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return 0.5
    return 1.0 / (1.0 + max(0, (TODAY - d).days) / 30.0)


def load_items() -> list[dict]:
    d = json.loads((SNAP / "feizhi_memory.json").read_text(encoding="utf-8"))
    out = []
    for kind, key, pfx in (("fact", "facts", "F"), ("event", "events", "E")):
        for idx, x in enumerate(d.get(key) or []):
            out.append({
                "tag": "%s%02d" % (pfx, idx), "kind": kind,
                "text": x.get("text", ""), "added": x.get("added", ""),
                "certainty": x.get("certainty", ""),
            })
    return out


def line_of(it: dict) -> str:
    hint = {"mid": "（记得是这样，可能记岔）",
            "low": "（好像是这样，不太确定）"}.get(it["certainty"], "")
    type_tag = "［经过］" if it["kind"] == "event" else ""
    return "- " + type_tag + it["text"] + hint


def score(it: dict, query: str) -> float:
    return (1.0 * coverage(query, it["text"])
            + 0.3 * recency(it.get("created") or it.get("added") or "")
            + 0.2 * CERT_W.get(it["certainty"], DEFAULT_CERT))


def select(mode: str, items: list[dict], query: str) -> list[dict]:
    if mode == "none":
        return []
    facts = [x for x in items if x["kind"] == "fact"]
    events = [x for x in items if x["kind"] == "event"]
    if mode == "truncate":
        return facts[-30:] + events[-12:]
    if mode == "full_orig":
        return facts + events
    ranked = sorted(items, key=lambda x: (-score(x, query), x["tag"]))
    if mode == "full_rerank":
        return ranked
    if mode == "topk8":
        return ranked[:8]
    raise ValueError(mode)


def render(items: list[dict]) -> str:
    if not items:
        return ""                     # none：记忆段完全不注入
    return TEMPLATE.format(items="\n".join(line_of(x) for x in items))


def load_history() -> str:
    con = sqlite3.connect(str(SNAP / "context.sqlite3"))
    rows = con.execute(
        "SELECT role, text FROM messages WHERE peer_wxid=? ORDER BY id",
        (PEER,)).fetchall()
    con.close()
    # 注意：与生产一致，**不渲染时间戳**
    return "\n".join("%s：%s" % ("<OWNER>" if r == "user" else "绯栀", t) for r, t in rows)


MODES = ("none", "truncate", "full_orig", "full_rerank", "topk8")


def evidence_state(case: dict, tags: set[str]) -> dict:
    """按答案要点逐条检查记忆通道是否覆盖。"""
    needs = case.get("evidence") or []
    missing = []
    for n in needs:
        cands = n.get("mem_any_of") or []
        if cands and not (set(cands) & tags):
            missing.append(n["need"])
    return {"ok": not missing, "missing": missing, "needs": len(needs)}


def main() -> int:
    items = load_items()
    doc = json.loads(CASES.read_text(encoding="utf-8"))
    cases = doc["cases"]
    hist = load_history()
    dev = [c for c in cases if c["split"] == "dev"]

    print("记忆 %d 条  |  历史原文 %d 字符（未超 20000 预算；与当前生产一致，不含时间戳）"
          % (len(items), len(hist)))
    print("用例 dev %d 条（holdout 未遍历）" % len(dev))
    print()

    print("=== 体积（统一模板）===")
    for mode in MODES:
        sel = select(mode, items, "")
        body = render(sel)
        print("  %-12s 条数 %3d   记忆段 %5d 字符   记忆+历史 %5d"
              % (mode, len(sel), len(body), len(body) + len(hist)))
    print("  说明：以上均未含人格段(7441)与其他输入，**不是**完整生产 prompt；")
    print("        字符占比只说明「单独缩减记忆段能省多少输入」，不代表质量影响大小。")

    print()
    print("=== 记忆通道证据完整率（按答案要点逐条检查；历史通道未参与计算）===")
    rows = []
    for c in dev:
        rec = {"id": c["id"], "category": c["category"], "modes": {}}
        kws = c.get("hist_probe_keywords") or []
        probe = [k for k in kws if k in hist]
        line = "%-9s %-8s 历史粗筛:%-6s" % (
            c["id"], c["category"],
            ("命中" if probe else ("无词表" if not kws else "未命中")))
        for mode in MODES:
            sel = select(mode, items, c["question"])
            body = render(sel)
            st = evidence_state(c, {x["tag"] for x in sel})
            rec["modes"][mode] = {"count": len(sel), "chars": len(body), **st}
            mark = "OK" if st["ok"] else ("缺%d" % len(st["missing"]))
            line += " | %s:%s" % (mode[:6], mark)
        rows.append(rec)
        print(line)

    print()
    need_cases = [c for c in dev if (c.get("evidence") or [])]
    print("=== 汇总：有证据要点的 %d 条（%d 条 evidence=[] 不计入）==="
          % (len(need_cases), len(dev) - len(need_cases)))
    by_id = {r["id"]: r for r in rows}
    for mode in MODES:
        ok = sum(1 for c in need_cases if by_id[c["id"]]["modes"][mode]["ok"])
        print("  %-12s %2d/%2d" % (mode, ok, len(need_cases)))

    out = EVAL / ("baseline3_" + time.strftime("%Y%m%d-%H%M%S") + ".json")
    out.write_text(json.dumps({
        "snapshot": SNAP.name, "version": "v3",
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ranker": "v0: bigram_coverage*1.0 + recency*0.3 + certainty*0.2",
        "template": "统一外层模板；各模式只差条目集合/顺序；none 不注入记忆段",
        "history_chars": len(hist),
        "history_has_timestamp": False,
        "holdout_visited": False,
        "metric": "记忆通道证据完整率（按答案要点逐条）",
        "results": rows,
        "notice": "证据完整率仅用于定位；判定按 answer_points / forbidden，需另跑生成",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("明细 ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
