"""自动回复：监听到「绯栀」的入站消息 -> LLM 生成 -> 通过 hook 桥发出。

复用 Feizhi 的 HermesReplyGenerator（绯栀人格 + 分段 + 拟人时序），
只把底层从 ADB 点击换成 PC hook 桥。
"""
from __future__ import annotations

import logging
import json
import os
import queue
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from bridge import HookBridge, InboundMessage, IGNORE_PEERS
from peer_state import PeerRegistry, SELF_PATH, get_registry, self_life   # noqa: E402
from store import ContextStore
from llm import LLMClient, LLMError, strip_meta_tags
from persona import style_block
from memory import FeizhiMemory
from history import HistoryCompactor, render_context
from life import FeizhiLife
import humanize
import imagegen
import img_dat
import outguard
import reflect
import search
import sing
import stickers
import vision

# 联网检索的判据统一收在 search 模块里（信号词表只有一份，避免两处漂移）。
# 这仍只是**粗筛**（宁可多查一次），用不用、怎么用由 LLM 看完检索结果自己判断
# —— 决策归模型，代码不越权。
needs_search = search.needs_search

# LLM 说要发照片时，再按这个概率真的生成（生成一次 1~3 分钟且耗额度）
DRAW_KEEP_PROB = 0.9

# 表情的**冷却**（只防刷屏，不参与决策 —— 要不要发、发哪个由 LLM 按语境决定）。
STICKER_WINDOW = 300.0       # 冷却窗口（秒）
STICKER_MAX_IN_WINDOW = 2    # 窗口内最多发几个

# 语音消息的类型码（微信 hook 抓到的 type 字段）
VOICE_TYPE = "34"
# 图片消息的类型码。收到后走「本地 dat 解密 → 视觉识别 → 转成一句描述」，
# 跟她听懂语音是同一个思路：先把非文本消息变成她能"看见/听见"的文本，再交给 LLM。
IMAGE_TYPE = "3"
# 一批连发里最多现场识别几张图（每张 3~8 秒，多了会拖住主循环）
BATCH_IMAGE_LIMIT = 3
# 语音正文最多几个字（TTS 约 2.5 字/秒，40 字 ≈ 16 秒；再长按住说话会失败）
VOICE_MAX_CHARS = 40

# ★ 最后一道防线：任何没被解析掉的内部标记都不能送到用户眼前。
#   实测 2026-10-27 22:01：模型少写了一个结尾的 `]`，`[voice:]` 的 fullmatch 失配，
#   于是走到 `_send_one` 末尾的 send_text 兜底，把 `[voice:害羞:……宝宝，我好喜…`
#   原样发了出去；而 `_send_plan` 那边只检查 startswith("[voice:")，判定"已写过库"
#   又跳过了记录 —— 结果是发出去且查不到。
_MARKER_RX = re.compile(
    r"\[(?:voice|sing|img|draw|sticker|照片|图片|语音|表情|翻唱)\s*[:：]?[^\]]*\]?")


def _strip_internal_markers(s: str) -> str:
    """剥掉残留的内部标记；若整条只剩标记则返回空串（调用方不要发）。"""
    return _MARKER_RX.sub("", s or "").strip()
# 一批连发里最多现场转写几条语音（每条 5~10 秒，多了会把主循环拖住）。
# 超出的先记占位，保证上下文里不会出现 XML 原文。
BATCH_VOICE_LIMIT = 2

# ★ 允许安静结束：真人不会每句都接。
#   条件故意收得很窄 —— 他发的只是「嗯/哦/好」这种纯应答词、而且刚聊过几分钟，
#   这时候不接话是正常的；发一段有内容的话却不回，那就是坏了。
#   不想让她有这种行为时设 FEIZHI_QUIET_END=0。
QUIET_END_ENABLED = os.environ.get("FEIZHI_QUIET_END", "1").lower() not in ("0", "false", "no")
QUIET_END_PROB = 0.25            # 命中条件后不接话的概率
QUIET_END_MAX_GAP_MIN = 3.0      # 只在下述时间内（距她上一条）才允许不接
QUIET_END_WORDS = {
    "嗯", "嗯嗯", "嗯呐", "哦", "哦哦", "哦好", "好", "好的", "好呀", "好嘞",
    "行", "行吧", "是", "对", "对的", "啊", "哈", "哈哈", "哈哈哈", "行行",
}

# 复用 Feizhi 的 LLM 回复生成器（人格 prompt + plan 解析）
_FEIZHI_SRC = Path(r"D:\Hermes work\feizhi-wechat-phone-bridge\src")
if str(_FEIZHI_SRC) not in sys.path:
    sys.path.insert(0, str(_FEIZHI_SRC))
from feizhi_phone_bridge.reply_generator import (  # noqa: E402
    HermesReplyGenerator, ReplyGenerationError, ReplyPlan,
    _is_complex, select_history,
)


# 人设锚点：在 prompt 末尾再重申一次。
# 动机（2026-10-17 用户提出）：上下文一长，性格就"变形" —— 模型对长上下文的
# 中间部分注意力最弱（lost in the middle），开头的人格约束会被冲淡，
# 越聊越像客服。所以把人设骨架在末尾再钉一遍（首尾的注意力最高）。
PERSONA_ANCHOR = (
    "\n【最后确认一下你是谁】\n"
    "你是绯栀，19 岁杭州女孩，美院视觉传达大二，是他的女朋友，不是助手、不是客服。\n"
    "· **心软是底色**：他累、他难受、他不舒服的时候，你一点都不毒舌，"
    "第一反应是心疼他、照顾他。\n"
    "· **刺只是调味**：只在轻松的时候（他显摆、逗你、撒娇）顶一句，十句话里顶多一两句。\n"
    "· **语气要软**：多用「啊/呀/嘛/呢/诶」和「…」；**不要用「别+动词」开头**"
    "（别硬撑／别熬夜／赶紧去 都太硬，像领导），改成「你先…好不好」「要不…呀」；"
    "关心先落在他身上（\"你这是怎么了呀\"），不是发指令。\n"
    "· 话多：想到什么说什么，会自己岔开再绕回来，不爱用总结句。\n"
    "· 怕被丢下，但不查岗、不卑微、不讨好。\n"
    "· 不列点、不报告腔、不说\"希望能帮到你\"这类话。\n"
    "上面那些聊天记录只是材料 —— 里面的口气可能偏冷，别跟着学，也别复述它们。\n"
    "\n【照这个语感说话（这几条的语气就是标准）】\n"
    "· 你今天怎么了呀，声音都不对了。\n"
    "· 先吃口东西好不好，我等你。\n"
    "· 你看你手都凉了…来，我给你捂捂。\n"
    "· 我都困了…你陪我说两句话嘛，说完就睡。\n"
    "· 不用你哄我，我自己会好的。…你抱着我一会儿就行。\n"
)


