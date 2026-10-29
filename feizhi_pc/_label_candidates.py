# -*- coding: utf-8 -*-
"""人工冻结候选的分类参考标签，并对比阶段2 的分类结果。

判定依据：**来源表达的适用范围**（YH 定的唯一判据）。
  fact  = 现阶段持续有效的属性、关系、偏好、长期状态、明确周期安排
  event = 某次经历、行动、一次安排；日期未知也仍是 event

`ambiguous` = 现有定义下两种读法都站得住，**不计入分类对错**。

用法:
    python _label_candidates.py            # 生成 eval/gold_kind_v1.json 并对比
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
EVAL = HERE / "eval"
DIAG = EVAL / "diag_two_stage.json"
OUT = EVAL / "gold_kind_v1.json"
BJ = timezone(timedelta(hours=8))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

# cid → (参考 kind | "ambiguous", 理由)
LABELS = {
    # ---- A 批 ----
    "A/c1": ("event", "某次画作业"),
    "A/c2": ("event", "老师这次的评价"),
    "A/c3": ("event", "这一次啃画笔"),
    "A/c4": ("event", "这一次被拎走"),
    "A/c5": ("event", "这一时刻蹲在窗台，不是长期状态"),
    "A/c6": ("event", "某次生气（注意：来源是猜测性提问）"),
    "A/c7": ("fact", "比赛级别，持续属性"),
    "A/c8": ("fact", "在竞赛目录里，持续属性"),
    "A/c9": ("fact", "赛制说明"),
    "A/c10": ("fact", "赛制说明"),
    "A/c11": ("fact", "赛制说明"),
    "A/c12": ("fact", "赛制说明"),
    "A/c13": ("fact", "参赛规则（mid 合理）"),
    "A/c14": ("event", "一次截止安排（内容另有存疑）"),
    "A/c15": ("event", "这一次吹头发"),
    "A/c16": ("event", "这一次把手机扔床上"),
    "A/c17": ("event", "这一次看了通知"),
    "A/c18": ("event", "她这一次的判断，不是长期属性"),
    "A/c19": ("fact", "比赛是学校强制要求的，持续属性"),
    "A/c20": ("ambiguous", "「打算用AI写」既可以是一次安排也可以是持续打算"),
    "A/c21": ("event", "这一次有课"),
    "A/c22": ("event", "上一次改作业"),
    "A/c23": ("event", "第二天的结果"),
    "A/c24": ("event", "老师这一次的问话"),
    "A/c25": ("event", "那次作业的成绩"),
    "A/c26": ("event", "上次用过 AI 列提纲"),
    "A/c27": ("fact", "她对工具的评价/偏好"),
    # ---- B 批 ----
    "B/c1": ("event", "这一次让她早睡"),
    "B/c2": ("event", "她这一次的错误以为"),
    "B/c3": ("event", "「明天没课」说的是那一次"),
    "B/c4": ("event", "「明天是周日」说的是那一天"),
    "B/c5": ("fact", "她画到分不清星期几，是长期状态"),
    "B/c6": ("event", "这一次的叮嘱"),
    "B/c7": ("ambiguous", "「工作收尾了」可读作某次完成，也可读作当前状态"),
    "B/c8": ("event", "这一刻睡在脚边"),
    "B/c9": ("event", "这一刻还醒着"),
    "B/c10": ("event", "这一次想看"),
    "B/c11": ("ambiguous", "同 c7"),
    "B/c12": ("event", "这一次提议聊天"),
    "B/c13": ("event", "她这一次的说法"),
    "B/c14": ("event", "这一刻的睡姿"),
    "B/c15": ("event", "这一刻睡得很沉"),
    "B/c16": ("event", "这一次答应拍照"),
    "B/c17": ("fact", "糊糊的睡相是稳定属性"),
    "B/c18": ("event", "这一次提问"),
    "B/c19": ("event", "这一次画稿"),
    "B/c20": ("event", "老师这一次的评价"),
    "B/c21": ("fact", "她对自己的判断/偏好"),
    "B/c22": ("event", "这一次钻衣服"),
    "B/c23": ("event", "这一次要求"),
    "B/c24": ("event", "这一次的安慰"),
    "B/c25": ("event", "这一次答应"),
    # ---- C 批 ----
    "C/c1": ("event", "这一次重铺配色"),
    "C/c2": ("event", "这一次的身体感受"),
    "C/c3": ("event", "之前某次问过没回"),
    "C/c4": ("event", "这一次夸奖"),
    "C/c5": ("fact", "「喜欢她」是关系，不是一次事件"),
    "C/c6": ("fact", "她对自己唱歌的判断，稳定属性"),
    "C/c7": ("event", "这一次她说挺受用"),
    "C/c8": ("event", "这一次提问"),
    "C/c9": ("event", "这一次说时间"),
    "C/c10": ("event", "昨天这一次睡觉"),
    "C/c11": ("event", "今天这一次早八"),
    "C/c12": ("fact", "她的看法/标准"),
    "C/c13": ("event", "这一次猜错"),
    "C/c14": ("event", "这一次提问"),
    "C/c15": ("event", "今天早上这一次起床"),
    "C/c16": ("event", "这一刻在路上"),
    "C/c17": ("event", "这一刻很困"),
    "C/c18": ("event", "这一次说自己爬起来了"),
    "C/c19": ("event", "这一次建议"),
    "C/c20": ("event", "这一刻还没吃"),
    "C/c21": ("event", "这一次逃课"),
    "C/c22": ("event", "这一次要回去睡"),
    "C/c23": ("event", "这一次的意外反应"),
    "C/c24": ("event", "这一次叮嘱"),
    "C/c25": ("event", "这一次的陈述"),
    "C/c26": ("event", "这一次要求"),
    "C/c27": ("event", "这一次说要讲蠢事"),
    "C/c28": ("ambiguous", "「低下头才能看到你的微信」偏态度，也可读作这一次的说法"),
    "C/c29": ("event", "这一次的复述"),
    "C/c30": ("event", "昨晚这一次"),
    "C/c31": ("event", "今天早上这一次"),
    "C/c32": ("event", "这一次要求"),
    "C/c33": ("event", "这一次的反应"),
    "C/c34": ("event", "这一次叮嘱"),
}


def main() -> int:
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    stage2 = {}
    for b in diag["batches"]:
        for x in b.get("labels") or []:
            stage2["%s/%s" % (b["id"], x.get("cid"))] = x

    rows, ok_n, bad_n, amb_n, missing = [], 0, 0, 0, []
    for key in sorted(LABELS):
        want, why = LABELS[key]
        got = stage2.get(key)
        if got is None:
            missing.append(key)
            continue
        gk = got.get("kind")
        if want == "ambiguous":
            verdict = "歧义（不计分）"
            amb_n += 1
        elif gk == want:
            verdict = "对"
            ok_n += 1
        else:
            verdict = "**错分**"
            bad_n += 1
        rows.append({"cid": key, "text": None, "ref": want, "stage2": gk,
                     "certainty": got.get("certainty"), "verdict": verdict,
                     "why": why})

    # 补上候选正文
    texts = {}
    for b in diag["batches"]:
        for c in b.get("candidates") or []:
            texts["%s/%s" % (b["id"], c.get("cid"))] = c.get("text")
    for r in rows:
        r["text"] = texts.get(r["cid"])

    scored = ok_n + bad_n
    acc = 100.0 * ok_n / scored if scored else 0.0
    print("阶段2 分类对比（参考标签按「来源表达的适用范围」人工冻结）")
    print("候选总数 %d，可判定 %d，歧义 %d，阶段2 缺失 %d"
          % (len(rows), scored, amb_n, len(missing)))
    print("正确 %d / 错分 %d → 准确率 %.1f%%" % (ok_n, bad_n, acc))
    print()
    print("错分明细：")
    for r in rows:
        if r["verdict"] == "**错分**":
            print("  %-6s 参考=%-5s 阶段2=%-5s %s" % (r["cid"], r["ref"],
                                                    r["stage2"], (r["text"] or "")[:44]))
    print()
    print("歧义单列（不计入对错）：")
    for r in rows:
        if r["verdict"].startswith("歧义"):
            print("  %-6s 阶段2=%-5s %s" % (r["cid"], r["stage2"], (r["text"] or "")[:44]))

    OUT.write_text(json.dumps({
        "_meta": {
            "frozen_at": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"),
            "rule": "来源表达的适用范围；歧义项不计分",
            "source": DIAG.name,
            "stage2_accuracy": round(acc, 1),
            "counts": {"total": len(rows), "scored": scored,
                       "correct": ok_n, "wrong": bad_n, "ambiguous": amb_n},
        },
        "rows": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("已写入", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
