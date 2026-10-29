# -*- coding: utf-8 -*-
"""第 1 步：真实回答对照（5 组 × dev 14 题 = 70 个回答）。

设计要点：
  * **只改变记忆段**。人格段、历史原文、PERSONA_ANCHOR、模型、温度、
    max_tokens、提问时刻全部固定；system prompt 直接复用生产的
    `FeizhiReplyGenerator._build_system`，不另造一套。
  * 自己发 HTTP 而不是走 llm.chat —— 为了记录 **usage 与 finish_reason**。
  * 输出两份：`answers_*.json`（含模式）与 `blind_*.json`（匿名打乱，供评分）。
    盲评文件不含模式，key 单独存，避免评分者被组名影响。

五组：
    none         不注入记忆段（下界锚点）
    truncate     现状 facts[-30:] + events[-12:]
    full_orig    全量、原顺序
    full_rerank  全量、按排序器 v0 重排
    topk8        同排序取前 8

用法:
    python _eval_answer.py --dry          # 只跑 1 题 5 组，验证链路
    python _eval_answer.py                # 全量 70 个
    python _eval_answer.py --cases syn-01,upd-02
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

FEIZHI = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(FEIZHI))

import outguard  # noqa: E402  对外输出检查（评测必须与生产一致）

EVAL = FEIZHI / "eval"
SNAP = EVAL / "snapshots" / "20261025-132233"
CASES = EVAL / "cases.json"
CONFIG = FEIZHI / "llm_config.json"

# 与生产一致
MAX_TOKENS = 900
TEMPERATURE = 0.85
TIMEOUT = 180

MODES = ("none", "truncate", "full_orig", "full_rerank", "topk8")


# ---------------- 记忆渲染（与 _eval_baseline.py 保持一致） ----------------
_CJK = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]+")
CERT_W = {"high": 1.0, "mid": 0.8, "low": 0.6}
DEFAULT_CERT = 0.9
TODAY = __import__("datetime").datetime(2026, 10, 25)

TEMPLATE = (
    "【你真正记得的事 —— 这不是设定，是你自己攒下来的记忆】\n"
    "{items}\n"
    "用法：像真人一样自然地想起来就用，别一次全倒出来，也别复述成清单；"
    "他提到相关的事时你自然会接上。没把握的细节不要编，宁可说记不清。"
)


def bigrams(s: str) -> set[str]:
    s = _CJK.sub("", s or "")
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else ({s} if s else set())


def coverage(q: str, t: str) -> float:
    a, b = bigrams(q), bigrams(t)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a)


def recency(added: str) -> float:
    try:
        from datetime import datetime
        d = datetime.strptime(added, "%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return 0.5
    return 1.0 / (1.0 + max(0, (TODAY - d).days) / 30.0)


def load_items() -> list[dict]:
    d = json.loads((SNAP / "feizhi_memory.json").read_text(encoding="utf-8"))
    out = []
    for kind, key, pfx in (("fact", "facts", "F"), ("event", "events", "E")):
        for idx, x in enumerate(d.get(key) or []):
            out.append({"tag": "%s%02d" % (pfx, idx), "kind": kind,
                        "text": x.get("text", ""), "added": x.get("added", ""),
                        "certainty": x.get("certainty", "")})
    return out


def line_of(it: dict) -> str:
    hint = {"mid": "（记得是这样，可能记岔）",
            "low": "（好像是这样，不太确定）"}.get(it["certainty"], "")
    return "- " + ("［经过］" if it["kind"] == "event" else "") + it["text"] + hint


def score(it: dict, q: str) -> float:
    return (coverage(q, it["text"]) + 0.3 * recency(it.get("created") or it.get("added") or "")
            + 0.2 * CERT_W.get(it["certainty"], DEFAULT_CERT))


def select(mode: str, items: list[dict], q: str) -> list[dict]:
    if mode == "none":
        return []
    facts = [x for x in items if x["kind"] == "fact"]
    events = [x for x in items if x["kind"] == "event"]
    if mode == "truncate":
        return facts[-30:] + events[-12:]
    if mode == "full_orig":
        return facts + events
    ranked = sorted(items, key=lambda x: (-score(x, q), x["tag"]))
    if mode == "full_rerank":
        return ranked
    if mode == "topk8":
        return ranked[:8]
    raise ValueError(mode)


def memory_block(mode: str, items: list[dict], q: str) -> str:
    sel = select(mode, items, q)
    if not sel:
        return ""
    return TEMPLATE.format(items="\n".join(line_of(x) for x in sel)) + "\n"


def load_history() -> str:
    import sqlite3
    con = sqlite3.connect(str(SNAP / "context.sqlite3"))
    rows = con.execute(
        "SELECT role, text FROM messages WHERE peer_wxid=? ORDER BY id",
        ("<WXID_FRIEND_A>",)).fetchall()
    con.close()
    return "\n".join("%s：%s" % ("<OWNER>" if r == "user" else "绯栀", t) for r, t in rows)


# ---------------- 模型调用（自己发，为了 usage） ----------------
def api_spec() -> tuple[str, str, str]:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    p = cfg["providers"]["deepseek"]
    return p["base_url"].rstrip("/"), p["api_key"], p.get("model", "deepseek-chat")


def call_model(system: str, user: str) -> dict:
    base, key, model = api_spec()
    t0 = time.time()
    try:
        r = requests.post(
            base + "/chat/completions",
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"},
            json={"model": model,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}],
                  "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE},
            timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "%s %s" % (type(exc).__name__, exc),
                "latency_s": round(time.time() - t0, 2)}
    dt = time.time() - t0
    if r.status_code != 200:
        return {"ok": False, "error": "HTTP %s %s" % (r.status_code, r.text[:200]),
                "latency_s": round(dt, 2)}
    d = r.json()
    ch = d["choices"][0]
    return {"ok": True, "output": (ch["message"].get("content") or "").strip(),
            "finish_reason": ch.get("finish_reason"),
            "usage": d.get("usage", {}), "latency_s": round(dt, 2)}


def parse_plan_text(raw: str) -> tuple[str, str]:
    """按生产规则把输出还原成「她实际会发出的文本」。

    返回 (文本, 状态)，状态 ∈ {"text", "plan", "plan_broken"}。
    模型有时输出 plan JSON（含 messages/think_before_ms），有时输出纯文本；
    生产用 _parse_plan 处理，这里用等价的最小实现，并把**解析失败单独计数**。
    """
    s = (raw or "").strip()
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return s, "text"
    try:
        obj = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return s, "text"
    if not isinstance(obj, dict) or not isinstance(obj.get("messages"), list):
        return s, "text"
    parts = []
    for x in obj["messages"]:
        if isinstance(x, dict) and x.get("text"):
            parts.append(str(x["text"]))
        elif isinstance(x, str):
            parts.append(x)
    if not parts:
        return s, "plan_broken"
    return "".join(parts).strip(), "plan"


def main() -> int:
    import autoreply

    args = sys.argv[1:]
    dry = "--dry" in args
    fill = "--fill" in args
    shuffle = "--shuffle" in args
    extra_runs = 0
    rerun = 0
    only = None
    for a in args:
        if a.startswith("--cases="):
            only = set(a.split("=", 1)[1].split(","))
        if a.startswith("--runs="):
            extra_runs = int(a.split("=", 1)[1])
        if a.startswith("--rerun="):
            rerun = int(a.split("=", 1)[1])

    items = load_items()
    cases = [c for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"]
             if c["split"] == "dev" and (only is None or c["id"] in only)]
    case_by_id = {c["id"]: c for c in cases}
    hist = load_history()

    # ---- 补跑模式：只重做上一轮网络失败的组合 ----
    prev_file = None
    prev = None
    todo_pairs = None
    if fill:
        prev_file = sorted(EVAL.glob("answers_*.json"))[-1]
        prev = json.loads(prev_file.read_text(encoding="utf-8"))
        failed = [(a["case_id"], a["mode"]) for a in prev["answers"] if not a.get("ok")]
        todo_pairs = set(failed)
        cases = [c for c in cases if any(cid == c["id"] for cid, _ in failed)]
        print("补跑 %d 个失败组合，来源 %s" % (len(failed), prev_file.name), flush=True)
    if dry:
        cases = cases[:1]

    # ---- 任务队列：(run, case, mode)。--runs=N 表示额外再跑 N 轮 ----
    import random
    jobs: list[tuple[int, dict, str]] = []
    if rerun:
        # --rerun=N：从第 1 轮跑满 N 轮（用于改了问句的用例整体重生成）
        for run in range(1, 1 + rerun):
            for c in cases:
                for mode in MODES:
                    jobs.append((run, c, mode))
        random.Random(20261025 + rerun).shuffle(jobs)
    elif extra_runs:
        for run in range(2, 2 + extra_runs):
            for c in cases:
                for mode in MODES:
                    jobs.append((run, c, mode))
        random.Random(20261025 + extra_runs).shuffle(jobs)
    else:
        for c in cases:
            for mode in MODES:
                if todo_pairs is not None and (c["id"], mode) not in todo_pairs:
                    continue
                jobs.append((1, c, mode))

    print("用例 %d 条 × 模式 %d 个 × 运行 %d 次 = %d 次调用%s"
          % (len(cases), len(MODES), rerun or ((1 + extra_runs) if extra_runs else 1),
             len(jobs), "（已交错打乱）" if (extra_runs or rerun) else ""), flush=True)
    print("历史 %d 字符；模型参数 max_tokens=%d temperature=%.2f"
          % (len(hist), MAX_TOKENS, TEMPERATURE), flush=True)

    # 复用生产的 prompt 构建器
    gen = autoreply.FeizhiReplyGenerator()
    gen.life_ctx = ""       # 固定：不让生活状态成为变量
    gen.search_ctx = ""     # 固定
    gen.context_text = hist

    answers = []
    n = 0
    t_start = time.time()
    cache = {}               # (case, mode) -> memory_block，避免重复渲染
    guard_stats: dict[str, int] = {}
    for run, c, mode in jobs:
        n += 1
        now_str = c["asked_at"].replace("T", " ")[:16]
        ck = (c["id"], mode)
        if ck not in cache:
            cache[ck] = memory_block(mode, items, c["question"])
        gen.memory_ctx = cache[ck]
        system = gen._build_system(hist, False, now_str)
        user = "<OWNER>：" + c["question"]
        res = call_model(system, user)
        raw = res.get("output", "") if res.get("ok") else ""
        text, pstate = parse_plan_text(raw) if res.get("ok") else ("", "fail")
        # ★ 评测必须过 outguard：产品评分看「最终会发出去的文本」，
        #   否则会把兜底或改写后的效果误算成记忆策略的功劳。
        #   这里不传 regenerate —— 评测不额外重生成，severe 直接落兜底，
        #   与「生产里最多重试一次后仍异常」的最坏情况一致。
        gtext, gstate = outguard.guard(text) if text else ("", "fail")
        guard_stats[gstate] = guard_stats.get(gstate, 0) + 1
        rec = {"run": run, "case_id": c["id"], "mode": mode, "question": c["question"],
               "now_str": now_str, "system_chars": len(system),
               "memory_chars": len(gen.memory_ctx), "user": user,
               "parse_state": pstate, "guard_state": gstate, **res}
        rec["output_raw"] = raw            # 诊断：模型原始输出
        rec["output_parsed"] = text        # 诊断：解析后、检查前
        rec["output"] = gtext or ""        # 产品评分：最终发送文本
        answers.append(rec)
        status = "ok" if res.get("ok") else "FAIL"
        print("[%3d/%d] r%d %-9s %-12s %-4s %4.1fs out=%d %s%s%s"
              % (n, len(jobs), run, c["id"], mode, status,
                 res.get("latency_s", 0), len(text),
                 (res.get("usage", {}) or {}).get("prompt_tokens", ""),
                 (" parse=%s" % pstate) if pstate != "text" else "",
                 (" guard=%s" % gstate) if gstate not in ("pass",) else ""),
              flush=True)

    # 补跑模式：与旧结果合并
    if fill and prev is not None:
        merged = {(a["case_id"], a["mode"], a.get("run", 1)): a for a in prev["answers"]}
        for a in answers:
            merged[(a["case_id"], a["mode"], a.get("run", 1))] = a
        answers = list(merged.values())

    stamp = time.strftime("%Y%m%d-%H%M%S")
    tag = ("repeat%d_" % extra_runs) if extra_runs else (("rerun%d_" % rerun) if rerun else "")
    out = EVAL / ("answers_%s%s.json" % (tag, stamp))
    plan_states: dict[str, int] = {}
    for a in answers:
        plan_states[a.get("parse_state", "?")] = plan_states.get(a.get("parse_state", "?"), 0) + 1
    out.write_text(json.dumps({
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "snapshot": SNAP.name,
        "model": api_spec()[2], "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "constraints": {
            "persona_sha16": __import__("hashlib").sha256(
                __import__("pathlib").Path(FEIZHI / "persona.py").read_bytes()
            ).hexdigest()[:16],
            "outguard_rules": "overlap>=%d / config-markers / internal-markers" % outguard.OVERLAP_N,
            "outguard_fallback": outguard.FALLBACK_TEXT,
        },
        "guard_stats": guard_stats,
        "shuffled": bool(extra_runs),
        "extra_runs": extra_runs,
        "elapsed_s": round(time.time() - t_start, 1),
        "filled_from": prev_file.name if prev_file else None,
        "parse_states": plan_states,
        "answers": answers,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("解析状态统计:", plan_states)

    # 盲评文件：打乱 + 去掉模式
    import random
    random.seed(20261025)
    blind_items, key = [], {}
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for rec in answers:
        if not rec.get("ok"):
            continue
        bid = "".join(random.choice(alphabet) for _ in range(6))
        key[bid] = {"case_id": rec["case_id"], "mode": rec["mode"],
                    "run": rec.get("run", 1)}
        blind_items.append({"blind_id": bid, "case_id": rec["case_id"],
                            "question": rec["question"],
                            "output": rec.get("output") or rec.get("output_raw", "")})
    random.shuffle(blind_items)
    blind = EVAL / ("blind_%s.json" % stamp)
    blind.write_text(json.dumps({"items": blind_items}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    keyf = EVAL / ("blind_%s.key.json" % stamp)
    keyf.write_text(json.dumps(key, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for a in answers if a.get("ok"))
    print()
    print("成功 %d / %d，用时 %.1fs" % (ok, len(answers), time.time() - t_start))
    print("明细 ->", out)
    print("盲评 ->", blind)
    print("答案key（评分时不要打开）->", keyf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