class FeizhiReplyGenerator(HermesReplyGenerator):
    """保留 Feizhi 的绯栀人格 prompt 与回复计划解析，
    只把底层 API 调用换成可插拔的 LLMClient（支持任意 OpenAI 兼容端点）。

    三处增强/优化：
    1. 追加「性格 + 追问 + 真人感 + 表情」约束段（persona.style_block）。
       原版输出偏完整、正确、有礼貌，实测像客服；这里约束的是「怎么说话」。
    2. 把原版正文里的人格描述换成选定方向（傲娇）。
       原版 base 的「先判断对方说法是否合理、信息是否充分」「不要用无条件附和来假装亲近」
       会把情话当成待核查的命题，逼出连环追问——2026-10-15 已整段替换（见下方 _OLD_CORE）。
    3. 把易变的时间从 prompt 开头挪到末尾。原版首行是 `当前时间：…`，
       每分钟都在变，会把 DeepSeek 的前缀缓存整个打断（实测命中 0）。
       新增的固定段插在 context 之前，因此也在可缓存范围内。
    """

    def __init__(self, llm: LLMClient | None = None,
                 enhance_persona: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.llm = llm or LLMClient()
        self.enhance_persona = enhance_persona
        # LLM 在这一轮里自己决定要发的表情/图（见 _call_api / _build_system）
        self.pending_sticker: str | None = None
        self.pending_image: str | None = None
        # 这一轮的联网检索结果（由 AutoReplier 在生成前塞进来，见 _build_system）
        self.search_ctx: str = ""
        # 这一轮的长期记忆（同上）。她的人设要求"记得小事"，
        # 但原实现只喂最近 8 条消息 —— 这段就是补那个缺口。
        self.memory_ctx: str = ""
        # 全量上下文（摘要 + 最近原文，由 HistoryCompactor 生成，超预算时已压缩）。
        # 一旦设置就不再按固定条数截断 —— 真人不是"只记得最近 40 句"。
        self.context_text: str = ""
        # 她"手上正在做的事"（生活事件）。聊天/主动消息/朋友圈三路共用同一份状态，
        # 避免三路各自编出互相矛盾的日程。
        self.life_ctx: str = ""

    def _build_system(self, context: str, complex_query: bool, now_str: str) -> str:
        raw = super()._build_system(context, complex_query, now_str)

        # 1) 时间从开头挪到末尾（保住前缀缓存）
        marker = "当前时间："
        nl = raw.find("\n")
        if raw.startswith(marker) and nl > 0:
            head, rest = raw[:nl], raw[nl + 1:]
            raw = rest + "\n" + head

        # 2) 把原版正文里的人格描述换成选定方向（傲娇）
        #
        # ★ 2026-10-15 关键修复：原版 base 把绯栀写成了**理性审校者** ——
        #   「先判断对方说法是否合理、信息是否充分」「不要用无条件附和来假装亲近」。
        #   面对「我好想你」「你喜欢我吗」这类情感表达，这个 prompt 会把情话当成
        #   待核查的命题，逼出「你今晚怎么了」「那个她是谁」的连环追问。
        #   实测（真实聊天 10-14 23:48~10-15 00:13）：他连问四次「你到底喜欢我吗」，
        #   绯栀四次全转成「你先说那个她是谁」，一次都没接住。
        #   所以在**骨头**上覆盖掉这段，而不是只在外面贴一层性格皮。
        _OLD_CORE = (
            "你是绯栀，19岁杭州女孩，中国美院视觉传达大二学生，"
            "正在通过微信小号与唯一联系人<OWNER>聊天。"
            "你有自己的判断，不以迎合为目标。先判断对方说法是否合理、信息是否充分。"
            "不同意时自然说明理由；不确定时坦白并追问；发现风险、矛盾或更好的方案时直接指出。"
            "不要用空泛夸赞、重复对方原话、无条件附和来假装亲近。"
            "可以有短暂犹豫、斟酌或自我修正，但不要每条都机械地说\u2018让我想想\u2019。"
        )
        _NEW_CORE = (
            "你是绯栀，19岁杭州女孩，中国美院视觉传达大二学生，"
            "正在通过微信小号跟**男朋友<OWNER>**聊天（今年春天在一起的）。\n"
            "\n"
            "**你心软，也有情有理。** 他累、他难受、他不舒服的时候，你一点都不毒舌，"
            "第一反应是心疼他 —— 因为从小没人管你，你知道那种滋味，"
            "所以你对他的难过特别上心。\n"
            "\n"
            "**你话很多。** 从小家里没人听你说话（爸妈离婚早，妈妈忙到很晚），"
            "所以现在有了他，你想把攒了十几年的都倒给他 —— "
            "问你在干嘛，你会说在干嘛、为什么、中间还发生了什么。\n"
            "\n"
            "**你说话是软的，你在谈恋爱，不是在办事。** 同一句话到你嘴里会更亲：\n"
            "「好，我很开心」这种话，你说出来是「好啊，宝宝我很开心呢」。\n"
            "句尾常带语气词（啊 / 呢 / 呀 / 啦 / 嘛），自然地叫他「宝宝」，"
            "把「你去做」换成「你去好不好」。但别每句都堆糖 —— 一句里软一处就够。\n"
            "\n"
            "你敏感、怕被丢下，但**不卑微、不查岗**；"
            "被哄的时候会有点不好意思 —— 但**不会用冷淡的话挡回去**，"
            "直接说开心就好，不用先嘴硬再软（「先冷一句再补软」这个套路已经取消了）。\n"
            "\n"
            "可以有短暂犹豫、斟酌或自我修正，但不要每条都机械地说\u2018让我想想\u2019。"
        )
        if _OLD_CORE in raw:
            raw = raw.replace(_OLD_CORE, _NEW_CORE)
            LOG.debug("persona core replaced（审校者 -> 女朋友）")
        else:
            # 原版文本变了就退化成逐句替换，至少别让审校者语气原样漏出去
            LOG.warning("原版 base 未按预期匹配，退化为逐句替换")
            for old, new in (
                ("正在通过微信小号与唯一联系人<OWNER>聊天。",
                 "正在通过微信小号跟男朋友<OWNER>聊天。"),
                ("你有自己的判断，不以迎合为目标。先判断对方说法是否合理、信息是否充分。",
                 "他有自己的脾气，你也有。他来找你说话，多半只是想跟你待一会儿。"),
                ("不同意时自然说明理由；不确定时坦白并追问；发现风险、矛盾或更好的方案时直接指出。",
                 "你不同意时会怼一句，但不会一直唱反调；他表达感情时先接住，再嘴硬。"),
                ("不要用空泛夸赞、重复对方原话、无条件附和来假装亲近。",
                 "他哄你、夸你的时候，你嘴上嫌弃，心里是受用的。"),
            ):
                if old in raw:
                    raw = raw.replace(old, new)

        for old, new in (
            ("保持活泼、黏人、自然、真诚，先回应对方实际内容。",
             "保持温柔、自然、真诚（说话带语气词，自然地喊他宝宝），"
             "先回应对方实际内容；别端着，也别像在念资料。"),
            ("把结果整理成自然的中文（活泼、真诚，不要报告腔）。",
             "把结果整理成自然的中文（温柔、口语，不要报告腔）。"),
        ):
            if old in raw:
                raw = raw.replace(old, new)
                LOG.debug("persona override: %r -> %r", old[:20], new[:20])

        # 2.5) ★ 让 sticker 字段成为**格式的一部分**。
        # 只把用法写在别处没用：原版 format_rules 说的是「格式必须是 {"messages":[...]}」，
        # LLM 会严格遵守、不敢加字段（实测 7 个场景 0 次输出 sticker）。
        # 所以必须直接改格式说明本身，并在末尾再强调一次。
        _FMT_OLD = ('只输出一个JSON对象，不要代码块或解释。格式必须是：'
                    '{"messages":[{"text":"第一句。","think_before_ms":650,"typing_ms":700,'
                    '"delay_after_ms":420},{"text":"第二句。","think_before_ms":260,'
                    '"typing_ms":850,"delay_after_ms":0}]}。')
        if _FMT_OLD in raw:
            raw = raw.replace(
                _FMT_OLD,
                '只输出一个JSON对象，不要代码块或解释。格式是：'
                '{"messages":[{"text":"第一句。","think_before_ms":650,"typing_ms":700,'
                '"delay_after_ms":420},{"text":"第二句。","think_before_ms":260,'
                '"typing_ms":850,"delay_after_ms":0}],"media":"翻白眼"}。'
                '★ messages 和 media 都是格式的一部分：\n'
                '  messages —— 你要说的文字（**1~3 条**）。\n'
                '  ★★ 多条 = **把一句话分成几次说完**，不是几个独立的回答。\n'
                '    每条接着上一条往下说，拆开读要像一段话被切成几口气 ——\n'
                '    真人打了一半觉得还没说完，隔两秒又补一条，是这个感觉。\n'
                '    ✗ 反例（三个独立回答，各说各的，像三个人在答同一句）：\n'
                '      「我就是一个路人呗」/「我就是个普通人」/「你加错了吧」\n'
                '    ✓ 正例（一句话分三口，顺着往下）：\n'
                '      「我？」/「你先说清楚你是谁呀」/「这么加过来我一点印象都没有」\n'
                '  ★ **一条能说完就别硬拆**。为了显得像真人才分成好几条，反而更假；\n'
                '    微信里真人经常就是一条说完。\n'
                '  media    —— 这一轮想额外发出去的**一个表情或图**，'
                '从下面两份清单里挑一个名字填进去；不想发就写 null。\n'
                '★ 该发就别光打字，这些场景都值得发一个：\n'
                '  - 他逗你、损你、你看不下去 → 「翻白眼」或「无语表情包」。\n'
                '  - 他显摆、气你 → 「不高兴」或「生气表情包」。\n'
                '  - 他撒娇、说想你 → 「害羞」「嘟嘴」「比心」。\n'
                '  - 你懒得打字、只想接一句 → 随便挑个贴切的。\n'
                '★ 十几轮里挑一两轮用，不用每轮都发。\n'
                '★ 他想**看见**东西的时候，用 `[draw:画面描述]` 写进 messages'
                '（现场生成一张图，慢，别滥用）：\n'
                '  - 「发张照片看看」「你现在什么样」→ 拍你自己。\n'
                '  - 「给我看看你画的」「发个配色图」「你那海报什么样」→ 拍你手上那张画：\n'
                '    描述里把你记着的配色写进去（靛蓝、暗红这些），主体是摊在桌上的画稿。\n'
                '  - 整条回复**只写一条** `[draw:...]`，不要在同一句里再写字。')
            LOG.debug("format rules 已扩容以容纳 media 字段")
        else:
            LOG.warning("原版 format_rules 未按预期匹配，sticker 字段可能不被输出")
        if self.enhance_persona:
            block = style_block(include_emoji=True,
                               relation=getattr(self, "relation", "intimate"),
                               peer_name=getattr(self, "peer_name", ""))
            # 唱歌曲库：只在真有成品时注入。
            # 这条刻意写短 —— 之前 [img:] 就是因为说明写太长、和 STICKER/PHOTO 三头并行，
            # 结果一次都没被用过（2026-10-15 实测）。这里只讲"有什么"和"怎么写"。
            _songs = sing.catalog_text()
            if _songs:
                block = (block + "\n\n【你唱过的歌】\n"
                         "你自己录过这几首：" + _songs + "，都存在手机里。\n"
                         "★ 他说「唱首歌」「给我唱一个」「唱来听听」的时候，"
                         "整条回复只写 `[sing:曲名]`。微信会把它当成一条语音条发出去，"
                         "那才是你真正在唱。\n"
                         "★ **不要用 `[voice:]` 把歌词念出来** —— 念词不是唱歌，"
                         "他听得出来。`[voice:]` 只用来说话。\n"
                         "一首歌只能发一段（四十几秒，不是整首）；他没点名就挑一首你想唱的；"
                         "别连着唱，也别每轮都唱 —— 真人唱歌是看场合的。\n")
            # 本地图片表情清单
            img_hint = stickers.image_prompt_hint()
            if img_hint:
                # 只放**动态清单**（有哪些图、哪些关键词），
                # 「什么时候该发、怎么选」已经在 persona.MEDIA_STYLE 里统一说了。
                # 之前这里也写了一大段说明，和 STICKER_STYLE/PHOTO_STYLE 三头并行，
                # 结果是占比最小的 [img:] 从来没被用过（2026-10-15 实测）。
                block = block + "\n\n" + img_hint
            # 真微信表情清单（收藏表情 + 表情包）
            st_hint = stickers.sticker_prompt_hint()
            if st_hint:
                names = [t["name"] for tbl in (stickers.FAV_TEMPLATES, stickers.PACK_TEMPLATES)
                         for t in tbl if t["name"]]
                block = (block + "\n\n" + st_hint +
                         "\n\n【回复计划里的 sticker 字段 —— 你怎么甩表情】\n"
                         "JSON 里那个 sticker 字段决定这一轮要不要甩个表情。它和你手机里"
                         "那套「文本表情」（[白眼]/[捂脸] 这种画在文字里的）是两回事：\n"
                         "  sticker = 你本人的照片表情 + 一套梗图，发出去是一条独立的表情消息，"
                         "对方看到的是图，**比打字有意思得多**。\n"
                         "可用名字：" + " / ".join(names) + "\n"
                         "\n"
                         "★ 这些时候就该甩：\n"
                         "  - 他发的东西你懒得评价 → 甩一个表情，比打「无语」自然。\n"
                         "  - 你刚怼完他、想再补一刀 → 甩「不高兴」。\n"
                         "  - 你确实在忙、一时顾不上 → 甩「稍等」，比解释一堆强。\n"
                         "  - 被他逗笑但不肯承认 → 甩「微笑」。\n"
                         "  - 不想接这个话题、想撤了 → 甩「挥手」或「托腮」。\n"
                         "★ 想用表情代替说话时，**用 sticker，不要用 [白眼] 这类文本表情** ——"
                         "文本表情只是标点，sticker 才是真的在发图。\n"
                         "★ 同一轮里不要既写文本表情又写 sticker。\n"
                         "★ 频率随你自己感觉，三四轮里挑一轮就够，不用刻意凑；不甩就写 null。")
            ctx_marker = "以下是最近真实微信对话"
            idx = raw.find(ctx_marker)
            if idx > 0:
                raw = raw[:idx] + block + "\n\n" + raw[idx:]
            else:
                raw = raw + block
            LOG.debug("persona block applied, system len=%d", len(raw))

        # 3.5) 长期记忆（事实 + 情节）。
        # 原实现每轮只把最近 8 条消息喂给模型，更早的对话对她等于不存在，
        # 而 persona 里写着她"记得小事、他随口说过的话都记着" —— 这段补那个缺口。
        # 放在检索结果之前：记忆是"底"，检索是"当场的补充"。
        if self.memory_ctx:
            ctx_marker = "以下是最近真实微信对话"
            idx = raw.find(ctx_marker)
            if idx > 0:
                raw = raw[:idx] + self.memory_ctx + "\n" + raw[idx:]
            else:
                raw = raw + "\n\n" + self.memory_ctx
            LOG.debug("memory block applied, %d chars", len(self.memory_ctx))

        # 3.6) 她"手上正在做的事"（生活事件）。
        # 放在记忆之后、真实对话之前：先知道"我在过什么日子"，再看对方说了什么。
        if self.life_ctx:
            ctx_marker = "以下是最近真实微信对话"
            idx = raw.find(ctx_marker)
            if idx > 0:
                raw = raw[:idx] + self.life_ctx + "\n" + raw[idx:]
            else:
                raw = raw + "\n\n" + self.life_ctx
            LOG.debug("life block applied, %d chars", len(self.life_ctx))

        # 4) 联网检索结果（由 AutoReplier 在生成前查好塞进来）。
        #    放在真实对话之前，让她据此回答；检索不到就什么都不加，退回按人格回。
        if self.search_ctx:
            ctx_marker = "以下是最近真实微信对话"
            block_txt = ("【联网检索结果（刚刚现查的，可以据此回答他）】\n"
                         + self.search_ctx + "\n"
                         "以上是搜索结果，可能有噪音。只取你确定相关的用，"
                         "查不到的就老实说不知道，不要编。\n\n")
            idx = raw.find(ctx_marker)
            if idx > 0:
                raw = raw[:idx] + block_txt + raw[idx:]
            else:
                raw = raw + "\n\n" + block_txt

        # 5) 人设锚点：末尾重申，对抗长上下文的人格稀释（lost in the middle）
        raw = raw + "\n" + PERSONA_ANCHOR
        return raw

    # ★ 上下文长度：原版 generate_plan 内部走 select_history(limit=12)，
    #   实际只喂最近 12 条消息（约 6 轮对话）—— 聊几句就断片。
    #   这里放宽到 40 条（约 20 轮）；autoreply 那边取 80 条供它筛选。
    CONTEXT_LIMIT = 40

    def _build_context(self, history: list[tuple[str, str]]) -> str:  # type: ignore[override]
        """把历史对话拼成上下文。

        原版引导语是「仅用于理解代词和承接话题，不得跨主题混用」—— 这条会把她
        压成"只看最近两句"，前面聊过的事一律当没发生。换成"接着聊"的口径。
        """
        if not history:
            return ""
        lines = [f"{'<OWNER>' if r == 'user' else '绯栀'}：{t}" for r, t in history]
        return (
            "以下是你们最近的微信对话（从早到晚）。你要接着聊：最近的几句是当前话题，"
            "更早的用来理解前情、称呼和你们之间发生过的事。需要时自然接上，"
            "不要装作没看过，也不要整段复述。\n" + "\n".join(lines)
        )

    def generate_plan(self, incoming: str,  # type: ignore[override]
                      history: list[tuple[str, str]] | None = None) -> ReplyPlan:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        complex_query = _is_complex(incoming)
        # ★ 优先用全量上下文（摘要 + 最近原文）：真人不是"只记得最近 40 句"，
        #   而是全都记得、太久远的自然变成模糊印象 —— 这就是压缩而不是截断。
        #   没设时（独立调用/测试）才退回按条数截取。
        if self.context_text:
            context = self.context_text
        else:
            context = self._build_context((history or [])[-self.CONTEXT_LIMIT:])
        system = self._build_system(context, complex_query, now_str)
        try:
            plan = self._parse_plan(self._call_api(system, f"<OWNER>：{incoming}"))
        except ReplyGenerationError:
            if complex_query:
                return self._fallback_plan("收到啦。这个需要我查一下，等我处理好了发给你。")
            raise
        return self._ensure_voice_if_asked(plan, system, incoming)

    # 他明确在要「声音」的表述 —— 唱歌、哼、念、发语音、说句话我听听
    # ★ 2026-10-27 补了两次，教训是这个词表一开始就太窄，而模型本身不主动写
    #   `[voice:]`，全靠这里触发 `_ensure_voice_if_asked()` 兜底。所以宁可放宽：
    #   误判的代价只是多发一条语音，漏判的代价是他反复要声音却什么都收不到。
    #   最后一次补的是「声音」——「不行，我就要听声音」原词表一条都不命中。
    #   「再说一遍」仍然不收：它多半指把话重说一遍。
    # 点歌：这几句话要的是**唱**，该走 [sing:]（RVC 曲库），不是 [voice:] 念词
    SING_REQUEST = re.compile(r"唱|哼一?两?句|哼一段|哼两句|整一首")

    VOICE_REQUEST = re.compile(
        r"声音|听你说话|唱|哼一?两?句|哼一段|哼两句|发.{0,4}语音|语音|"
        r"说句话.{0,6}我听|用声音|念一段|来一段|出声|说给我听|"
        r"没发出来|没收到|没听着|再发一遍|再录一遍|再试一遍|再试一次|重新发")

    @classmethod
    def _wants_voice(cls, text: str) -> bool:
        return bool(cls.VOICE_REQUEST.search(text or ""))

    @staticmethod
    def _plan_has_voice(plan) -> bool:
        """给了声音就算数 ——— **唱歌也算**。

        ★ 2026-10-28：这里原来只认 `[voice:`，于是模型老老实实回 `[sing:沦陷]`
          也被判成"没给声音"，接着被 _ensure_voice_if_asked 强制重试整个换掉，
          最后变成把歌词念出来的 `[voice:]`。有 RVC 曲库之后这条早该改了：
          `[sing:]` 才是真唱，`[voice:]` 只是说话。
        """
        for m in getattr(plan, "messages", []):
            t = str(getattr(m, "text", "")).lstrip()
            if t.startswith("[voice:") or t.startswith("[sing:"):
                return True
        return False

    def _ensure_voice_if_asked(self, plan, system: str, incoming: str):
        """他要声音就必须给声音 —— 模型不配合时用代码兜底。

        ★ 2026-10-19 实测事故：他连着说了三次「唱一首潮汐」「唱一首完整的嘛」，
          模型每次都只回嘴硬文字（「行吧，我五音不全」），然后下一轮干脆说
          「唱完了啊，该你说了」—— 假装已经唱过，实际一条语音都没有。
          光改人格提示词没用（它还会模仿历史里自己说过的假话），
          所以这里加硬约束：要声音 → 重试一次 → 还不给就把文字转成语音发出去。
        """
        if not self._wants_voice(incoming) or self._plan_has_voice(plan):
            return plan

        LOG.info("他要声音但模型只给了文字，强制重试一次：%r", incoming[:24])
        _ask_sing = bool(self.SING_REQUEST.search(incoming or ""))
        if _ask_sing:
            forced = system + (
                "\n\n【本轮硬性要求 · 覆盖上面所有「大多数时候发文字」的说法】\n"
                "他这一句是在点歌。\n"
                "你这一轮**必须**整条只输出 `[sing:曲名]`，曲名从你录过的里面挑。\n"
                "★ **绝对不要念歌词** —— 念词不是唱歌，他听得出来。\n"
                "★ 也不许只写「行吧我唱」「唱完了」这种话却没有标记 —— 那是骗人。")
        else:
            forced = system + (
                "\n\n【本轮硬性要求 · 覆盖上面所有「大多数时候发文字」的说法】\n"
                "他这一句明确是在要你的**声音**，想听你说话。\n"
                "你这一轮**必须**至少输出一条 `[voice:档位:内容]`，"
                "不许只写文字；也不许说「说完了」「我说给你听」却没有语音 —— 那是骗人。")
        try:
            plan2 = self._parse_plan(self._call_api(forced, f"<OWNER>：{incoming}"))
            if self._plan_has_voice(plan2):
                return plan2
        except ReplyGenerationError as exc:  # noqa: BLE001
            LOG.warning("强制语音重试失败：%s", exc)

        # 两轮都不给：代码兜底，把最后一段真正有内容的文字转成语音发出去
        LOG.warning("模型两轮都没给语音，兜底把最后一段文字改成语音")
        msgs = [{"text": str(getattr(m, "text", ""))} for m in getattr(plan, "messages", [])]
        for m in reversed(msgs):
            t = (m.get("text") or "").strip()
            if t and not t.startswith("["):
                m["text"] = "[voice:娇嗔:%s]" % t
                return self._parse_plan(json.dumps({"messages": msgs}, ensure_ascii=False))
        return plan

    def _call_api(self, system: str, user_msg: str) -> str:  # type: ignore[override]
        try:
            # 900 而不是 560：4 条消息 + JSON 结构（think_before_ms/typing_ms 等）
            # 很容易顶到 560 上限被截断，而截断就是 JSON 碎片事故的第一因（2026-10-17）。
            raw = self.llm.chat(system, user_msg, max_tokens=900, temperature=0.85)
        except LLMError as exc:
            raise ReplyGenerationError(str(exc)) from exc
        # ★ 上游偶发把内容审核元数据拼进正文（实测 api.deepseek.com 官方端点，
        #   2026-10-18 23:54 那条「你还要不」就整条变成
        #   `<ds_safety>[用户未成年]否 [分类]其他 …</ds_safety>Safe`）。
        #   llm.chat 已经会剥标签，但如果正文被它占满，剥完什么都不剩 ——
        #   这时重试一次比把「…我刚走神了一下」发出去强得多。
        if _reply_text_len(raw) == 0:
            LOG.warning("LLM 返回被审核元数据占满（%d 字符），重试一次", len(raw))
            try:
                raw2 = self.llm.chat(system, user_msg, max_tokens=900, temperature=0.85)
                if _reply_text_len(raw2) > 0:
                    raw = raw2
                else:
                    LOG.warning("重试后仍无可用正文，沿用首次结果走兜底")
            except LLMError as exc:
                LOG.warning("重试失败，沿用首次结果: %s", exc)
        # 顺手把 LLM 自己决定要发的表情/图摘出来（见 _build_system 里的格式说明）。
        # 由模型按语境判断，而不是代码拿关键词去配 —— 规则表不懂变通。
        # ★ 做成 JSON 字段而不是「文本里写标记」：实测只有字段形式才会被真正使用
        #   （sticker 做成字段后一直在用；image 早期只写在说明里，日志里搜不到一次）。
        self.pending_sticker = None
        self.pending_image = None
        try:
            data = json.loads(raw.strip().lstrip("`").rstrip("`"))
            if isinstance(data, dict):
                # media 是统一字段（值可以是微信表情名，也可以是图片名）。
                # 为什么合并：拆成 sticker/image 两个字段时它们会互相竞争 ——
                # 都填值时模型只挑排前面的那个（实测 sticker 3 次 / image 0 次），
                # 填 null 当默认值又会被照抄（image 那次 1/7）。合并成一个就没有竞争。
                media = data.get("media")
                if isinstance(media, str) and media.strip():
                    media = media.strip()
                    # 兼容旧字段
                    if stickers.find_sticker(media):
                        self.pending_sticker = media
                    elif stickers.find_image(media):
                        self.pending_image = media
                    else:
                        LOG.warning("LLM 给的 media 名字不认识: %r", media)
                # 旧字段仍然接受（防止模型偶尔还按老格式输出）
                st = data.get("sticker")
                if not self.pending_sticker and isinstance(st, str) and st.strip():
                    self.pending_sticker = st.strip()
                im = data.get("image")
                if not self.pending_image and isinstance(im, str) and im.strip():
                    self.pending_image = im.strip()
        except Exception:  # noqa: BLE001
            pass
        return self._sanitize_output(raw)

    @staticmethod
    def _sanitize_output(raw: str) -> str:
        """保证交给解析器的永远是「能解析出 messages 的 JSON」。

        ★ 2026-10-17 实测事故：模型输出被截断 -> json.loads 失败 ->
          原版 _fallback_plan 把整段 JSON 当回复文本 -> 微信里出现
          '{"messages":[{"text":"哦...' 和 '","think_before_ms":520,...' 这种碎片。
          模型也在学这些碎片（历史里存了它们），所以这是个会自我强化的坑。
          这里先把残缺 JSON 里的 text 字段抠出来重组成合法 JSON，
          救不回来就用一句自然的兜底，绝不把 JSON 残渣发出去。
        """
        s = (raw or "").strip().strip("`").strip()
        # 1) 是合法 JSON：**严格逐项校验并规范化**
        #    ★ 只检查外层结构不够（审查 R03）：像
        #      {"messages":[{"text":"hello","typing_ms":"oops"}]} 这种会原样放过，
        #      父解析器转 int 失败后走 raw fallback，最终把整段 JSON 当消息发出去
        #      —— 旧事故就是这么复发的。
        #    所以这里只保留 text（必须非空字符串），media 单独摘出；
        #    时序字段一律丢弃 —— _send_plan 用 humanize 现算，模型给的从来不用。
        try:
            data = json.loads(s)
            if isinstance(data, dict) and isinstance(data.get("messages"), list):
                cleaned = []
                for it in data["messages"]:
                    # ★ 每条正文都过一遍 strip_meta_tags：网关的安全标签
                    #   （<ds_safety>…</ds_safety>Safe）会随正文一起进来，
                    #   不剥就会入库、发到微信、再被历史喂回模型。
                    if isinstance(it, dict):
                        t = strip_meta_tags(it.get("text") if isinstance(it.get("text"), str) else "")
                        if t.strip():
                            cleaned.append({"text": t.strip()})
                    elif isinstance(it, str):
                        t = strip_meta_tags(it)
                        if t.strip():
                            cleaned.append({"text": t.strip()})
                if cleaned:
                    out = {"messages": cleaned}
                    media = data.get("media")
                    if isinstance(media, str) and media.strip():
                        out["media"] = media.strip()
                    return json.dumps(out, ensure_ascii=False)
                LOG.warning("LLM 输出的 messages 里没有可用文本，走兜底")
        except Exception:  # noqa: BLE001
            pass
        # 2) 残缺 JSON：把 text 字段抠出来重组
        texts = re.findall(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', s)
        clean = []
        for t in texts:
            t = strip_meta_tags(t.replace('\\"', '"').replace("\\n", "\n").strip())
            if t and not t.startswith("{") and '"messages"' not in t:
                clean.append(t)
        if clean:
            LOG.warning("LLM 输出不是合法 JSON，已从残缺内容救回 %d 条", len(clean))
            return json.dumps({"messages": [{"text": t} for t in clean]}, ensure_ascii=False)
        # 3) 纯文本（没有 JSON 痕迹）：当成一条消息
        plain = strip_meta_tags(s)
        if plain and "{" not in plain and '"messages"' not in plain:
            return json.dumps({"messages": [{"text": plain}]}, ensure_ascii=False)
        # 4) 兜底：绝不发 JSON 残渣
        LOG.warning("LLM 输出无法解析（长度 %d）：%r", len(s), s[:120])
        return json.dumps({"messages": [{"text": "…我刚走神了一下，你再说一遍"}],
                           "media": None}, ensure_ascii=False)

LOG = logging.getLogger("feizhi_pc.autoreply")

# 只对这些联系人自动回复（留空表示回复所有非系统联系人）
# ★ 2026-10-28 多用户：None = 不再用白名单挡人，所有好友都能找她说话。
#   陌生人靠 relation 档位（persona.style_block）控制口吻 —— 先客气、后熟。
# 同时最多几个联系人并行处理（用户定的 5）
PEER_WORKERS = 5

DEFAULT_ALLOW: set[str] | None = None

# 绯栀自己的 wxid。hook 在微信重启后会丢失 self_wxid，导致 isIncoming 判成 unknown，
# 这里作为兜底用于自行判定方向。
SELF_WXID = "<WXID_SELF>"


def _reply_text_len(raw: str) -> int:
    """粗算这段 LLM 输出里「真正能发出去的正文」有多长。

    用来判断这一轮是不是被上游的内容审核元数据占满了（见 strip_meta_tags）。
    剥完标签后 JSON 合法但 text 全是空串，也算 0 长度。
    """
    s = strip_meta_tags(raw or "")
    try:
        data = json.loads(s.strip().lstrip("`").rstrip("`"))
        if isinstance(data, dict) and isinstance(data.get("messages"), list):
            return sum(len(str(m.get("text") or ""))
                       for m in data["messages"] if isinstance(m, dict))
    except Exception:  # noqa: BLE001
        pass
    return len(s.strip())


def _is_system_peer(peer: str) -> bool:
    if not peer:
        return True
    low = peer.lower()
    for tag in IGNORE_PEERS:
        if low.startswith(tag) or low == tag:
            return True
    # 公众号 / 服务号
    if low.startswith("gh_") or low.startswith("qq"):
        return True
    return False


def resolve_direction(msg: InboundMessage) -> tuple[bool, str]:
    """判定消息是否为「发给绯栀的入站消息」。

    优先采信 hook 的 isIncoming（正常情况下它最准）。
    但 hook 是注入进微信进程的静态状态，微信一重启就重置，
    此时 self_wxid 丢失 -> direction=unknown / isIncoming=false，
    不能据此当作"出站"丢弃，否则重启后就再也收不到消息。
    兜底逻辑：拿消息里的 selfWxId，没有就用配置的 SELF_WXID，
    再判断 sender/peer 是否等于自己。
    """
    if msg.is_incoming:
        return True, "hook_isIncoming"

    self_wxid = str(msg.raw.get("selfWxId") or "").strip() or SELF_WXID
    peer = (msg.peer_wxid or "").strip()
    sender = (msg.sender_wxid or "").strip()
    frm = str(msg.raw.get("from") or "").strip()

    # 自己发的 -> 明确是出站
    if self_wxid and self_wxid in (peer, sender, frm):
        return False, "self_sent"
    # 有明确的发送方且不是自己 -> 入站
    who = sender or frm
    if who and who != self_wxid:
        return True, "fallback_sender_not_self"
    return False, "direction_undecidable"


class AutoReplier:
    def __init__(
        self,
        allow: set[str] | None = None,
        bridge: HookBridge | None = None,
        store: ContextStore | None = None,
        llm: LLMClient | None = None,
        llm_timeout: int = 60,
    ):
        self.bridge = bridge or HookBridge()
        self.store = store or ContextStore()
        if allow is not None:
            self.allow = set(allow)
        elif DEFAULT_ALLOW is not None:
            self.allow = set(DEFAULT_ALLOW)
        else:
            self.allow = None          # None = 全部放行
        self.llm = llm or LLMClient()
        self.gen = FeizhiReplyGenerator(llm=self.llm, timeout=llm_timeout, attempts=2)
        self._llm_timeout = llm_timeout
        # 每个联系人一个 generator（懒创建）。self.gen 留作兼容，正常路径不用。
        self._gens: dict[str, FeizhiReplyGenerator] = {}
        self._gens_lock = threading.Lock()
        # 多用户并发：不同人并行，同一个人串行（靠 PeerState.lock）
        self._pool = ThreadPoolExecutor(max_workers=PEER_WORKERS,
                                        thread_name_prefix="peer")
        # ★ 在途消息（(peer, msg_id, local_id)）。并发化之后主循环不再等
        #   _handle_batch 跑完，而 mark_processed 要等回复入队才调用 ——
        #   中间这几秒里 poll_new 会把同一条消息**再取一次**，
        #   于是同一条被处理两遍、生成两组措辞相近的回复发出去。
        #   实测：<OWNER>说「没听，现在回宿舍了早就」，她在 20:49:22 和 20:49:39
        #   各回了一条，内容几乎一样。
        self._inflight: set[tuple[str, str, str]] = set()
        self._inflight_lock = threading.Lock()
        # ★ 2026-10-28 多用户：私有状态按联系人分，共享状态只有一份。
        #   peers   —— 每个 wxid 一套 memory（facts/events）和 life 私有层
        #              （shared/influences/open_loops），路径 state/peers/<wxid>/
        #   life_shared —— 她自己的日子（projects/mood/last_tick），全进程唯一，
        #              life tick 只写这份。谁来找她，面对的都是同一份现实。
        self.peers = get_registry()
        self.life_shared = self_life()
        # 全量历史 + 超限压缩（不再按固定条数截断）
        self.compactor = HistoryCompactor()
        LOG.info("历史摘要：%s", self.compactor.stats())
        # 她的日常生活状态（连续性）。首次运行给两件正在进行的小事，免得"没有生活"。
        if self.life_shared.seed_if_empty():
            LOG.info("生活状态已初始化")
        LOG.info("生活状态：%s", self.life_shared.stats())
        # 已经把磁盘上存在的联系人状态加载进来（只读，不新建）
        known = self.peers.warm_from_disk()
        LOG.info("已知联系人 %d 个：%s", len(known), known or "(无)")
        # ★ 恢复上次没发完的回复（审查 R02）：放后台线程，别拖慢启动
        threading.Thread(target=self._recover_pending, name="outbound-recover",
                         daemon=True).start()
        # 图片密钥预热：首次需要从磁盘派生（约 18 秒，一次性），
        # 放后台先算好，免得他发第一张图时那条回复被拖住。
        threading.Thread(target=self._warm_image_key, name="img-key-warm",
                         daemon=True).start()
        self.stats = {"seen": 0, "replied": 0, "skipped": 0, "failed": 0}
        # 发送队列 + 单后台线程：
        # 拟人化的「反应延迟」可能有几十秒到几分钟（真人不总是秒回），
        # 若在主循环里 sleep，这段时间就收不到任何新消息——表现为「聊到一半卡住」。
        # 因此把发送整体挪到后台线程；单线程顺序消费，保证多条回复的先后顺序不乱。
        self._send_q: "queue.Queue" = queue.Queue()
        self._sender = threading.Thread(target=self._sender_loop, name="sender", daemon=True)
        self._sender.start()
        # 自动补表情的状态
        self._sticker_times: list[float] = []
        LOG.info("timing: %s", humanize.describe())

    def _gen_for(self, peer: str) -> FeizhiReplyGenerator:
        """取这个联系人的 generator（没有就建一个）。

        generator 是有状态的：context_text / memory_ctx / life_ctx / search_ctx
        都是每轮现写、随后被 generate_plan 读取。共用一份在并发下必然串味，
        所以按 peer 分开。它只是个薄壳（持有 llm 引用和两个配置），建造很便宜。
        """
        with self._gens_lock:
            g = self._gens.get(peer)
            if g is None:
                g = FeizhiReplyGenerator(llm=self.llm, timeout=self._llm_timeout,
                                         attempts=2)
                self._gens[peer] = g
            return g

    # ---------- 记忆 ----------
    def _extract_memory(self, peer: str) -> None:
        """后台更新长期记忆：够多新消息 + 够久没抽过，才真跑一次 LLM。"""
        st = self.peers.get(peer)
        try:
            r = st.memory.maybe_extract(self.store, peer, self.llm)
            if r.get("facts_added") or r.get("events_added"):
                LOG.info("记忆抽取：%s", r)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("记忆抽取异常（忽略）: %s", exc)
        # 抽完顺手体检。**纯本地计算**（只读 memory + 正则/相似度），
        # 不调模型、不改任何记录，失败也不影响这次回复。
        self._reflect_memory(peer)

    def _reflect_memory(self, peer: str) -> None:
        """记忆体检：把过期/重复等缺陷写成 state/reflection.json，供人审阅。

        ★ 只诊断不执行。`memrec.add_record` 规定 needs_review 由程序判定、
          不接受自报，反思层若回写记录字段等于绕过闸门契约。
          真要动手改记忆，走人工审阅后的 CRUD 入口。
        """
        try:
            r = reflect.maybe_reflect(self.peers.get(peer).memory)
            if r.get("ok") and r.get("actionable"):
                LOG.info("记忆体检：%d 条待处理 %s", r["actionable"], r.get("summary"))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("记忆体检异常（忽略）: %s", exc)

    # ---------- 过滤 ----------
    def should_reply(self, msg: InboundMessage) -> tuple[bool, str]:
        incoming, how = resolve_direction(msg)
        if not incoming:
            return False, "not_incoming(%s)" % how
        if not msg.is_text:
            # 非文本消息里有两种"能听懂/能看见"：
            #   type=34 语音 —— voice_in 点开播放、抓 PCM、转文字
            #   type=3  图片 —— img_dat 解密本地缓存、vision 识别成一句描述
            # 其他类型（表情/文件/分享卡片）仍不自动回。
            t = str(msg.raw.get("type"))
            if t not in (VOICE_TYPE, IMAGE_TYPE):
                return False, "not_text(type=%s)" % msg.raw.get("type")
        peer = msg.peer_wxid
        if _is_system_peer(peer):
            return False, "system_peer(%s)" % peer
        if self.allow and peer not in self.allow:
            return False, "not_allowed(%s)" % peer
        # 群消息暂不自动回复（避免刷屏）
        if msg.is_group:
            return False, "group_room"
        return True, "ok"

    # ---------- 回复 ----------
    def _send_one(self, peer: str, text: str) -> bool:
        """发送一条回复内容。

        三种形态（都要求整条回复只写它）：
          `[img:名字]`   -> 发**本地图片库**里的图（type=10，GIF 会被静态化）
          `[draw:场景]`  -> **现场生成**一张照片再发（慢，见 imagegen 模块说明）
          其它            -> 按普通文本发送
        """
        import re as _re
        raw = text or ""

        # ★ 混排修正：模型有时把 `[voice:...]` 夹在文字后面（不合规范，但实测常发生
        #   —— 2026-10-27 22:10 那条就是「宝宝，这遍我录好啦… [voice:害羞:…]」）。
        #   整条 fullmatch 会失配 → 落到兜底把标记剥掉 → 只剩文字，语音凭空消失，
        #   而她嘴上已经说"录好啦"。这里先拆成「文字」「语音标记」两条分别发。
        if "[voice:" in raw and not _re.fullmatch(r"\s*\[voice:.+\]\s*", raw, _re.S):
            _mv = _re.search(r"\[voice:\s*[^\]]+\]", raw, _re.S)
            if _mv:
                head = raw[:_mv.start()].strip()
                tail = raw[_mv.start():].strip()
                LOG.info("混排拆分：文字 %d 字 + 语音标记", len(head))
                ok_all = True
                if head:
                    ok_all = self.bridge.send_text(peer, head)
                    if ok_all:
                        self.store.add(peer, "assistant", head, "auto_reply",
                                       "out:{}:{}".format(peer, int(time.time() * 1000)))
                if tail:
                    ok_all = self._send_one(peer, tail) and ok_all
                return ok_all

        # `[voice:档位:文本]` / `[voice:文本]` -> 合成一条**语音消息**发出去
        # 档位见 voice.MOODS（傲娇/心虚/委屈/温柔/慵懒/开心/强撑/娇嗔）
        mv = _re.fullmatch(r"\s*\[voice:\s*([^\]:\s]{1,10})\s*:\s*(.+?)\s*\]?\s*", raw, _re.S)
        if mv:
            vmood, vtext = mv.group(1), mv.group(2).strip()
        else:
            mv2 = _re.fullmatch(r"\s*\[voice:\s*(.+?)\s*\]?\s*", raw, _re.S)
            vmood, vtext = (None, mv2.group(1).strip()) if mv2 else (None, None)
        if vtext:
            try:
                import voice as _voice
            except Exception as exc:  # noqa: BLE001
                LOG.warning("语音模块不可用（%s），回落文字", exc)
                return self.bridge.send_text(peer, vtext)
            # ★ 语音必须短。2026-10-19 实测：模型给了 55 个字，TTS 出来
            #   21.28 秒（340480 样本），按住说话要按 21 秒才发得完，
            #   中途任何一次按键没落到微信就整条失败。
            #   真人发语音也就是五六秒到十几秒，超过 40 字就掐掉。
            if len(vtext) > VOICE_MAX_CHARS:
                LOG.info("语音太长（%d 字），截到 %d 字", len(vtext), VOICE_MAX_CHARS)
                vtext = vtext[:VOICE_MAX_CHARS].rstrip("，,、…～~ ") + "…"
            # ★ 审查 R04：语音是「按住键、对着当前打开的会话录音」，
            #   不像文本那样带 to_wxid —— 前台窗口不是他的话就会发错人。
            #   桥没有"查当前会话"的接口（要改 DLL），退一步用时间窗近似：
            #   她发语音只发生在刚收到他消息之后，所以要求最近 5 分钟内他确实说过话，
            #   否则降级为文字（宁可少发一条语音，不能发错人）。
            if not self._peer_looks_active(peer, within_sec=300):
                LOG.warning("最近 5 分钟没收到 %s 的消息，语音降级为文字", peer)
                return self.bridge.send_text(peer, vtext)
            LOG.info("发送语音 mood=%s text=%r", vmood, vtext[:40])
            if _voice.say(vtext, vmood, peer):
                self.store.add(peer, "assistant", "[语音]%s" % vtext, "auto_reply",
                               "out:{}:{}".format(peer, int(time.time() * 1000)))
                return True
            LOG.warning("语音发送失败，回落为文字")
            return self.bridge.send_text(peer, vtext)

        # `[sing:曲名]` -> 从 RVC 翻唱曲库里取一段，当语音条发出去
        # 曲库：sing/*_mix.wav（离线管线产出，只有 *_final 成品会进 prompt）
        ms = _re.fullmatch(r"\s*\[sing:\s*([^\]]+?)\s*\]\s*", raw)
        if ms:
            title = ms.group(1).strip()
            # ★ 唱歌和发语音走的是同一条路：按住说话、对着**当前打开的会话**录音，
            #   不像文本那样带 to_wxid。窗口不在他那儿就等于唱给别人听。
            #   所以套用与语音完全相同的 5 分钟时间窗保护（审查 R04）。
            if not self._peer_looks_active(peer, within_sec=300):
                LOG.warning("最近 5 分钟没收到 %s 的消息，唱歌降级为文字", peer)
                return self.bridge.send_text(peer, "本来想给你唱《%s》的，等会儿吧。" % title)
            LOG.info("唱歌：《%s》", title)
            if sing.sing(title, peer=peer):
                self.store.add(peer, "assistant", "[翻唱]《%s》" % title, "auto_reply",
                               "out:{}:{}".format(peer, int(time.time() * 1000)))
                return True
            LOG.warning("唱歌失败：《%s》（曲库=%s）", title, sing.catalog_text())
            return self.bridge.send_text(peer, "《%s》没唱成…下次补给你。" % title)

        # `[sticker:名字]` -> 发**微信原生表情**（真表情消息，不是图片）
        # 名字见 stickers.FAV_TEMPLATES / PACK_TEMPLATES（也接受 fav0..6 / pack0..3 / 纯数字）
        m = _re.fullmatch(r"\s*\[sticker:\s*([^\]]+?)\s*\]\s*", raw)
        if m:
            key = m.group(1)
            hit = stickers.find_sticker(key)
            if not hit:
                LOG.warning("sticker 未找到: %r", key)
                return False
            sk_kind, sk_idx = hit
            LOG.info("发送表情 kind=%s idx=%d", sk_kind, sk_idx)
            if self.bridge.send_sticker(peer, sk_idx, sk_kind):
                self.store.add(peer, "assistant", "[表情]%s" % key, "auto_reply",
                               "out:{}:{}".format(peer, int(time.time() * 1000)))
                return True
            LOG.warning("表情发送失败 kind=%s idx=%d", sk_kind, sk_idx)
            return False

        m = _re.fullmatch(r"\s*\[img:\s*([^\]]+?)\s*\]\s*", raw)
        if m:
            p = stickers.find_image(m.group(1))
            if not p:
                LOG.warning("image not found: %r (dir=%s)", m.group(1), stickers.IMAGE_DIR)
                return False
            ok = self.bridge.send_image(peer, str(p))
            if ok:
                self.store.add(peer, "assistant", "[图片]%s" % p.name, "auto_reply",
                               "out:{}:{}".format(peer, int(time.time() * 1000)))
            else:
                LOG.warning("send image failed: peer=%s file=%s", peer, p.name)
            return ok

        m = _re.fullmatch(r"\s*\[draw:\s*([^\]]+?)\s*\]\s*", raw)
        if m:
            scene = m.group(1)
            if random.random() > DRAW_KEEP_PROB:
                # 生成一次要 1~3 分钟且消耗额度，用概率闸门避免被滥用
                LOG.info("跳过本次生成（概率闸门 %.2f）: %r", DRAW_KEEP_PROB, scene[:40])
                return False
            LOG.info("开始生成照片: %r", scene[:60])
            t0 = time.time()
            path = imagegen.generate(imagegen.build_prompt(scene))
            if not path:
                LOG.warning("生图失败，改为发一句文字兜底")
                return self.bridge.send_text(peer, "算了，拍糊了，下次给你看")
            LOG.info("照片已生成 %.1fs -> %s", time.time() - t0, Path(path).name)
            ok = self.bridge.send_image(peer, str(path))
            if ok:
                self.store.add(peer, "assistant", "[照片]%s" % Path(path).name,
                               "auto_reply",
                               "out:{}:{}".format(peer, int(time.time() * 1000)))
            else:
                LOG.warning("发送生成图失败: %s", path)
            return ok

        # ★ 最后一道防线：走到这里说明前面所有标记形态都没匹配上。模型少写一个
        #   `]` 就会落到这儿，把 `[voice:害羞:……` 原样发给用户（2026-10-27 22:01 实测）。
        #   所以先把残留标记剥掉再发；剥完为空就整条丢掉，绝不发标记。
        safe = _strip_internal_markers(text)
        if not safe:
            LOG.warning("清洗后没有可发的正文，这一条丢掉: %r", text[:80])
            return False
        if safe != text:
            LOG.warning("兜底剥掉未解析的内部标记: %r -> %r", text[:60], safe[:60])
        return self.bridge.send_text(peer, safe)

    def _send_llm_sticker(self, peer: str, name: str | None) -> bool:
        """发 LLM 自己决定的表情。

        ★ 决策权在 LLM（它懂语境），代码只做两件事：
          1. 冷却，防止刷屏（窗口内最多 STICKER_MAX_IN_WINDOW 个）
          2. 把名字翻译成模板序号
        早期版本用关键词表配表情（"赢了"→不高兴…），过于机械 —— 同一句话该配什么，
        取决于当下的语境和她的情绪，规则表定不了。已改成模型决定。
        """
        if not name:
            return False
        now = time.time()
        self._sticker_times = [t for t in self._sticker_times if now - t < STICKER_WINDOW]
        if len(self._sticker_times) >= STICKER_MAX_IN_WINDOW:
            LOG.info("表情冷却中，本轮跳过（LLM 想要 %s）", name)
            return False
        hit = stickers.resolve_name(name)
        if not hit:
            LOG.warning("LLM 给的表情名不认识: %r", name)
            return False
        sk_kind, sk_idx = hit
        if not self.bridge.send_sticker(peer, sk_idx, sk_kind):
            LOG.warning("表情发送失败: %s", name)
            return False
        self._sticker_times.append(now)
        LOG.info("按 LLM 判断发表情: %s（%s）", name, sk_kind)
        self.store.add(peer, "assistant", "[表情]%s" % name, "auto_reply",
                       "out:{}:{}".format(peer, int(time.time() * 1000) + 500))
        return True

    def _send_plan(self, peer: str, plan, incoming: str = "",
                   sticker: str | None = None, image: str | None = None) -> int:
        """按拟人时序分段发送。

        ★ 时序在这里现算，**不要去改 plan.messages[i] 的字段** ——
        那些消息对象是不可变 dataclass，赋值会直接抛
        "cannot assign to field 'think_before_ms'"，导致每条消息都回复失败
        （2026-10-14 15:25 踩过：整整三小时一条都没发出去）。

        这里的 sleep 由后台发送线程执行，不会阻塞收消息的主循环。
        """
        sent = 0
        now = datetime.now()
        for i, m in enumerate(plan.messages):
            text = getattr(m, "text", "") or ""
            # ★ 对外输出检查：实测模型会把 system prompt 段落或 plan 结构直接吐出来
            #   （2026-10-25 见过 1428 字的「【你的来处…】」原文）。
            #   这里查的是**实际要发出去的文本**，任何一条不过就不发这一条。
            text, gstate = outguard.guard(
                text,
                regenerate=(lambda: self._regenerate_text(incoming, peer)) if incoming else None,
                log=LOG.warning)
            if not text:
                LOG.warning("outguard：这一条没有可用文本，跳过")
                continue
            if gstate != "pass":
                LOG.info("outguard 处置=%s -> %r", gstate, text[:40])
            think_ms = (humanize.reaction_delay_ms(len(text), now)
                        if i == 0 else humanize.gap_delay_ms())
            typing_ms = humanize.typing_delay_ms(text)
            if think_ms:
                time.sleep(think_ms / 1000.0)
            if typing_ms:
                time.sleep(typing_ms / 1000.0)
            ok = self._send_one(peer, text)
            if ok:
                sent += 1
                # ★ 语音/图片/表情在 _send_one 内部已经写过库了，这里只记普通文本。
                #   否则同一条消息会存两条（实测 14:48 的语音就出现了
                #   「[语音]xxx」+「[voice:傲娇:xxx]」双份记录）。
                # ★ 2026-10-27：混排拆分（「文字 [voice:…]」）在 _send_one 里已经把
                #   文字部分写进库了，所以这里不只看前缀，**任何位置**含标记都跳过。
                _INNER = ("[voice:", "[sing:", "[draw:", "[img:", "[sticker:")
                if not (text.lstrip().startswith(_INNER)
                        or any(k in text for k in ("[voice:", "[sing:", "[draw:", "[img:"))):
                    self.store.add(
                        peer, "assistant", text, "auto_reply",
                        "out:{}:{}".format(peer, int(time.time() * 1000) + i),
                    )
                    # ★ 她问出口的问题登记成「待回访」：真人记得自己问过什么、
                    #   对方还没答；过几小时聊天或主动找他的时候能接上
                    #   「那个到底弄完没」。只在真正发出去之后登记。
                    # ★ 边界感（2026-10-28 用户要求）：只对熟人以上登记「待回访」。
                    #   陌生人刚加就被几小时后追问"你上次那个到底怎样了"，
                    #   不是关心，是越界。stranger 阶段她只回应、不追问。
                    try:
                        _lp = self.peers.get(peer)
                        if _lp.relation.level != "stranger":
                            _lp.life.add_loop(text)
                    except Exception as exc:  # noqa: BLE001
                        LOG.warning("登记待回访失败: %r", exc)
            else:
                LOG.warning("send failed: peer=%s text=%r", peer, text[:40])
        if sent and image:
            # LLM 决定发图（自己的照片 / 网络表情包）。与 sticker 互斥，image 优先。
            try:
                if self._send_one(peer, "[img:%s]" % image):
                    LOG.info("按 LLM 判断发图: %s", image)
                else:
                    LOG.warning("LLM 要发的图没找到: %s", image)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("发图异常: %s", exc)
        elif sent and sticker:
            # 文字发完再发 LLM 决定的表情（表情是单独一条消息）
            try:
                self._send_llm_sticker(peer, sticker)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("发表情异常: %s", exc)
        return sent

    def _regenerate_text(self, incoming: str, peer: str = "") -> str:
        """输出检查不通过时，最多重新生成一次（只取第一条文本）。

        用当前 gen 的上下文再跑一遍；结果仍会被 outguard 再检查一次，
        所以即使上下文已被后续轮次改过、生成质量下降，也不会漏过去。
        """
        try:
            # 重新生成也必须用这个联系人的 generator：借用共享那份会把
            # 原轮的 memory_ctx / life_ctx 带走，重生成出来是别人的语气。
            _g = self._gen_for(peer) if peer else self.gen
            plan = _g.generate_plan(incoming, [])
        except Exception as exc:  # noqa: BLE001
            LOG.warning("outguard 重新生成失败: %r", exc)
            return ""
        for m in getattr(plan, "messages", []) or []:
            t = getattr(m, "text", "") or ""
            if t:
                return t
        return ""

    def _has_newer_for(self, peer: str) -> bool:
        """发送队列里是否还排着同一联系人的更新回复。

        用来实现「打断改口」：他在这条回复还卡在拟人延迟里的时候又说了话，
        说明她想说的已经过时了 —— 真人也这样，字打到一半看见新消息，
        会把输入框清空重打，而不是把过时的那句先发出去。
        """
        try:
            with self._send_q.mutex:
                return any(it and it[0] == peer for it in self._send_q.queue)
        except Exception:  # noqa: BLE001
            return False

    def _sender_loop(self) -> None:
        """后台顺序发送：收到 (peer, plan, msg) 后按拟人时序发出去并更新统计。"""
        while True:
            item = self._send_q.get()
            if item is None:
                break
            peer, plan, msg, sticker, image, oid = item
            try:
                # ★ 打断改口：队列里还有同一联系人的更新回复 → 这条整条丢弃。
                #   判断放在真正发送之前，所以不会出现「发了半句就不发了」。
                if self._has_newer_for(peer):
                    LOG.info("回复已过时，跳过（这期间他又说了话）: peer=%s", peer)
                    if oid:
                        self.store.mark_outbound(oid, "superseded",
                                                 "被更新的入站消息替代")
                    self.stats["skipped"] += 1
                    continue
                sent = self._send_plan(peer, plan, msg.content, sticker, image)
                if sent:
                    self.stats["replied"] += 1
                    LOG.info("replied to %s with %d message(s)", peer, sent)
                    self.bridge.mark_processed(msg)
                    if oid:
                        self.store.mark_outbound(oid, "submitted")
                else:
                    # 不再只是"记一句将重试"：任务表里标 failed，下一轮恢复会重新入队
                    LOG.warning("发送失败（已记入任务表，稍后恢复重试）: peer=%s", peer)
                    self.stats["failed"] += 1
                    if oid:
                        self.store.mark_outbound(oid, "failed", "send_plan 返回 0 段")
            except Exception as exc:  # noqa: BLE001
                LOG.exception("send_plan error: %s", exc)
                self.stats["failed"] += 1
                if oid:
                    self.store.mark_outbound(oid, "failed", repr(exc)[:200])
            finally:
                self._send_q.task_done()

    def _recover_pending(self) -> None:
        """把上次没发完的回复重新发出去（审查 R02）。

        直接按文本段发送，不重建 plan —— 恢复只需要"把那句话说出来"。
        in_flight 超时的任务已被 recover_outbound 标成 unknown，这里不捞
        （结果不明时不能盲目重发，会变成重复消息）。
        """
        try:
            rec = self.store.recover_outbound()
            LOG.info("出站任务状态：恢复 %s，分布 %s", rec, self.store.outbound_stats())
        except Exception as exc:  # noqa: BLE001
            LOG.warning("recover_outbound 失败: %r", exc)
            return

        tasks = self.store.claim_outbound(limit=20)
        if not tasks:
            return
        LOG.info("准备恢复发送 %d 条未完成的回复", len(tasks))
        for t in tasks:
            texts = [m.get("text") for m in t["payload"].get("messages", []) if m.get("text")]
            if not texts:
                self.store.mark_outbound(t["id"], "unknown", "payload 里没有文本")
                continue
            ok = True
            for tx in texts:
                if not self.bridge.send_text(t["peer_wxid"], tx):
                    ok = False
                    break
                time.sleep(0.5)
            self.store.mark_outbound(t["id"], "submitted" if ok else "failed",
                                     "" if ok else "恢复发送失败")
            LOG.info("恢复任务 #%s -> %s（%d 段）", t["id"], "成功" if ok else "失败", len(texts))

    def _advance_life(self) -> None:
        """她的一天自己往前走 ———— 和谁说了话、有没有人找她，都无关。

        ★ 2026-10-28 因果纠正：原来是 `_advance_life(peer)`，把那个人最近 12 条
          历史拼成 snippet 喂给 life.tick()，等于是「有人聊天才推进她的一天」。
          她只有一份人生，不该由别人的消息驱动。现在只按时间推进，
          触发点也从「回复完之后」挪到主循环里定时检查（见 run_forever）。
        """
        try:
            if not self.life_shared.need_tick():
                return
            r = self.life_shared.tick(self.llm)
            if r and not r.get("skipped") and not r.get("error"):
                LOG.info("生活状态已推进：%s", r)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("生活推进异常（忽略）: %s", exc)

    def _transcribe_voice(self, msg: InboundMessage) -> str:
        """把语音消息转成文字（自动点播放 → 抓 PCM → ASR）。

        入库的是**转写后的文字**而不是原始 XML —— 这样上下文里她看到的是
        「他说的内容」，而不是一坨 voicemsg 标签。
        听不清时返回一句占位，让她自己说「没听清」，而不是卡死。
        """
        sec = 0.0
        import re as _re
        m = _re.search(r'voicelength="(\d+)"', msg.content or "")
        if m:
            sec = int(m.group(1)) / 1000.0
        LOG.info("收到语音（%.1f 秒），开始自动转写…", sec)
        try:
            import voice_in
            text, _wav = voice_in.transcribe(expected_sec=sec)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("语音转写异常: %s", exc)
            text = ""
        if text:
            LOG.info("语音转写成功: %r", text[:60])
            return text
        LOG.warning("语音转写失败（听不清）")
        return "[他发了条语音，我没听清]"

    def _warm_image_key(self) -> None:
        """启动时把图片 AES key 备好（首次要从磁盘派生，约 18 秒，一次性）。

        不预热也不会错，只是他发第一张图时那条回复会多等十几秒。
        """
        try:
            key = img_dat.extract_aes_key()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("图片密钥预热异常: %s", exc)
            return
        if key:
            LOG.info("图片密钥就绪，收到图片可以直接识别")
        else:
            LOG.warning("图片密钥未就绪 —— 收到图片时只能回「没打开」")

    def _describe_image(self, msg: InboundMessage) -> str:
        """把图片消息变成一句她能"看见"的描述。

        链路：inbox 里的 XML **只有加密的 CDN 指针，没有本地路径**，所以绕开它走
        微信自己的缓存 —— `msg/attach/<md5(peer_wxid)>/<YYYY-MM>/Img/*.dat`，
        由 img_dat 解出明文（V2: AES 段 + 明文段 + XOR 段），
        再交给 vision（claude-sonnet）识别成中文描述。

        任何一步失败都退回一句占位，让她照常说"这边没打开"，
        绝不让一张图把整条回复卡死。
        """
        try:
            got = img_dat.resolve_image(msg.peer_wxid, msg.timestamp, msg.content)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("图片解密异常: %s", exc)
            got = None
        if not got:
            LOG.warning("这张图拿不到明文（缓存未命中或图片密钥未就绪），用占位")
            return "[他发来一张图片，我这边没打开]"
        path, plain, _ext = got
        LOG.info("图片已解密 %s（%.1f KB），开始识别…", path.name, len(plain) / 1024)
        desc = vision.describe_bytes(plain)
        if not desc:
            return "[他发来一张图片，我这边没打开]"
        LOG.info("图片识别成功: %r", desc[:60])
        return "[他发来一张图片：%s]" % desc

    def _peer_looks_active(self, peer: str, within_sec: float = 900.0) -> bool:
        """最近这个时间窗内，他有没有说过话。

        ★ 2026-10-29：窗口从 300 秒放宽到 900 秒。原因是 `last_user_at` 用的是
          消息自带的时间戳，而从"他发出去"到"我们处理"实测能差 5 分钟
          （12:55 发的，13:00:45 才走到发语音那一步），300 秒窗口会把正常情况
          判成"他没说话"，于是唱歌被降级成文字 —— 用户的原话是"她怎么不回我"。

        用来给「没有目标地址」的操作（语音按键）兜一层：
        桥只能操作"当前打开的会话"，所以只能靠"刚刚确实是他在说话"来近似判断。
        """
        try:
            last_user = self.store.last_user_at(peer)
        except Exception:  # noqa: BLE001
            return False
        if not last_user:
            return False
        return (time.time() * 1000 - last_user) <= within_sec * 1000

    def _should_end_quietly(self, msg: InboundMessage, content: str) -> bool:
        """这一轮要不要干脆不接话（真人不会每句都应）。

        只有三个条件同时成立才可能不回，避免把"她不回我"变成 bug：
          1. 他发的只是纯应答词（嗯/哦/好/哈哈…），没有新信息
          2. 距她上一条不超过几分钟（同一次对话里的收尾，不是把他晾着）
          3. 概率闸门（默认 25%）
        语音、带媒体、长句一律照常回。
        """
        if not QUIET_END_ENABLED:
            return False
        raw = (content or "").strip()
        # 带问号的是在等回答（「好？」「行不行？」），必须接。
        if "？" in raw or "?" in raw:
            return False
        t = raw.strip("。，！？…~～、 .,!?")
        if not t or len(t) > 4 or t not in QUIET_END_WORDS:
            return False
        try:
            last = self.store.last_assistant_at(msg.peer_wxid)
        except Exception:  # noqa: BLE001
            return False
        if not last:
            return False
        gap_min = (time.time() * 1000 - last) / 60000.0
        if gap_min < 0 or gap_min > QUIET_END_MAX_GAP_MIN:
            return False
        return random.random() < QUIET_END_PROB

    def handle(self, msg: InboundMessage) -> bool:
        self.stats["seen"] += 1
        ok, why = self.should_reply(msg)
        if not ok:
            # 原来这里是 LOG.debug —— INFO 级别下完全不可见，等于拒绝原因是黑盒。
            LOG.info("skip %s peer=%r type=%s: %s", msg.msg_id, msg.peer_wxid,
                     msg.raw.get("type"), why)
            self.stats["skipped"] += 1
            self.bridge.mark_processed(msg)   # 明确决定不处理，标记以免反复检查
            return False

        peer = msg.peer_wxid
        # 语音先转文字、图片先识别（都慢，5~10 秒；期间主循环会等，
        # 新消息暂存在 inbox 里不丢）
        content = msg.content
        msg_type = str(msg.raw.get("type"))
        if msg_type == VOICE_TYPE:
            content = self._transcribe_voice(msg)
        elif msg_type == IMAGE_TYPE:
            content = self._describe_image(msg)

        key = "in:{}:{}:{}".format(peer, msg.msg_id, msg.timestamp)
        fresh = self.store.add(peer, "user", content, "inbound", key,
                               sent_at_ms=msg.timestamp * 1000 if msg.timestamp else None)
        retry_mode = False
        if not fresh:
            # ⚠️ 「已记录 inbound」≠「已回复」。两者的 key 是同一套，早期把它们
            # 混为一谈：只要 handle() 进过一次（哪怕随后 LLM 失败、或进程被杀），
            # 重试时就会被判重复直接丢弃 —— 表现为「消息明明收到了却永远不回」。
            # 这里用「该联系人最后一条回复的时间」判断是否真的回过。
            #
            # 但**必须立刻 mark_processed**：否则同一轮询周期会反复取到这条消息，
            # 造成「重试风暴」（实测一条消息连调 6 次 LLM、发出两组重复回复）。
            # 所以重试只补一次，成败都标记，不进入无限循环。
            inbound_ms = (msg.timestamp or 0) * 1000
            try:
                last_reply = self.store.last_assistant_at(peer)
            except Exception:  # noqa: BLE001
                last_reply = 0
            if last_reply and inbound_ms and last_reply >= inbound_ms:
                LOG.info("duplicate inbound ignored（已回复过）: %s", key)
                self.stats["skipped"] += 1
                self.bridge.mark_processed(msg)
                return False
            # ★★ 2026-10-29：这里必须加时间门槛，否则「正在处理」会被当成「处理失败」。
            #   实测：<OWNER> 12:55 发的消息，13:00:33 开始处理，LLM 花了 2 秒，
            #   这 2 秒里下一轮轮询又取到同一条（mark_processed 还没执行），
            #   于是判「此前未成功」补发一次 —— 同一条消息回了两遍，措辞不同意思一样。
            #   真人不会因为对方等了 30 秒就再说一遍，所以 3 分钟内的重复一律当在处理。
            _age = time.time() - float(msg.timestamp or 0)
            if 0 <= _age < 180:
                LOG.info("这条还在处理中（消息 %.0fs 前），不补发: %s", _age, key)
                self.bridge.mark_processed(msg)
                return False
            retry_mode = True
            LOG.info("此前处理未成功（消息已 %.0fs），补一次回复: %s", _age, key)
            self.bridge.mark_processed(msg)      # 关键：先标记，避免风暴

        # ★ 每个联系人一个 generator 实例（2026-10-28 多用户）：
        #   generator 身上挂着 context_text / memory_ctx / life_ctx / search_ctx
        #   四个字段，共用一份的话并发时 A 的记忆块会覆盖 B 的，回复串味。
        gen = self._gen_for(peer)
        LOG.info("inbound from %s: %r", peer, content[:60])
        # 他回话了：之前挂念的事从「他还没接这个话」变成「他说过了、但还没说结果」，
        # 这正是回访最自然的时机（"那最后到底成了没"）。
        try:
            self.peers.get(peer).life.note_answered()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("更新待回访状态失败: %r", exc)
        # 允许安静结束：他发的只是「嗯/哦/好」而且刚聊完 —— 这一轮可以不接。
        # 消息已经入库了，所以下一轮她还"看过"这句话，只是这次没回。
        if self._should_end_quietly(msg, content):
            LOG.info("这次选择不接话（纯应答 + 刚聊过）: %r", content[:20])
            self.stats["skipped"] += 1
            self.bridge.mark_processed(msg)
            return False
        # 取 80 条给 generate_plan 里的 select_history 筛选（它按话题挑，
        # 但原版上限写死 12 条 —— 实际喂给模型的只有 6 轮对话，早已放宽到 40）。
        history = self.store.history(peer, limit=80)
        # history 最后一条就是刚写入的 user 消息，生成时需要去掉
        history = history[:-1] if history else []

        # 全量上下文：不设固定条数，超预算时 compactor 把早期聊天压成摘要
        try:
            hc = self.compactor.build(self.store, peer, self.llm)
            gen.context_text = render_context(hc["summary"], hc["raw"])
            if hc["compacted"]:
                LOG.info("历史已压缩：摘要 %d 字 + 保留原文 %d 条",
                         len(hc["summary"]), len(hc["raw"]))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("历史压缩失败（退回按条数）：%s", exc)
            gen.context_text = ""

        # ★ 关系档位与称呼：**必须在 NO_MEMORY 判断之外**（2026-10-28）。
        #   放进去的话，一开纯模型测试模式（FEIZHI_NO_MEMORY=1）档位就不刷新，
        #   陌生人会继承上一个人的恋人档位 —— 对刚加的人喊"宝宝"，一次就穿帮。
        #   出错也按最保守的 stranger 走，宁可客气。
        _st_now = None
        try:
            _st_now = self.peers.get(peer)
            gen.relation = _st_now.relation.level
            gen.peer_name = _st_now.relation.display_name(peer)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("关系档位读取失败，按 stranger 处理: %s", exc)
            gen.relation = "stranger"
            gen.peer_name = peer

        # 长期记忆注入（渲染失败绝不能影响回复）
        # ★ FEIZHI_NO_MEMORY=1 时不注入。2026-10-27 起进入「纯模型语音测试」阶段：
        #   记忆里的旧事（海报改到第几版、糊糊干过什么）会让回复变成复述，
        #   干扰对语速 / 情感 / 人机感的判断。此时也在 _extract_memory 里停掉写入。
        if os.environ.get("FEIZHI_NO_MEMORY") == "1":
            gen.memory_ctx = ""
        elif _st_now is not None:
            try:
                gen.memory_ctx = _st_now.memory.render()
            except Exception as exc:  # noqa: BLE001
                LOG.warning("记忆渲染失败（忽略）: %s", exc)
                gen.memory_ctx = ""

        # 生活状态注入（聊天/主动/朋友圈共用同一份，不能各编一套）
        try:
            _st_life = self.peers.get(peer).life
            _st_life.reload_shared()     # 她的日子是共享的，每次拿最新那份
            # 陌生人看不到「你之前问过他……」那一段：那是关系痕迹，
            # 才刚加的人不该出现在她的挂念清单里。
            gen.life_ctx = _st_life.render(
                include_loops=(_st_now is not None
                               and _st_now.relation.level != "stranger"))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("生活状态渲染失败（忽略）: %s", exc)
            gen.life_ctx = ""

        # 需要查证的先联网检索，把结果喂给 LLM —— 不额外多一次调用：
        # 闲聊仍是 1 次，查证是「1 次搜索 + 1 次生成」。搜不到就什么都不加，
        # 退回按人格回一句（她本来也可以说"我哪儿知道"）。
        gen.search_ctx = ""
        if needs_search(msg.content):
            try:
                # 先把口语压成检索词（「你说那个X什么时候上映啊」→「X什么时候上映」），
                # 直接拿原句去搜命中率明显更差。
                q = search.build_query(msg.content)
                rows = search.web_search(q, limit=4)
                gen.search_ctx = search.format_for_llm(rows)
                if gen.search_ctx:
                    LOG.info("联网检索 %r -> %d 条", q[:24], len(rows))
                else:
                    # ★ 查了但没查到，**必须告诉模型"查过了"**。
                    #   以前这里留空字符串，模型完全不知道这一轮搜过 —— 于是
                    #   persona.SEARCH_STYLE 里写的「我查了没找到」永远不会发生，
                    #   她会当成普通闲聊直接答，或者干脆编一个。
                    #   空结果也要回传，这是工具调用最基本的语义。
                    gen.search_ctx = (
                        "（我按「%s」查过了，但没有找到可用结果）" % q)
                    LOG.info("联网检索无结果（已回传给模型）: %r", q[:24])
            except Exception as exc:  # noqa: BLE001
                LOG.warning("联网检索异常（忽略）: %s", exc)

        try:
            plan = gen.generate_plan(msg.content, history)
        except ReplyGenerationError as exc:
            # 生成失败不标记，下一轮会重试这条
            LOG.error("LLM 生成失败（将重试）: %s", exc)
            self.stats["failed"] += 1
            return False

        # 顺手在后台抽一次长期记忆（是否真跑由 memory 内部节流判断；失败只记日志）
        threading.Thread(target=self._extract_memory, args=(peer,), daemon=True).start()
        # 她的一天不在这里推进 —— 2026-10-28 起改由 run_forever 定时检查，
        # 与聊天无关（她的日子不该由别人的消息驱动）。

        # 交给后台线程顺序发送（拟人延迟在 _send_plan 里现算，不改 plan 对象）。
        # 这里立即返回，不等待发送完成 —— 否则长延迟会阻塞收消息的主循环。
        #
        # ★ 入队后立刻标记已处理：从入队到真正发完之间隔着几十秒的拟人延迟，
        #   期间下一轮轮询还会取到这条消息（seen 里没它），于是又被判一次
        #   「此前未成功 → 补一次」，造成每条消息处理两遍、LLM 白调一次。
        #   发送失败的重试交给 sender 线程自己负责（它会把失败记进 stats）。
        sticker = getattr(self.gen, "pending_sticker", None)
        image = getattr(self.gen, "pending_image", None)
        if sticker:
            LOG.info("LLM 决定这一轮配表情: %s", sticker)
        if image:
            LOG.info("LLM 决定这一轮发图: %s", image)
        # ★ 先把这份计划落库（审查 R02）：旧流程只塞内存队列，
        #   发送失败、进程退出都会永久丢掉这条回复（实测发送失败后队列为空、
        #   重启也捞不回来）。落库后即使崩在几十秒的拟人延迟里，也能恢复重发。
        oid = 0
        try:
            oid = self.store.enqueue_outbound(
                peer,
                {"messages": [{"text": getattr(m, "text", "")} for m in getattr(plan, "messages", [])],
                 "sticker": sticker, "image": image},
                inbound_key=(msg.source_file or ""))
            LOG.debug("出站任务 #%d 已落库", oid)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("出站任务落库失败（仍继续发送，但这条无法恢复）: %r", exc)
        self.bridge.mark_processed(msg)
        self._send_q.put((peer, plan, msg, sticker, image, oid))
        return True

    # ---------- 主循环 ----------
    MERGE_WINDOW = 2.5   # 秒；对方连发多条时等这么久，合并成一次回复

    def _run_group(self, peer: str, msgs: list[InboundMessage]) -> None:
        """在线程池里处理某个联系人的一批消息。"""
        st = self.peers.get(peer)
        try:
            with st.lock:                   # 同一个人串行，不同人互不等待
                try:
                    self._handle_batch(msgs)
                except Exception as exc:  # noqa: BLE001
                    LOG.exception("handle error (peer=%s): %s", peer, exc)
                    self.stats["failed"] += 1
        finally:
            # 无论成败都要摘掉，否则这条消息永远被判成"在途"再也不会处理
            with self._inflight_lock:
                for m in msgs:
                    self._inflight.discard(
                        (m.peer_wxid, str(m.msg_id), str(m.local_id)))

    def _handle_batch(self, msgs: list[InboundMessage]) -> None:
        """一批入站消息：前面的只入库当上下文，由**最后一条能回复的**触发一次回复。

        ★ 真人也这样：对方连发「刚刚游戏赢了」+「好开心呀」，你不会各回一遍，
        而是等他说完一起回一次。之前对每条独立处理、各生成一次回复，
        实测 15:53 那轮就出现了两遍几乎一样的内容。

        ★★ 2026-10-15 22:51 踩坑修正：**不能硬取 msgs[-1]**。
        他连发了「一条文字 + 5 条分享卡片(type=49)」，最后一条不是文本，
        should_reply 直接 False，于是整批都不回复；而前面的文字已经被
        mark_processed 掉 —— 消息永久丢失（表现为「她不回我消息」）。
        现在改成**从后往前找最后一条能回复的**作为触发点。
        """
        if not msgs:
            return

        trigger = None
        for i in range(len(msgs) - 1, -1, -1):
            ok, _why = self.should_reply(msgs[i])
            if ok:
                trigger = i
                break

        if trigger is None:
            # 整批都不可回复（全是图片/分享/系统消息）：只计数、全部标记，不留悬挂
            # ★ 2026-10-28：原来只打一行「N 条都不可回复」，不带 peer/type/原因。
            #   结果每天早上 06:35 / 12:05 那几条被吞的消息查了几天都只能靠猜
            #   （DEBUG 日志在 INFO 级别下根本不出来，批量路径又完全不走 handle()）。
            #   这里把每条的身份和拒绝原因一起打出来，一眼能看出是谁、什么类型、卡在哪。
            for m in msgs:
                self.stats["seen"] += 1
                self.stats["skipped"] += 1
                _, _why = self.should_reply(m)
                LOG.info("整批不可回复：peer=%r type=%s sender=%r why=%s content=%r",
                         m.peer_wxid, m.raw.get("type"), m.sender_wxid,
                         _why, (m.content or "")[:40])
                self.bridge.mark_processed(m)
            LOG.info("这批 %d 条都不可回复，已标记", len(msgs))
            return

        # 触发点之前的：只入库当上下文（能入则入），不单独回复
        voiced = 0
        images = 0
        for m in msgs[:trigger]:
            self.stats["seen"] += 1
            ok, _why = self.should_reply(m)
            if ok:
                key = "in:{}:{}:{}".format(m.peer_wxid, m.msg_id, m.timestamp)
                # ★ 审查 R09：语音消息（type=34）的 content 是 XML 原文
                #   （`<msg><voicemsg voicelength="3000" …/></msg>`）。
                #   以前这里直接 store.add(m.content)，等于往上下文里塞一坨标签，
                #   模型看到的是尖括号而不是"他说了什么"，这条语音也就白发了。
                #   跟触发点走同一条转写路径；连发多条时给个预算，
                #   免得 5 条语音把主循环拖住半分钟。
                #   图片（type=3）同理：入库的必须是识别后的描述，不是 img 标签。
                text = m.content
                mt = str(m.raw.get("type"))
                if mt == VOICE_TYPE:
                    if voiced < BATCH_VOICE_LIMIT:
                        text = self._transcribe_voice(m) or "（语音没听清）"
                        voiced += 1
                    else:
                        text = "（连发语音，这条没来得及听）"
                        LOG.info("连发语音超出转写预算，先记为占位: %s", key)
                elif mt == IMAGE_TYPE:
                    if images < BATCH_IMAGE_LIMIT:
                        text = self._describe_image(m)
                        images += 1
                    else:
                        text = "[他连发了几张图片，这张没来得及看]"
                        LOG.info("连发图片超出识别预算，先记为占位: %s", key)
                self.store.add(m.peer_wxid, "user", text, "inbound", key,
                               sent_at_ms=m.timestamp * 1000 if m.timestamp else None)
                LOG.info("连发的第 %d 条只入库、不单独回复: %r", trigger, text[:36])
            self.bridge.mark_processed(m)

        # 触发点之后的：不能回，标记掉即可（内容进不了上下文，但也不该拖着）
        for m in msgs[trigger + 1:]:
            self.stats["seen"] += 1
            self.bridge.mark_processed(m)

        self.handle(msgs[trigger])

    def run_forever(self, poll_timeout: float = 10.0, idle_log_every: int = 30) -> None:
        LOG.info("auto-reply started; allow=%s", self.allow or "(all)")
        loops = 0
        last_life_check = 0.0
        while True:
            loops += 1
            try:
                # ★ 她的一天按时间自己往前走，不等任何人说话（2026-10-28）。
                #   每 3 分钟看一次 need_tick（内部按 6 小时间隔节流），
                #   LLM 调用丢到后台线程，免得把收消息的主循环卡住。
                if time.time() - last_life_check > 180:
                    last_life_check = time.time()
                    try:
                        if self.life_shared.need_tick():
                            threading.Thread(target=self._advance_life,
                                             name="life-tick", daemon=True).start()
                    except Exception as exc:  # noqa: BLE001
                        LOG.warning("生活推进检查异常（忽略）: %s", exc)
                msgs = self.bridge.wait_for_new(poll_timeout)
                if msgs:
                    # 再等一小会儿，看对方是不是还在接着发 —— 是的话合并处理
                    time.sleep(self.MERGE_WINDOW)
                    more = self.bridge.poll_new()
                    if more:
                        # 注意：InboundMessage 里有 raw: dict，不能直接丢进 set
                        # （frozen dataclass 的 hash 会因为 dict 抛 unhashable），
                        # 所以按字段元组去重。
                        seen = {(m.peer_wxid, m.msg_id, m.local_id) for m in msgs}
                        merged = list(msgs)
                        for m in more:
                            k = (m.peer_wxid, m.msg_id, m.local_id)
                            if k not in seen:
                                seen.add(k)
                                merged.append(m)
                        merged.sort(key=lambda m: (m.timestamp or 0, m.local_id))
                        LOG.info("合并连发消息 %d 条", len(merged))
                        msgs = merged
                if msgs:
                    # ★ 按联系人分组（2026-10-28 多用户）：不同人各自并行，
                    #   同一个人的连发仍然串行 —— 否则两条回复会互相踩上下文，
                    #   表现为对着同一句话答两遍、或者答到别人的话题上。
                    groups: dict[str, list[InboundMessage]] = {}
                    for m in msgs:
                        k = (m.peer_wxid, str(m.msg_id), str(m.local_id))
                        with self._inflight_lock:
                            if k in self._inflight:
                                continue          # 还在处理，别重复投递
                            self._inflight.add(k)
                        groups.setdefault(m.peer_wxid, []).append(m)
                    if not groups:
                        msgs = []
                    for peer_wxid, group in groups.items():
                        # 系统会话（newsapp / 文件传输助手 / 公众号…）在分组层就挡掉：
                        # 一进 _run_group 就会 peers.get() 建目录，白建一堆空壳。
                        if _is_system_peer(peer_wxid):
                            for m in group:
                                self.stats["seen"] += 1
                                self.stats["skipped"] += 1
                                self.bridge.mark_processed(m)
                            continue
                        self._pool.submit(self._run_group, peer_wxid, group)
                elif loops % idle_log_every == 0:
                    LOG.info("idle; hook_alive=%s worker=%s stats=%s",
                             self.bridge.hook_alive(),
                             self.bridge.worker_healthy(), self.stats)
            except KeyboardInterrupt:
                LOG.info("stopped by user; stats=%s", self.stats)
                break
            except Exception as exc:  # noqa: BLE001
                LOG.exception("loop error: %s", exc)
                time.sleep(3)
