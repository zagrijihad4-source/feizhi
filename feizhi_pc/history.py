# -*- coding: utf-8 -*-
"""绯栀的对话历史压缩（全量上下文 + 超限自动压缩）。

设计动机（2026-10-17 用户提出）：
不该用固定条数截断 —— 真人不是"只记得最近 40 句"，而是全部记得、
太久远的自然变成模糊印象。所以改成：

  1. 全量历史都进 prompt（不设固定条数）
  2. 总字符数超过预算时，把**较早的部分压成一段她自己视角的叙述**
  3. 摘要会累积：旧摘要 + 新一批消息 -> 新摘要，并记录覆盖到哪条消息 id
  4. 最近一段始终保留原文（她"记得清"的部分）

这跟 DeepSeek 会话的 checkpoint 机制是同一个思路：压缩而不是丢弃。
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

LOG = logging.getLogger("feizhi_pc.history")

HERE = Path(__file__).resolve().parent
DEFAULT_PATH = HERE / "state" / "feizhi_summary.json"

# 触发压缩的字符预算。
# 中文约 1.5~2 token/字，20000 字 ≈ 30~40k token；DeepSeek 上下文 64k，
# 还要留给 system prompt（约 8k 字符）和输出（900 token），所以留一半余量。
CHAR_BUDGET = 20000
# 压缩时保留多少比例的最近原文（她"记得清楚"的部分）
KEEP_RATIO = 0.35
# 单条摘要的长度上限（防止摘要自己长成新的大山）
SUMMARY_MAX = 2600

SUMMARY_SYSTEM = """你在帮「绯栀」整理记忆。
下面是她和男朋友<OWNER>更早的一段聊天（可能还带着更早的旧摘要）。
请把它压成一段她自己视角的叙述，保留：
- 发生过的重要事情（时间、地点、结果）
- 两人之间的约定、梗、称呼、习惯
- <OWNER>的状态变化（工作、学业、情绪、身体）
- 她自己的重要状态变化
丢掉：寒暄、重复、没有信息量的语气词。
用第一人称、平实中文，像在回想，不要分点罗列，不要写"摘要"两个字。
只输出这段叙述本身。"""


def clip_message(t: str, limit: int = 1200) -> str:
    """长消息保留头尾、中间省略（审查 R12）。

    旧代码只给模型前 300 字，却把整条消息标记为"已覆盖" —— 长消息的尾部
    就此从后续工作上下文里消失。现在保留头 2/3 + 尾 1/3，两头都不丢。
    """
    t = str(t or "")
    if len(t) <= limit:
        return t
    head = limit * 2 // 3
    tail = limit - head
    return t[:head] + "……" + t[-tail:]


# store 里存的是**内部记录标记**，不是真正发出去的话。
# 它们原样进上下文会被模型学走 —— 实测 2026-10-27 她输出过
# 「绯栀：[照片]gen_4c9f2b7e8a1d3f6c.jpg 你看这版…」，连自己的名字和凭空
# 编的文件名都照抄了这套格式，而那个文件在 images/ 里根本不存在。
# 所以在**进上下文之前**统一翻成人话。
_MARKER_PATTERNS = [
    (re.compile(r"^\[图片\]\s*(.+?)(?:\.\w+)?\s*$"), "（发了一张「%s」的图片）"),
    (re.compile(r"^\[照片\]\s*(.+?)(?:\.\w+)?\s*$"), "（发了一张自己拍的照片）"),
    (re.compile(r"^\[表情\]\s*(.+?)(?:\.\w+)?\s*$"), "（发了个「%s」表情）"),
    (re.compile(r"^\[贴纸\]\s*(.+?)(?:\.\w+)?\s*$"), "（发了个「%s」表情包）"),
    (re.compile(r"^\[语音\]\s*(.+?)\s*$"), "（发了条语音：%s）"),
    (re.compile(r"^\[翻唱\]\s*(.+?)\s*$"), "（给<OWNER>唱了一段%s）"),
]


def humanize_marker(text: str) -> str:
    """把内部记录标记翻成给模型看的自然描述。"""
    t = str(text or "").strip()
    for pat, fmt in _MARKER_PATTERNS:
        m = pat.match(t)
        if m:
            # 有的格式串没有占位符（如「（发了一张自己拍的照片）」），不能盲取 % 格式化
            return fmt % m.group(1) if "%s" in fmt else fmt
    return t


class HistoryCompactor:
    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path)
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                d.setdefault("summary", "")
                d.setdefault("covered_until_id", 0)
                d.setdefault("updated", "")
                return d
            except Exception as e:  # noqa: BLE001
                LOG.warning("摘要文件损坏，重新开始：%r", e)
        return {"summary": "", "covered_until_id": 0, "updated": ""}

    def save(self) -> None:
        self.path.parent.mkdir(exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ---------- 查询 ----------
    @property
    def summary(self) -> str:
        return self.data.get("summary", "")

    def stats(self) -> dict:
        return {"summary_chars": len(self.summary),
                "covered_until_id": self.data.get("covered_until_id", 0),
                "updated": self.data.get("updated", "")}

    # ---------- 核心 ----------
    def build(self, store, peer: str, llm=None) -> dict:
        """返回 {summary, raw, compacted, total_chars}。

        raw 是「未被摘要覆盖的原始消息」，正序 [(role, text), ...]。
        超出预算且有 llm 时会先压缩，再返回。
        """
        try:
            rows = store.all_messages(peer)      # ★ 全量，不再 limit 5000（审查 R12）
        except Exception as e:  # noqa: BLE001
            LOG.warning("读历史失败：%r", e)
            rows = []     # 时间正序

        covered = int(self.data.get("covered_until_id", 0))
        raw_after = [r for r in rows if int(r.get("id") or 0) > covered]
        pair = [(("user" if r.get("role") == "user" else "assistant"),
                 humanize_marker(str(r.get("text", ""))))
                for r in raw_after]

        total = len(self.summary) + sum(len(t) for _, t in pair)
        result = {"summary": self.summary, "raw": pair, "compacted": False,
                  "total_chars": total}

        if total <= CHAR_BUDGET or llm is None or len(pair) < 20:
            return result

        # 超出预算：把较早的 (1-KEEP_RATIO) 压进摘要
        # ★ 按**字符预算**决定切到哪，而不是按条数（审查 R12）：
        #   原来按比例切条数，遇到长消息仍会超预算（实测预算 20000 却返回 50047 字）。
        budget_keep = int(CHAR_BUDGET * KEEP_RATIO)
        keep_chars = 0
        cut = len(pair)
        for i in range(len(pair) - 1, -1, -1):
            keep_chars += len(pair[i][1])
            if keep_chars > budget_keep:
                cut = i + 1
                break
            cut = i
        cut = max(1, min(cut, len(pair) - 1))
        old_part, keep_part = pair[:cut], pair[cut:]
        new_summary = self._compress(old_part, llm)
        if new_summary is None:
            return result      # 压缩失败就原样返回（宁可长一点也不能丢）

        self.data["summary"] = new_summary
        self.data["covered_until_id"] = int(raw_after[cut - 1].get("id") or 0)
        self.data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save()
        LOG.info("历史已压缩：%d 条 -> 摘要 %d 字，覆盖到 id=%d（保留原文 %d 条）",
                 cut, len(new_summary), self.data["covered_until_id"], len(keep_part))
        return {"summary": new_summary, "raw": keep_part, "compacted": True,
                "total_chars": len(new_summary) + sum(len(t) for _, t in keep_part)}

    def _compress(self, pairs: list[tuple[str, str]], llm) -> str | None:
        convo = "\n".join("%s：%s" % ("<OWNER>" if r == "user" else "绯栀", clip_message(t))
                          for r, t in pairs)
        user = ""
        if self.summary:
            user += "【更早的摘要】\n" + self.summary + "\n\n"
        user += "【这段聊天】\n" + convo
        try:
            out = llm.chat(SUMMARY_SYSTEM, user, max_tokens=1200, temperature=0.4)
        except Exception as e:  # noqa: BLE001
            LOG.warning("压缩调用失败（保留原文）：%r", e)
            return None
        out = (out or "").strip().strip("`").strip()
        if not out:
            return None
        if len(out) > SUMMARY_MAX:
            out = out[:SUMMARY_MAX]
        return out


def render_context(summary: str, raw: list[tuple[str, str]]) -> str:
    """把摘要 + 原文拼成注入用的上下文。"""
    parts = []
    if summary:
        parts.append("【她记得的更早的事（自己的回忆，不是逐句原文）】\n" + summary)
    if raw:
        lines = "\n".join("%s：%s" % ("<OWNER>" if r == "user" else "绯栀", t) for r, t in raw)
        parts.append("【最近的对话（原文）】\n" + lines)
    if not parts:
        return ""
    return ("以下是你们的聊天记录，你要接着聊：最近的几句是当前话题，"
            "更早的回忆用来理解前情、称呼和你们之间发生过的事。"
            "需要时自然接上，不要装作没看过，也不要整段复述。\n\n" + "\n\n".join(parts))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(HERE))
    from store import ContextStore
    c = HistoryCompactor()
    print("摘要状态：", json.dumps(c.stats(), ensure_ascii=False))
    d = c.build(ContextStore(), "<WXID_FRIEND_A>")
    print("原始消息 %d 条，总字符 %d，是否压缩 %s"
          % (len(d["raw"]), d["total_chars"], d["compacted"]))
