# -*- coding: utf-8 -*-
"""两阶段诊断：先把「候选选没选出来」和「选出来分没分对」拆开。

YG 定的流程：
  阶段1 只产出**原子候选**（一条 = 一个可独立核验的命题），不判 kind/certainty；
        两个不同时间的事必须分开（避免再出现「十二点多睡了，因为有早八」这种合并）。
  阶段2 只返回 cid + kind + certainty，**不许删除、合并、改写**候选。
        这是**诊断限制**，不代表所有候选都合格。
  程序检查 cid 一一对应；两阶段分开评分。

调用成本单独记在本文件产出的 `_meta` 里。

用法:
    python _diag_two_stage.py            # 全部三批
    python _diag_two_stage.py A          # 只跑 A 批
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
EVAL = HERE / "eval"
DB = HERE / "state" / "context.sqlite3"
GOLD = EVAL / "gold_v1.json"
OUT = EVAL / "diag_two_stage.json"
PEER = "<WXID_FRIEND_A>"

sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
logging.getLogger("feizhi_pc.memory").setLevel(logging.CRITICAL)

import llm as L                  # noqa: E402
import memory as M               # noqa: E402
import memrec as R               # noqa: E402

BJ = timezone(timedelta(hours=8))

STAGE1_SYSTEM = """你要从这段微信对话里列出**所有值得记的原子信息候选**。

规则：
1. 一条候选只写**一个可独立核验的命题**。属性、关系、偏好、事件都可以。
2. ★ **不要把两件事写进一条**，尤其是两个不同时间的事必须分开：
     ✗「他十二点多睡了，因为有早八」   ← 这是两件事（睡觉 / 有早八），日期还不同
     ✓「他十二点多睡了」                time_raw 填睡觉那句话里的时间说法
     ✓「他有早八」                      time_raw 填早八那句话里的时间说法
3. 每条必须给：
     cid                 c1 / c2 / …（本批内唯一）
     text                一句话说清这个命题，**不含日期/相对时间**
     source_msg_ids      支持它的消息 ID（对话里 `#` 后面的数字），至少一条
     time_raw            原话里的时间说法，**原样抄**；没有就填 ""
     time_anchor_msg_id  相对说法时填说出这句话的消息 ID，否则 null
4. **不要判断这是事实还是事件**，也不要给 certainty —— 那是下一步的事。
5. **宁可多列，不要漏**；寒暄和纯语气词不用列。

只输出一个 JSON 对象，不要解释、不要代码块：
{"candidates": [{"cid": "c1", "text": "...", "source_msg_ids": [517],
                 "time_raw": "明天", "time_anchor_msg_id": 517}]}"""

STAGE2_SYSTEM = """下面已经给你一批**抽好的候选**（每条有 cid）。你的任务**只是分类**。

必须遵守：
- 只返回每个候选的 `cid`、`kind`、`certainty`。
- **不许删除、不许合并、不许改写 text、不许新增**。cid 必须与输入一一对应，一条不漏。
  （这是诊断要求，不是因为这些候选都合格。）

kind 的判据**只有一条**：来源表达的适用范围。
  fact  = 现阶段持续有效的属性、关系、偏好、长期状态，或明确的周期安排（可被后续更新）。
  event = 某次经历、行动，或一次安排。**即使日期完全未知，也仍然是 event。**
  日期出现与否、certainty 高低，都不能单独决定分类。

certainty 表示「忠实于原话的把握」，与 kind 无关：
  high = 对方自己说过或确认过，且没被纠正
  mid  = 从情境推出来的，或只有间接线索
  low  = 记不太准

