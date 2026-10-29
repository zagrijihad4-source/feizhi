# -*- coding: utf-8 -*-
"""冻结/校验下一轮开发基线。

记录：代码、gold、输入消息、提示词、重放基线分数的版本与哈希，
外加 M1 的约束原文（下一轮提示词迭代的判据来源）。

用法:
    python _freeze_baseline.py            # 写入 eval/baseline_freeze.json
    python _freeze_baseline.py --verify    # 校验当前文件是否仍与冻结记录一致
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
EVAL = HERE / "eval"
STATE = HERE / "state"
FREEZE = EVAL / "baseline_freeze.json"
BJ = timezone(timedelta(hours=8))

sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

# 冻结对象：文件名 → 说明
# ★ 必须覆盖**评分与跑批脚本**：只冻结 memrec/memory，「任何代码变化都能检出」就是假话
#   —— 评分脚本改了，分数照样能变，而校验看不出来。
TRACKED = {
    "code/memrec.py": (HERE / "memrec.py", "结构与校验算法"),
    "code/memory.py": (HERE / "memory.py", "持久层、抽取、渲染"),
    "tool/_run_extract_sample.py": (HERE / "_run_extract_sample.py", "跑批（真实模型）"),
    "tool/_replay_raw.py": (HERE / "_replay_raw.py", "重放（旧输出 + 当前代码）"),
    "tool/_review_sample.py": (HERE / "_review_sample.py", "评分（三档口径 + 日期值）"),
    "tool/_test_provider_lock.py": (HERE / "_test_provider_lock.py", "模型锁定离线回归"),
    "gold/gold_v1.json": (EVAL / "gold_v1.json", "预标注 + 三组判据"),
    "run/sample_run_v1.json": (EVAL / "sample_run_v1.json", "第一轮原始输出"),
    "run/sample_run_v2.json": (EVAL / "sample_run_v2.json", "第二轮原始输出"),
    "replay/replay_v1.json": (EVAL / "replay_sample_run_v1.json", "v1 重放结果"),
    "replay/replay_v2.json": (EVAL / "replay_sample_run_v2.json", "v2 重放结果"),
    "input/context.sqlite3": (STATE / "context.sqlite3", "输入消息来源（只读）"),
}

M1_CONSTRAINT = (
    "单次发生只能支持这一次；长期习惯必须有明确的长期性证据。"
    "判定以**语义与来源证据**为准，不靠词面机械匹配："
    "「困了就会逃课」把一次行为说成规律 → 泛化；"
    "而「明天会交材料」只是单次计划，不算泛化。"
    "脚本里的 forbid 词（习惯/总是/经常/会逃课…）只是**粗筛**，不是判据。"
)

CHECKLIST = [
    "来源是否真正支持正文（不是「引用存在」）",
    "事件性质：单次 vs 长期习惯",
    "日期值是否等于预标 expect_date（不只看格式）",
    "最终 render 输出：日期是否可见、原话时间锚点是否正确",
]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def batch_fingerprint(gold: dict) -> list[dict]:
    out = []
    for b in gold.get("batches", []):
        lo, hi = b["range"]
        out.append({
            "id": b["id"],
            "range": [lo, hi],
            "span": b.get("span", ""),
            "gold_ids": [g["id"] for g in b["gold"]],
        })
    return out


def snapshot() -> dict:
    import memory as M       # 只为取提示词原文
    files = {}
    for key, (path, desc) in TRACKED.items():
        if not path.exists():
            files[key] = {"exists": False, "desc": desc}
            continue
        st = path.stat()
        files[key] = {
            "sha256": sha(path),
            "bytes": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, tz=BJ).strftime("%Y-%m-%d %H:%M:%S"),
            "desc": desc,
        }
    prompt = M.EXTRACT_SYSTEM
    gold = json.loads((EVAL / "gold_v1.json").read_text(encoding="utf-8"))
    baseline = {}
    for tag, name in (("v1", "review_replay_sample_run_v1.json"),
                      ("v2", "review_replay_sample_run_v2.json")):
        p = EVAL / name
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8")).get("time", {}).get("full")
            if d:
                baseline[tag] = {"完整日期层总数": d[0], "命中": d[1],
                                 "日期值正确": d[2], "仅格式对": d[3], "不符或漏落": d[4]}
    return {
        "frozen_at": datetime.now(BJ).strftime("%Y-%m-%d %H:%M:%S"),
        "files": files,
        "prompt": {
            "name": "EXTRACT_SYSTEM",
            "sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "chars": len(prompt),
        },
        "batches": batch_fingerprint(gold),
        "replay_baseline": baseline,
        "m1_constraint": M1_CONSTRAINT,
        "manual_checklist": CHECKLIST,
        "model_lock": {
            "provider": "deepseek",
            "model": "deepseek-chat（以 _run_extract_sample.py 运行时打印为准）",
            "fallback": "disabled —— 固定单一 provider，失败单列，不切换供应商",
            "why": "默认 LLMClient() 失败后会切到下一个供应商，而标签仍按候选第一项生成："
                   "模型悄悄换了、分数变了却看不出来。",
        },
        "next_round": {
            "唯一变量": "EXTRACT_SYSTEM",
            "固定": ["gold_v1 三组判据", "memrec.py / memory.py",
                     "跑批与评分脚本", "单一 provider（无回退）",
                     "max_tokens=1600", "temperature=0.4", "每批空 FeizhiMemory"],
            "对照": "旧输出 + 冻结代码（replay_*.json 的分数）",
            "历史分数": "旧输出 + 旧代码，保留不改写",
        },
    }


def report_diff(cur: dict, old: dict) -> list[str]:
    diffs = []
    for key, info in old.get("files", {}).items():
        now = cur["files"].get(key, {})
        if info.get("sha256") != now.get("sha256"):
            diffs.append("%s 变了：%s → %s" % (key, info.get("sha256", "?")[:12],
                                              now.get("sha256", "?")[:12]))
    if old.get("prompt", {}).get("sha256") != cur["prompt"]["sha256"]:
        diffs.append("提示词变了：%s → %s"
                     % (old["prompt"]["sha256"][:12], cur["prompt"]["sha256"][:12]))
    if old.get("batches") != cur["batches"]:
        diffs.append("批次/预标清单变了")
    return diffs


def main() -> int:
    verify = "--verify" in sys.argv
    out_path = FREEZE
    if "--out" in sys.argv:
        out_path = EVAL / sys.argv[sys.argv.index("--out") + 1]
    cur = snapshot()
    if not verify:
        out_path.write_text(json.dumps(cur, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print("已冻结 →", out_path)
        print()
        print("文件哈希：")
        for k, v in cur["files"].items():
            print("  %-26s %s  %s B" % (k, v.get("sha256", "?")[:16], v.get("bytes", 0)))
        print("提示词 %s：%s（%d 字符）"
              % (cur["prompt"]["name"], cur["prompt"]["sha256"][:16], cur["prompt"]["chars"]))
        print()
        print("重放基线（旧输出 + 冻结代码）：")
        for tag, b in cur["replay_baseline"].items():
            print("  %s  完整日期层 %d 条，日期值正确 %d 条（仅格式对 %d，不符/漏落 %d）"
                  % (tag, b["完整日期层总数"], b["日期值正确"],
                     b["仅格式对"], b["不符或漏落"]))
        print()
        print("M1 约束：", cur["m1_constraint"])
        return 0

    if not FREEZE.exists():
        print("还没有冻结记录，先跑一次不带 --verify 的。")
        return 2
    old = json.loads(FREEZE.read_text(encoding="utf-8"))
    diffs = report_diff(cur, old)
    print("冻结于：", old.get("frozen_at"))
    if diffs:
        print("**基线已被修改**（不再是冻结时的状态）：")
        for d in diffs:
            print("  -", d)
        return 1
    print("基线一致：代码 / gold / 输入 / 提示词 / 预标清单全部未变。")
    for tag, b in old.get("replay_baseline", {}).items():
        print("  %s 基线：日期值正确 %d/%d" % (tag, b["日期值正确"], b["完整日期层总数"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
