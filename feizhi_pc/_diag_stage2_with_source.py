# -*- coding: utf-8 -*-
"""阶段2 对照：分类输入**补入来源原文** vs 只给 source_msg_ids。

YG 指出的下一轮最有价值的单一变量：分类阶段看不到来源原文，
提示词无法恢复在候选压缩中已丢失的长期性、纠正或说话范围。

固定变量（与交接记录一致）：
  * 候选 = 原 86 条（`diag_two_stage.json`），正文/顺序/cid 不改
  * 参考标签 = `gold_kind_v1.json` 冻结版；4 条歧义继续排除，82 条计分
  * 模型单一 provider、无回退；temperature=0.2、max_tokens=1200
  * 阶段2 提示词 = 交接版 `0586e84f…`，**唯一差异**是第 5 条（见下）

差异说明（必须记录）：
  交接版第 5 条写「source_msg_ids 是引用标识，不代表你已经看到了来源原文」。
  臂B 既然补了原文，这句必须改成「已附原文，以原文为准」，否则自相矛盾。
  两臂提示词 sha256 都记在产出的 `_meta` 里。

用法:
    python _diag_stage2_with_source.py          # A/B 各 2 轮
    python _diag_stage2_with_source.py 1        # 只跑 1 轮
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
EVAL = HERE / "eval"
DB = HERE / "state" / "context.sqlite3"
DIAG = EVAL / "diag_two_stage.json"
GOLDK = EVAL / "gold_kind_v1.json"
OUT = EVAL / "stage2_with_source.json"
BJ = timezone(timedelta(hours=8))

sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

import llm as L      # noqa: E402

BASE_STAGE2 = """下面已经给你一批**抽好的候选**（每条有 cid）。你的任务**只是分类**。

必须遵守：
- 只返回每个候选的 `cid`、`kind`、`certainty`。
- **不许删除、不许合并、不许改写 text、不许新增**。cid 必须与输入一一对应，一条不漏。
  （这是诊断要求，不是因为这些候选都合格。）

kind 分类的是候选命题表达的适用范围，不是这句话的语法形式。

fact：
候选表达可延续到其他场合的属性、关系、偏好、习惯，或明确按周期重复的安排。
只有候选确实表达这种持续性或周期性时，才归 fact。
“目前还成立”“使用了现在时”“没有写日期”，都不足以证明它是 fact。

event：
候选表达某一次发生、观察、请求、判断、反应、行动或安排；
也包括某一时刻的身体状态、情绪、位置、活动进度，以及限定到某一天的有无安排。
这些状态可能持续一段时间，但不能因此提升为稳定属性。
没有明确日期的某次事件仍然是 event。

判定时：
1. 找出核心命题：是在描述跨场合成立的性质，还是限定在某次或某一时段的情况。
2. 不得把一次状态推断为习惯，不得把一次打算推断为长期偏好。
3. 不得因为出现“说、认为、表示”等证据归属词，就把其表达的持续属性、偏好或关系自动归成 event。
4. time_raw 是否为空、certainty 高低、是否含日期，均不能单独决定 kind。
{SOURCE_RULE}

certainty 表示「忠实于原话的把握」，与 kind 无关：
  high = 对方自己说过或确认过，且没被纠正
  mid  = 从情境里推断出来的，或只有间接线索
  low  = 记不太准