只输出一个 JSON 对象，不要解释、不要代码块：
{"labels": [{"cid": "c1", "kind": "fact", "certainty": "high"}]}"""


class Recorder:
    def __init__(self, inner):
        self.inner = inner
        self.calls = 0
        self.seconds = 0.0
        self.raw: list[str] = []

    def chat(self, system, user, **kw):
        t0 = time.time()
        out = self.inner.chat(system, user, **kw)
        self.seconds += time.time() - t0
        self.calls += 1
        self.raw.append(out)
        return out


class StaticStore:
    def __init__(self, rows):
        self.rows = rows

    def recent(self, limit=120):
        return list(self.rows)


def load_rows(lo: int, hi: int) -> list[dict]:
    con = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True)
    rows = con.execute(
        "SELECT id, role, text, sent_at_ms FROM messages"
        " WHERE id BETWEEN ? AND ? ORDER BY id", (lo, hi)).fetchall()
    con.close()
    return [{"id": r[0], "role": r[1], "text": r[2] or "",
             "sent_at_ms": r[3], "peer_wxid": PEER} for r in rows]


def fmt_ms(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=BJ).strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return "未知"


def convo(rows) -> str:
    return "\n".join(
        "#%s [%s] %s：%s" % (
            r["id"], fmt_ms(r["sent_at_ms"]),
            "<OWNER>" if r["role"] == "user" else "绯栀",
            str(r["text"])[:800])
        for r in rows)


def extract_json(s: str):
    """从模型输出里尽量取出 JSON（容忍前后废话与截断）。"""
    i, j = s.find("{"), s.rfind("}")
    for cand in (s[i:j + 1] if i >= 0 and j > i else "",):
        if not cand:
            continue
        try:
            return json.loads(cand)
        except Exception:  # noqa: BLE001
            pass
        salv = M._salvage_json(cand)
        try:
            return json.loads(salv)
        except Exception:  # noqa: BLE001
            continue
    return None


def main() -> int:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    want = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else None
    lc = L.LLMClient(order=["deepseek"])
    spec = dict(L.PROVIDERS.get("deepseek", {}))
    spec.update(lc.cfg.overrides.get("deepseek", {}))
    print("模型（锁定，无回退）： deepseek/%s" % spec.get("model"))
    print("两阶段诊断：阶段1 出原子候选；阶段2 只分类，不许删改。")
    print()

    out = {"_meta": {
        "ran_at": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"),
        "provider": "deepseek", "model": spec.get("model", "?"),
        "fallback": "disabled",
        "stage1_prompt_sha256": __import__("hashlib").sha256(
            STAGE1_SYSTEM.encode()).hexdigest()[:16],
        "stage2_prompt_sha256": __import__("hashlib").sha256(
            STAGE2_SYSTEM.encode()).hexdigest()[:16],
        "cost": {"calls": 0, "seconds": 0.0, "note": "阶段1+阶段2 各一次/批"},
    }, "batches": []}

    for b in gold["batches"]:
        if want and b["id"] not in want:
            continue
        lo, hi = b["range"]
        rows = load_rows(lo, hi)
        print("=" * 74)
        print("批 %s  %s（%d 条消息）" % (b["id"], b["span"], len(rows)))
        print("=" * 74)

        # ---- 阶段1：原子候选 ----
        r1 = Recorder(lc)
        try:
            raw1 = r1.chat(STAGE1_SYSTEM, "【对话】\n" + convo(rows),
                           max_tokens=2000, temperature=0.4)
        except Exception as e:  # noqa: BLE001
            print("  [阶段1 失败]", e)
            out["batches"].append({"id": b["id"], "error_stage1": str(e)})
            continue
        obj1 = extract_json(raw1) or {}
        cands = obj1.get("candidates") or []
        print("  阶段1：%d 条候选（%.1fs）" % (len(cands), r1.seconds))
        out["_meta"]["cost"]["calls"] += r1.calls
        out["_meta"]["cost"]["seconds"] += r1.seconds

        # ---- 阶段2：只分类 ----
        payload = json.dumps(
            {"candidates": [{"cid": c.get("cid"), "text": c.get("text"),
                             "source_msg_ids": c.get("source_msg_ids"),
                             "time_raw": c.get("time_raw")} for c in cands]},
            ensure_ascii=False, indent=1)
        r2 = Recorder(lc)
        try:
            raw2 = r2.chat(STAGE2_SYSTEM, "【候选】\n" + payload,
                           max_tokens=1200, temperature=0.2)
        except Exception as e:  # noqa: BLE001
            print("  [阶段2 失败]", e)
            out["batches"].append({"id": b["id"], "candidates": cands,
                                   "raw_stage1": raw1, "error_stage2": str(e)})
            continue
        obj2 = extract_json(raw2) or {}
        labels = obj2.get("labels") or []
        out["_meta"]["cost"]["calls"] += r2.calls
        out["_meta"]["cost"]["seconds"] += r2.seconds

        # ---- 程序检查 cid 一一对应 ----
        cids = [str(c.get("cid")) for c in cands]
        lids = [str(x.get("cid")) for x in labels]
        missing = [c for c in cids if c not in lids]
        extra = [c for c in lids if c not in cids]
        dup = sorted({c for c in lids if lids.count(c) > 1})
        print("  阶段2：%d 条标签（%.1fs） 缺=%s 多=%s 重复=%s"
              % (len(labels), r2.seconds, missing, extra, dup))

        lab = {str(x.get("cid")): x for x in labels}
        for c in cands:
            cid = str(c.get("cid"))
            g = lab.get(cid) or {}
            print("    %-4s [%-5s %-4s] %s"
                  % (cid, g.get("kind") or "缺失", g.get("certainty") or "-",
                     (c.get("text") or "")[:52]))
        print()

        out["batches"].append({
            "id": b["id"], "msg_count": len(rows),
            "candidates": cands, "labels": labels,
            "check": {"missing": missing, "extra": extra, "dup": dup},
            "raw_stage1": raw1, "raw_stage2": raw2,
            "seconds": {"stage1": round(r1.seconds, 1), "stage2": round(r2.seconds, 1)},
        })

    out["_meta"]["cost"]["seconds"] = round(out["_meta"]["cost"]["seconds"], 1)
    EVAL.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("成本：%d 次调用，%.1f 秒" % (out["_meta"]["cost"]["calls"],
                                      out["_meta"]["cost"]["seconds"]))
    print("已写入", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
