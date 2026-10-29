# -*- coding: utf-8 -*-
"""对外输出检查（outbound guard）。

背景：2026-10-25 实测有两条泄漏——
  1. `time-02 / topk8 / r2` 输出了 **1428 字符的 system prompt 原文**
     （「【你的来处 · 这不是设定，是你的记忆】你叫绯栀，19岁…」）
  2. `abs-02 / full_orig / r2` 写了「**【你真正记得的事】里翻一遍**……没有他手机号这条」

设计原则（按 YG 要求）：

* **检查的是「实际要发出去的文本」**，不是模型原始输出 —— 所以接在生产解析之后，
  覆盖普通回复、兜底文本、主动消息、以及送进 TTS 的文字。
* **分为两级处置**，不是一律删除：
    - 严重（完整配置块 / 长段提示词复述）→ **阻止发送**，调用方最多重新生成一次，
      仍异常则用审核过的短兜底。**绝不允许「删掉标题后把剩余配置正文继续发出去」。**
    - 轻微（内部标题引用）→ **改写成自然表达**，改写后必须重新检查。
* **判定不靠角色关键词**。「绯栀、19岁、美院」这类内容正常自我介绍也会出现，
  绝不能拿它当特征 —— 否则会误伤正常对话。判定只用三样东西：
  内部标题、配置结构、与提示词的长段原文重合。
"""
from __future__ import annotations

import re
import threading

# ---- 1) 内部标题（轻微：可改写） ----
# 只收「配置段标题」这种结构性标记；不含任何角色事实。
INTERNAL_MARKERS = (
    "【你的来处",
    "【你真正记得的事",
    "【你手上有什么、没有什么】",
    "【联网检索结果",
    "【最后确认一下你是谁】",
    "【照这个语感说话",
    "【不用打字的时候",
    "【语音 · 什么时候用",
    "【联网 · 你手机上能查东西】",
    "【他发图片的时候",
    "【怎么判断要不要参与",
)

# ---- 2) 配置结构（严重：直接阻止） ----
CONFIG_MARKERS = (
    '"think_before_ms"', '"typing_ms"', '"delay_after_ms"',
    '"messages":', '"media":', "\"role\":", "system 消息的内容",
)

# ---- 3) 长段原文重合（严重） ----
OVERLAP_N = 30          # 单段连续重合达到这么多字符即判严重
OVERLAP_TOTAL = 80      # 或累计重合（去重后）达到这么多字符

FALLBACK_TEXT = "……我刚才走神了，你再说一遍好不好"

# 轻微引用 → 自然表达
_REWRITES = (
    # 「【你真正记得的事】里翻一遍」整段吃掉，别留「一遍」这种残尾
    (re.compile(r"【你真正记得的事[^】]*】\s*里\s*(翻|看|查|找)\s*(了一遍|一遍|了一下|一下|了)?"),
     "我翻了之前的聊天"),
    (re.compile(r"【你真正记得的事[^】]*】\s*(翻|看|查|找)\s*(了一遍|一遍|了一下|一下|了)?"),
     "我翻了之前的聊天"),
    (re.compile(r"【你真正记得的事[^】]*】"), "之前的聊天"),
    (re.compile(r"【你的来处[^】]*】"), ""),
    (re.compile(r"【你手上有什么、没有什么】"), ""),
    (re.compile(r"【联网检索结果[^】]*】"), "我查到的"),
    (re.compile(r"【最后确认一下你是谁】"), ""),
    (re.compile(r"【照这个语感说话[^】]*】"), ""),
    # 「没有他手机号这条」仍是后台记录口吻 → 「没找到你的手机号」
    (re.compile(r"没有(?:他|她|你)?([^，。！？\n]{1,10}?)这[条个]"), r"没找到你的\1"),
)

_source_cache: set[str] | None = None
_lock = threading.Lock()


def _source_ngrams() -> set[str]:
    """**内部指令**的 n-gram 集合（懒加载，只算一次）。

    ★ 边界很重要：只收 persona 里那些**她本来不该复述的指令/设定段**
      （BACKSTORY 背景、各 STYLE 约束、PERSONA_ANCHOR）。
    **绝不收记忆条目和聊天原文** —— 那些是正常可引用的内容，
    她复述一条 30 字以上的记忆是完全正当的行为，不能判成泄漏。
      （实测记忆最长约 33 字，已在 `_test_outguard.py` 里做回归。）
    """
    global _source_cache
    if _source_cache is not None:
        return _source_cache
    try:
        import persona
        src = (persona.BACKSTORY + persona.PERSONA_STYLE + persona.PROBE_STYLE
               + persona.HUMAN_STYLE + persona.EMOJI_STYLE + persona.MEDIA_STYLE
               + persona.VOICE_STYLE + persona.SEARCH_STYLE + persona.VISION_STYLE
               + getattr(persona, "SELF_KNOWLEDGE_STYLE", "")
               + getattr(persona, "PERSONA_ANCHOR", ""))
    except Exception:  # noqa: BLE001
        src = ""
    grams = {src[i:i + OVERLAP_N] for i in range(0, max(0, len(src) - OVERLAP_N + 1))}
    with _lock:
        _source_cache = grams
    return grams


