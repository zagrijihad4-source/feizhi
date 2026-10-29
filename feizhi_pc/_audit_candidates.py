# -*- coding: utf-8 -*-
"""两阶段诊断结果的人工核对辅助：把候选连来源原文摆出来 + 机器初筛。

不做语义判定，只做三件可程序化的事：
  1. 来源存在性：source_msg_ids 是否都在本批消息里（**引用存在**，不等于支持正文）
  2. 原子性启发式：一条候选里是否疑似塞了多个时间表达 / 多个命题
  3. 与 gold 的对应：哪些候选覆盖到预标事实（粗筛）

用法: python _audit_candidates.py
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
EVAL = HERE / "eval"
DB = HERE / "state" / "context.sqlite3"
GOLD = EVAL / "gold_v1.json"
DIAG = EVAL / "diag_two_stage.json"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

TIME_WORDS = ("今天", "明天", "昨天", "前天", "后天", "大后天", "今晚", "昨晚",
              "今早", "明早", "明晚", "上午", "下午", "早上", "晚上", "中午")
JOIN_WORDS = ("因为", "所以", "然后", "而且", "但是", "可是", "以及", "还有")


def load_texts(ids):
    ids = [i for i in ids if isinstance(i, int) or str(i).isdigit()]
    if not ids:
        return {}
    con = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True)
    q = ",".join("?" * len(ids))
    rows = con.execute(
        "SELECT id, role, text FROM messages WHERE id IN (%s)" % q,
        [int(i) for i in ids]).fetchall()
    con.close()
    return {r[0]: ("<OWNER>" if r[1] == "user" else "绯栀", r[2] or "") for r in rows}


def main() -> int:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    ranges = {b["id"]: b["range"] for b in gold["batches"]}
    golds = {b["id"]: b["gold"] for b in gold["batches"]}
    print("两阶段诊断核对：", diag["_meta"]["ran_at"], diag["_meta"]["model"])
    print("成本：%d 次调用 %.1f 秒"
          % (diag["_meta"]["cost"]["calls"], diag["_meta"]["cost"]["seconds"]))
    print()

    tot_c = tot_bad_src = tot_multi = 0
    for b in diag["batches"]:
        bid = b["id"]
        lo, hi = ranges[bid]
        valid = set(range(lo, hi + 1))
        cands = b.get("candidates") or []
        labels = {str(x.get("cid")): x for x in (b.get("labels") or [])}
        print("=" * 78)
        print("批 %s：%d 条候选" % (bid, len(cands)))
        print("=" * 78)
        for c in cands:
            tot_c += 1
            cid = str(c.get("cid"))
            t = c.get("text") or ""
            ids = c.get("source_msg_ids") or []
            bad = [i for i in ids if int(i) not in valid] if ids else []
            tw = [w for w in TIME_WORDS if w in t]
            jw = [w for w in JOIN_WORDS if w in t]
            flags = []
            if not ids:
                flags.append("无来源")
                tot_bad_src += 1
            elif bad:
                flags.append("来源不在本批%s" % bad)
                tot_bad_src += 1
            if len(tw) > 1 or jw:
                flags.append("疑似非原子(时间词=%s 连接词=%s)" % (tw, jw))
                tot_multi += 1
            g = labels.get(cid) or {}
            print("  %-4s [%-5s %-4s] %s" % (cid, g.get("kind") or "缺失",
                                            g.get("certainty") or "-", t[:56]))
            if flags:
                print("        ⚠ " + "；".join(flags))
            texts = load_texts(ids)
            for i in ids:
                who, tx = texts.get(int(i), ("?", "（取不到）"))
                print("        源#%s %s：%s" % (i, who, tx.replace("\n", " ")[:76]))
            # 与 gold 的粗筛对应
            for gg in golds[bid]:
                if any(k in t for k in (gg.get("must_contain") or [])):
                    print("        ← 可能覆盖 gold %s" % gg["id"])
        print()

    print("=" * 78)
    print("机器初筛汇总（不是语义结论）")
    print("=" * 78)
    print("  候选总数 %d；来源缺失/越界 %d；疑似非原子 %d"
          % (tot_c, tot_bad_src, tot_multi))
    print("  ★ 「来源存在」不等于「来源支持正文」，必须人工核对。")
    print("  ★ 疑似非原子只是启发式（多个时间词/连接词），也可能本来就是一个命题。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