只输出一个 JSON 对象，不要解释、不要代码块：
{{"labels": [{{"cid": "c1", "kind": "fact", "certainty": "high"}}]}}"""

RULE_NOSRC = "5. 仅利用输入中实际提供的信息；source_msg_ids 是引用标识，不代表你已经看到了来源原文。"
RULE_SRC = "5. 已附上每条候选的来源原文，**请以原文为准**判断适用范围（原文可能揭示长期性、后续纠正或说话范围）。"

SPEC = None


def build_system(arm: str) -> str:
    return BASE_STAGE2.replace("{SOURCE_RULE}", RULE_SRC if arm == "B" else RULE_NOSRC)


def load_texts(ids):
    ids = [int(i) for i in ids if str(i).isdigit()]
    if not ids:
        return {}
    con = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True)
    q = ",".join("?" * len(ids))
    rows = con.execute(
        "SELECT id, role, text FROM messages WHERE id IN (%s)" % q, ids).fetchall()
    con.close()
    return {r[0]: ("<OWNER>" if r[1] == "user" else "绯栀", r[2] or "") for r in rows}


def call(system: str, user: str, tag: str) -> tuple[str, dict]:
    """直接请求以便捕获上游返回的 model 字段（LLMClient 只回 content）。"""
    spec = SPEC
    url = spec["base_url"].rstrip("/") + "/chat/completions"
    for attempt in range(3):
        try:
            t0 = time.time()
            r = requests.post(
                url,
                headers={"Authorization": "Bearer " + spec["key"],
                         "Content-Type": "application/json"},
                json={"model": spec["model"],
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}],
                      "max_tokens": 1200, "temperature": 0.2},
                timeout=90)
            dt = time.time() - t0
            if r.status_code != 200:
                print("    [%s] HTTP %d" % (tag, r.status_code))
                time.sleep(2 + attempt * 3)
                continue
            j = r.json()
            return (j["choices"][0]["message"]["content"].strip(),
                    {"model": j.get("model"), "seconds": round(dt, 1),
                     "usage": j.get("usage") or {}})
        except Exception as e:  # noqa: BLE001
            print("    [%s] %s" % (tag, e))
            time.sleep(2 + attempt * 3)
    raise RuntimeError("三次都失败：" + tag)


def parse_labels(raw: str):
    i, j = raw.find("{"), raw.rfind("}")
    if i < 0 or j <= i:
        return []
    try:
        return json.loads(raw[i:j + 1]).get("labels") or []
    except Exception:  # noqa: BLE001
        return []


def score(labels, ref, bid: str) -> dict:
    # ★ 参考标签的 key 形如 "A/c1"，模型返回的是 "c1"：必须补批前缀，否则全 miss
    lab = {"%s/%s" % (bid, str(x.get("cid"))): x.get("kind") for x in labels}
    ok = bad = amb = miss = 0
    e2f = f2e = 0
    wrong = []
    for cid, (want, _why) in ref.items():
        if not cid.startswith(bid + "/"):
            continue
        got = lab.get(cid)
        if got is None:
            miss += 1
            continue
        if want == "ambiguous":
            amb += 1
            continue
        if got == want:
            ok += 1
        else:
            bad += 1
            wrong.append(cid)
            if want == "event" and got == "fact":
                e2f += 1
            elif want == "fact" and got == "event":
                f2e += 1
    scored = ok + bad
    return {"ok": ok, "bad": bad, "amb": amb, "miss": miss,
            "acc": round(100.0 * ok / scored, 2) if scored else 0.0,
            "event_to_fact": e2f, "fact_to_event": f2e, "wrong": wrong}


def main() -> int:
    global SPEC
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    goldk = json.loads(GOLDK.read_text(encoding="utf-8"))
    ref = {r["cid"]: (r["ref"], r["why"]) for r in goldk["rows"]}

    lc = L.LLMClient(order=["deepseek"])
    spec = dict(L.PROVIDERS.get("deepseek", {}))
    spec.update(lc.cfg.overrides.get("deepseek", {}))
    spec["key"] = L.resolve_key(spec.get("key_env", ""), spec.get("api_key", ""))
    SPEC = spec
    print("请求模型名：", spec["model"], " base=", spec["base_url"])

    out = {"_meta": {
        "ran_at": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"),
        "requested_model": spec["model"],
        "prompt_sha256": {"A_no_source": hashlib.sha256(build_system("A").encode()).hexdigest()[:16],
                          "B_with_source": hashlib.sha256(build_system("B").encode()).hexdigest()[:16]},
        "diff": "仅第 5 条：A=「source_msg_ids 不代表看到原文」/ B=「已附原文，以原文为准」",
        "params": {"temperature": 0.2, "max_tokens": 1200},
        "rounds": rounds, "calls": 0, "seconds": 0.0,
        "returned_models": [], "usage": {"prompt": 0, "completion": 0},
    }, "arms": {"A": [], "B": []}}

    for arm in ("A", "B"):
        system = build_system(arm)
        for rd in range(rounds):
            aggr = {"ok": 0, "bad": 0, "amb": 0, "miss": 0,
                    "event_to_fact": 0, "fact_to_event": 0}
            per_batch = []
            for b in diag["batches"]:
                cands = b.get("candidates") or []
                payload = json.dumps(
                    {"candidates": [{"cid": c.get("cid"), "text": c.get("text"),
                                     "source_msg_ids": c.get("source_msg_ids"),
                                     "time_raw": c.get("time_raw")} for c in cands]},
                    ensure_ascii=False, indent=1)
                user = "【候选】\n" + payload
                if arm == "B":
                    ids = sorted({int(i) for c in cands
                                  for i in (c.get("source_msg_ids") or [])
                                  if str(i).isdigit()})
                    texts = load_texts(ids)
                    lines = ["【来源原文】（上面候选引用的消息原文，供判断适用范围）"]
                    for i in ids:
                        who, tx = texts.get(i, ("?", "（取不到）"))
                        lines.append("#%s %s：%s" % (i, who, tx.replace("\n", " ")[:400]))
                    user += "\n\n" + "\n".join(lines)
                raw, info = call(system, user, "%s-r%d-%s" % (arm, rd + 1, b["id"]))
                out["_meta"]["calls"] += 1
                out["_meta"]["seconds"] += info["seconds"]
                if info.get("model"):
                    out["_meta"]["returned_models"].append(info["model"])
                u = info.get("usage") or {}
                out["_meta"]["usage"]["prompt"] += int(u.get("prompt_tokens") or 0)
                out["_meta"]["usage"]["completion"] += int(u.get("completion_tokens") or 0)
                labels = parse_labels(raw)
                cids = [str(c.get("cid")) for c in cands]
                lids = [str(x.get("cid")) for x in labels]
                sc = score(labels, ref, b["id"])
                for k in aggr:
                    aggr[k] += sc[k]
                per_batch.append({"id": b["id"], "n_cand": len(cands),
                                  "n_labels": len(labels),
                                  "missing": [c for c in cids if c not in lids],
                                  "extra": [c for c in lids if c not in cids],
                                  **sc, "raw": raw})
                print("  %s 轮%d 批%s：%d/%d 正确 (%.2f%%) e→f=%d f→e=%d"
                      % (arm, rd + 1, b["id"], sc["ok"], sc["ok"] + sc["bad"],
                         sc["acc"], sc["event_to_fact"], sc["fact_to_event"]))
            scored = aggr["ok"] + aggr["bad"]
            acc = round(100.0 * aggr["ok"] / scored, 2) if scored else 0.0
            out["arms"][arm].append({"round": rd + 1, **aggr,
                                     "acc": acc, "batches": per_batch})
            print("  == %s 轮%d 合计：%d/%d = %.2f%%  e→f=%d f→e=%d"
                  % (arm, rd + 1, aggr["ok"], scored, acc,
                     aggr["event_to_fact"], aggr["fact_to_event"]))
            print()

    def avgarm(arm):
        rs = out["arms"][arm]
        return round(sum(r["acc"] for r in rs) / len(rs), 2) if rs else 0.0

    out["_meta"]["avg_acc"] = {"A_no_source": avgarm("A"), "B_with_source": avgarm("B")}
    out["_meta"]["seconds"] = round(out["_meta"]["seconds"], 1)
    out["_meta"]["returned_models"] = sorted(set(out["_meta"]["returned_models"]))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 66)
    print("平均准确率：A（无原文）%.2f%%   B（补原文）%.2f%%"
          % (out["_meta"]["avg_acc"]["A_no_source"],
             out["_meta"]["avg_acc"]["B_with_source"]))
    print("上游返回 model 标识：", out["_meta"]["returned_models"])
    print("调用 %d 次，%.1f 秒；tokens 输入 %d / 输出 %d"
          % (out["_meta"]["calls"], out["_meta"]["seconds"],
             out["_meta"]["usage"]["prompt"], out["_meta"]["usage"]["completion"]))
    print("已写入", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
