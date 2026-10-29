"""记忆反思层 v1：定期给记忆做体检，产出一份可审阅的缺陷清单。

★ 职责边界（硬约束，改动前先读这一段）
  * **只读** memory，绝不修改 `feizhi_memory.json` 里的任何记录。
    `memrec.add_record` 里写死了「needs_review 由程序判定，不接受自报」，
    反思层若回写记录字段，等于绕过 gate/quarantine 那一整套契约
    —— 那条路以前踩过坑（见 eval/SAMPLE_REPORT.md）。
  * 结论写到独立的 `state/reflection.json`，供人看、由人决定要不要动手。
  * 任何异常只记日志，绝不向上抛 —— 它挂在回复主流程旁边，不能连累回消息。

★ v1 为什么**不调模型**
  体检的三类缺陷全是「程序可判」的：
    A. 正文里带相对时间词（明天/前天/待会儿…）—— 契约要求正文不含时间词，
       时间只放 time_raw。这类记录当初写进去是合规的，但过期后正文仍带着
       「明天」，渲染进 prompt 时模型会当真（实测：`<OWNER>明天9点有课` 入库于
       2026-10-16，今天渲染仍然写「明天」）。
    B. 瞬时状态被记成长期记忆 —— 「<OWNER>还没回」只在一瞬间成立。
    C. 同一件事被多次复述 —— 挤占 `render()` 的 12 条事件配额。
  A/B 的过期判定可以用「入库日 + 相对词偏移」算出来；C 用剥虚词后的二元组覆盖率。
  没有一步需要语义理解，所以边际成本是 0（只读本地 JSON，一次几毫秒）。

★ 实验记录（2026-10-27，生产 96 条活记录）
  A 类 5 条、B 类 2 条、C 类 4 组 —— 全部经人工核对为真，零假阳性。
  第一版指标有两处错，已修正并留档：
    1. 「刚刚」把「她觉得自己刚刚好」误判成时间词 → 从词表移除。
    2. 用 Jaccard 判重复得到 0 组，与肉眼所见矛盾：
       「<OWNER>周日没有课」vs「<OWNER>周日没课，绯栀让他别打游戏太晚」
       Jaccard 仅 0.20。本项目最常见的重复形态是「一句是另一句的改写扩充」，
       必须用**短句二元组被覆盖的比例**（containment），不是 Jaccard。
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import memrec as R
from memory import BEIJING

LOG = logging.getLogger("feizhi.reflect")

DEFAULT_PATH = Path(__file__).resolve().parent / "state" / "reflection.json"

# 相对词的日偏移。None = 指向的日期没法精确算出来（跨周/跨学期），
# 这种只能交给人看，程序不擅自判过期。
REL_OFFSET = {
    "大后天": 3,
    "明天": 1,
    "后天": 2,
    "昨天": -1,
    "前天": -2,
    "今天": 0,
    "今晚": 0,
    "今早": 0,
    "刚才": 0,
    # ★ 「现在 / 马上 / 待会儿」保留检测但**不自动判过期**（None）：
    #   它们既是时间副词（「现在在画稿」→ 早过期，实测有这类脏数据），
    #   也可能是状态描述（「现在住石家庄」→ 仍然有效），程序分不开。
    #   注意是**降级为人工复核**，不是从词表里删掉 —— 删掉就再也扫不出来了。
    "现在": None,
    "马上": None,
    "待会儿": None,
    "待会": None,
    "等会儿": None,
    "这周": None,
    "本周": None,
    "下周": None,
    "上周": None,
    "这学期": None,
    "本周末": None,
    "周末": None,
}
# 长的优先匹配，否则「大后天」会被「后天」抢先、「本周末」被「周末」抢先。
_KEYS = sorted(REL_OFFSET, key=len, reverse=True)
REL_PAT = re.compile("|".join(re.escape(k) for k in _KEYS))

# 瞬时状态：只在说话的当下成立。只收 REL_PAT 覆盖不到的，避免同一句报两遍。
# ★ 「没回」要排除「没回家 / 没回来 / 没回国」这类真实状态描述，
#   否则「<OWNER>还没回家」会被当成瞬时状态误报。
MOMENT_PAT = re.compile(r"(?:还没回|没有回|没回)(?![家来国去头])|正在|还在|等下")

# 剥掉虚词再比，否则「没有课」和「没课」会被当成两件事。
FILLER = re.compile(r"[有的了是在和也就都还又很把被给让跟向对]")
_NORM_STRIP = re.compile(r"[\s，。！？、,.!?;；:：\"'“”‘’()（）\[\]【】]+")

SEV_ORDER = {"high": 0, "mid": 1, "low": 2}


def _core(s: str) -> str:
    return FILLER.sub("", _NORM_STRIP.sub("", str(s or "")))


def _bigrams(s: str) -> set:
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def _ref(x: dict) -> str:
    return str(x.get("id") or "<legacy>")


def _created(x: dict) -> str:
    return str(x.get("created") or x.get("added") or "")


def _index(live: list[dict]) -> dict:
    """复现 `render_existing()` 的 F/E 编号，好让人直接对上 prompt 里那一条。

    编号规则必须和 memory.py 保持一致（facts 先、events 后，各从 1 起），
    否则报告里写「F01」人会找到另一条记忆上去。
    """
    idx = {}
    facts = [x for x in live if x.get("kind") != "event"]
    events = [x for x in live if x.get("kind") == "event"]
    for i, x in enumerate(facts, 1):
        idx[id(x)] = "F%02d" % i
    for i, x in enumerate(events, 1):
        idx[id(x)] = "E%02d" % i
    return idx


def _parse_day(s: str):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _check_time_leak(live, idx, today):
    """A. 正文里带相对时间词，且它指向的那天已经过去。"""
    out = []
    for x in live:
        text = str(x.get("text") or "")
        words = REL_PAT.findall(text)
        if not words:
            continue
        created = _parse_day(_created(x))
        # 用最长匹配的那个词判偏移（同一句可能同时出现「明天」和「周末」）
        word = max(words, key=len)
        off = REL_OFFSET.get(word)
        target = None
        if created is not None and off is not None:
            target = created + timedelta(days=off)
        if off is None:
            action, auto_ok, sev = "review", False, "mid"
            why = "正文含「%s」，指向的日期跨周/跨月算不准，需要人看" % word
        elif target is None:
            action, auto_ok, sev = "review", False, "mid"
            why = "正文含「%s」，但没有入库日可算基准" % word
        elif target < today:
            action, auto_ok, sev = "archive", True, "high"
            why = ("正文含「%s」；入库日 %s → 指向 %s，已过去 %d 天，"
                   "现在渲染出来仍像当下的安排"
                   % (word, created, target, (today - target).days))
        else:
            action, auto_ok, sev = "keep", True, "low"
            why = "正文含「%s」，但指向 %s 还没到" % (word, target)
        out.append({
            "check": "time_leak",
            "refs": [idx.get(id(x), "?")],
            "record_id": x.get("id"),
            "kind": x.get("kind"),
            "text": text,
            "created": _created(x),
            "evidence": why,
            "action": action,
            "auto_ok": auto_ok,
            "severity": sev,
        })
    return out


def _check_transient(live, idx, today):
    """B. 瞬时状态被当成长期记忆。"""
    out = []
    for x in live:
        text = str(x.get("text") or "")
        words = MOMENT_PAT.findall(text)
        if not words:
            continue
        out.append({
            "check": "transient",
            "refs": [idx.get(id(x), "?")],
            "record_id": x.get("id"),
            "kind": x.get("kind"),
            "text": text,
            "created": _created(x),
            "evidence": ("含「%s」—— 这类状态只在说话当下成立，"
                         "沉淀成长期记忆后会让模型以为事情一直卡在那儿"
                         % "/".join(sorted(set(words)))),
            "action": "review" if x.get("kind") == "event" else "archive",
            "auto_ok": x.get("kind") != "event",
            "severity": "mid",
        })
    return out


def _check_duplicate(live, idx):
    """C. 近重复：剥虚词后短句二元组被覆盖 >= 0.7。

    保留原则：正文更长、信息更全的那条留下，另一条建议归档。
    """
    out = []
    for i in range(len(live)):
        for j in range(i + 1, len(live)):
            a, b = live[i], live[j]
            ca, cb = _core(a.get("text")), _core(b.get("text"))
            if len(ca) < 4 or len(cb) < 4:
                continue
            ga, gb = _bigrams(ca), _bigrams(cb)
            cov = len(ga & gb) / min(len(ga), len(gb))
            if cov < 0.7:
                continue
            la, lb = len(str(a.get("text") or "")), len(str(b.get("text") or ""))
            keep, drop = (a, b) if la >= lb else (b, a)
            out.append({
                "check": "duplicate",
                "refs": [idx.get(id(a), "?"), idx.get(id(b), "?")],
                "record_id": a.get("id"),
                "text": str(a.get("text") or ""),
                "text_b": str(b.get("text") or ""),
                "evidence": ("两句覆盖率 %.2f，重复；建议留「%s」"
                             % (cov, keep.get("text"))),
                "keep": idx.get(id(keep), "?"),
                "drop": idx.get(id(drop), "?"),
                "action": "archive",
                # 重复对里的两条可能分属不同 kind（同一件事被记成 fact 和 event），
                # 归档哪条、要不要合并成一条，需要人看一眼，程序不擅自决定。
                "auto_ok": False,
                "severity": "mid" if cov < 0.95 else "high",
            })
    return out


def scan(memory, today=None) -> dict:
    """跑一遍体检，返回报告字典。**只读**，不碰 memory。"""
    today = today or datetime.now(BEIJING).date()
    recs = memory._view()
    all_live = R.recallable(recs)
    # ★ 编号按**全集**算：`render_existing()` 不对 text 做过滤，
    #   若按过滤后的列表编号，一旦有 text 为空的记录，F02 之后会整体错位，
    #   报告里的「F07」就会指到另一条记忆上。
    idx = _index(all_live)
    live = [x for x in all_live if x.get("text")]

    findings = []
    findings += _check_time_leak(live, idx, today)
    findings += _check_transient(live, idx, today)
    findings += _check_duplicate(live, idx)
    findings.sort(key=lambda f: (SEV_ORDER.get(f["severity"], 9), f["check"]))

    counts = {}
    for f in findings:
        counts[f["check"]] = counts.get(f["check"], 0) + 1
    return {
        "ts": datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S"),
        "today": str(today),
        "scanned": len(live),
        "summary": counts,
        "actionable": sum(1 for f in findings if f["action"] != "keep"),
        "findings": findings,
    }


def save_report(report: dict, path=None) -> Path:
    """原子写：先写 .tmp 再 replace，避免留下半截 JSON。"""
    p = Path(path or DEFAULT_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
    return p


def maybe_reflect(memory, min_interval: float = 86400.0, path=None) -> dict:
    """按间隔跑体检并落盘。挂在后台线程里，异常一律吞掉。

    默认 24 小时一次：v1 是纯本地计算，成本为 0，但报告没人看就等于噪音，
    频率再高没意义。
    """
    try:
        p = Path(path or DEFAULT_PATH)
        if p.exists():
            try:
                prev = json.loads(p.read_text(encoding="utf-8"))
                last = datetime.strptime(prev.get("ts", ""), "%Y-%m-%d %H:%M:%S")
                age = (datetime.now(BEIJING) - last.replace(tzinfo=BEIJING)).total_seconds()
                if age < min_interval:
                    return {"skipped": "too_soon", "age": int(age)}
            except Exception:  # noqa: BLE001  旧报告坏了就照常重跑
                pass
        report = scan(memory)
        save_report(report, p)
        if report["actionable"]:
            LOG.info("记忆体检：%d 条待处理 %s", report["actionable"],
                     report["summary"])
        return {"ok": True, "actionable": report["actionable"],
                "summary": report["summary"]}
    except Exception as e:  # noqa: BLE001
        LOG.warning("记忆体检失败（忽略）：%r", e)
        return {"error": "reflect", "detail": str(e)}