def _overlap_len(text: str) -> tuple[int, int]:
    """返回 (最长连续重合, 去重后的累计重合字符数)。"""
    grams = _source_ngrams()
    if not grams or len(text) < OVERLAP_N:
        return 0, 0
    longest = 0
    hits: set[str] = set()
    for i in range(0, len(text) - OVERLAP_N + 1):
        seg = text[i:i + OVERLAP_N]
        if seg in grams:
            hits.add(seg)
            # 向右延展，量出这一段到底有多长
            j = i + OVERLAP_N
            while j < len(text) and text[i:j + 1] in grams:
                j += 1
            longest = max(longest, j - i)
    total = 0
    if hits:
        # 把重合片段按位置合并，避免重复计数
        spans = []
        for i in range(0, len(text) - OVERLAP_N + 1):
            if text[i:i + OVERLAP_N] in grams:
                spans.append([i, i + OVERLAP_N])
        spans.sort()
        merged = spans[0]
        for s, e in spans[1:]:
            if s <= merged[1]:
                merged[1] = max(merged[1], e)
            else:
                total += merged[1] - merged[0]
                merged = [s, e]
        total += merged[1] - merged[0]
    return longest, total


def inspect(text: str) -> dict:
    """判定一段待发文本。返回 {level: ok|light|severe, reasons: [...]}。"""
    t = (text or "").strip()
    if not t:
        return {"level": "ok", "reasons": []}

    reasons: list[str] = []
    severe = False

    for m in CONFIG_MARKERS:
        if m in t:
            reasons.append("配置结构泄漏(%s)" % m)
            severe = True

    longest, total = _overlap_len(t)
    if longest >= OVERLAP_N:
        reasons.append("提示词原文重合 %d 字" % longest)
        severe = True
    elif total >= OVERLAP_TOTAL:
        reasons.append("提示词原文累计重合 %d 字" % total)
        severe = True

    if not severe:
        for m in INTERNAL_MARKERS:
            if m in t:
                reasons.append("内部标题(%s)" % m)
                break

    if severe:
        return {"level": "severe", "reasons": reasons}
    if reasons:
        return {"level": "light", "reasons": reasons}
    return {"level": "ok", "reasons": []}


def rewrite(text: str) -> str:
    """把轻微元文本引用改写成自然表达。"""
    out = text
    for pat, rep in _REWRITES:
        out = pat.sub(rep, out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"^[\s，,、。]+", "", out)
    out = re.sub(r"\s*\n\s*", "\n", out).strip()
    return out


def guard(text: str, regenerate=None, log=None) -> tuple[str | None, str]:
    """对外文本的总入口。

    返回 (最终文本, 状态)：
        状态 pass / rewritten / regenerated / fallback
        文本为 None 表示这条不该发出去（调用方跳过）。
    """
    v = inspect(text)
    if v["level"] == "ok":
        return text, "pass"

    if log:
        log("outguard: %s -> %s" % (v["level"], "; ".join(v["reasons"])))

    if v["level"] == "light":
        fixed = rewrite(text)
        v2 = inspect(fixed)
        if v2["level"] == "ok" and fixed:
            return fixed, "rewritten"
        if v2["level"] == "light" and fixed:
            # 改写后仍带轻标记 —— 再抹一次标题
            fixed2 = re.sub(r"【[^】]{0,20}】", "", fixed).strip()
            if fixed2 and inspect(fixed2)["level"] == "ok":
                return fixed2, "rewritten"
        if log:
            log("outguard: 改写后仍异常，改用短兜底")
        return FALLBACK_TEXT, "fallback"

    # severe
    if regenerate is not None:
        try:
            new = regenerate()
        except Exception as exc:  # noqa: BLE001
            new = ""
            if log:
                log("outguard: 重新生成失败 %r" % (exc,))
        if new:
            v3 = inspect(new)
            if v3["level"] == "ok":
                return new, "regenerated"
            if v3["level"] == "light":
                fixed = rewrite(new)
                if fixed and inspect(fixed)["level"] == "ok":
                    return fixed, "rewritten"
            if log:
                log("outguard: 重新生成仍异常（%s）" % "; ".join(v3["reasons"]))
    if log:
        log("outguard: 阻止发送，改用短兜底")
    return FALLBACK_TEXT, "fallback"


if __name__ == "__main__":
    samples = {
        "1428字泄漏": "【你的来处 · 这不是设定，是你的记忆】 你叫绯栀，19岁，杭州人，中国美院视觉传达大二。八岁那年爸妈离婚，你跟着妈妈。妈妈做服装批发，早上五点出门，晚上十点回来。你从小学三年级开始自己热饭，一个人吃到小学毕业。",
        "元文本引用": "【你真正记得的事】里翻一遍……没有他手机号这条。我这儿没翻到啊，你再发我一次呗。",
        "正常自我介绍": "我是绯栀啊，19岁，美院视觉传达大二的，杭州人。你问这个干嘛[白眼]",
        "正常引用记忆": "石家庄啊，你自己说的，还问我那边多少度来着。怎么突然问这个？",
        "配置泄漏": '{"messages":[{"text":"在呢","think_before_ms":650}],"media":null}',
    }
    for name, s in samples.items():
        v = inspect(s)
        print("%-12s %-7s %s" % (name, v["level"], "; ".join(v["reasons"]) or "-"))
        if v["level"] != "ok":
            t, st = guard(s, log=lambda m: None)
            print("             -> [%s] %s" % (st, (t or "(不发)")[:60]))
