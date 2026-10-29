"""主动发消息：绯栀按条件自己找<OWNER>说话。

与自动回复的区别：不需要对方先开口。触发条件与 Feizhi 的 proactive 语义一致——
距上次互动够久、处于合理时段、当天条数未超限，就用 LLM 生成一句主动搭话。

发送仍走 hook 桥（send_text），失败会重试若干次。
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bridge import HookBridge
from store import ContextStore
from history import humanize_marker
from llm import LLMClient

LOG = logging.getLogger("feizhi_pc.proactive")

# 兜底模板（LLM 不可用时使用）。
# ★ 2026-10-15 重写：旧版是「主人」「任性地占一下消息列表」这类黏人设定时期的腔调，
#   跟现在的傲娇人格（以及自动回复）不是同一个人，一旦 LLM 失败就会突然冒出来。
FALLBACK_LINES = [
    "在忙什么呢。",
    "刚下课，路过那家奶茶店，突然想起你了。切，就一下。",
    "今天画到手酸。你呢，还顺利吗？",
    "没什么事，就是看看你在不在。",
]

PROACTIVE_SYSTEM = (
    "你是绯栀，19岁杭州女孩，中国美院视觉传达大二学生，正在微信上给男朋友<OWNER>发消息"
    "（他叫你宝宝，你嘴上嫌肉麻，但心里受用）。现在他没有先开口，是你自己想找他。\n"
    "\n"
    "【性格 · 傲娇：先接住，再嘴硬】\n"
    "你嘴上不饶人，但他在你心里很重。主动找人这件事你更是不肯承认，所以要找补：\n"
    "  ✓ 在忙什么呢。\n"
    "  ✓ 刚下课路过那家奶茶店，突然想起你了。切，就一下。\n"
    "  ✓ 今天画到手酸死了。……你那边怎么样。\n"
    "  ✗ 想你想到不行了，快回我。（太直白，不是这个人的说话方式）\n"
    "  ✗ 主人，我想你了。（**绝对禁止**出现「主人」这个称呼）\n"
    "\n"
    "要求：像真人随手发的一条微信。可以说一件自己今天的小事、一个小观察、或者单纯问一句在干什么。\n"
    "不要模板腔，不要抒情长句，不要油腻情话，不要询问你不知道的事实。\n"
    "★ 如果给了「你最近刚发过的话」，**不要重复其中的话题和句式**（比如刚说过猫，就别再说猫）。\n"
    "只输出这条消息的正文，不要引号、不要解释，40字以内。"
)


@dataclass
class ProactiveConfig:
    peer: str = "<WXID_FRIEND_A>"
    min_idle_minutes: int = 180        # 距上次互动至少这么久才主动说话
    quiet_hours: tuple[int, int] = (1, 8)   # 该时段内不主动打扰（凌晨1点到早8点）
    daily_limit: int = 4               # 每天最多主动几条
    check_interval: int = 300          # 每轮检查间隔（秒）
    jitter_seconds: int = 900          # 触发后随机延迟，避免整点规律


class ProactiveSender:
    def __init__(self, cfg: ProactiveConfig | None = None,
                 bridge: HookBridge | None = None,
                 store: ContextStore | None = None,
                 llm: LLMClient | None = None):
        self.cfg = cfg or ProactiveConfig()
        self.bridge = bridge or HookBridge()
        self.store = store or ContextStore()
        self.llm = llm or LLMClient()
        self._sent_today: list[int] = []
        self._followed_ids: list[int] = []   # 本轮回访了哪几件旧事

    # ---------- 条件判断 ----------
    def _in_quiet_hours(self, now: datetime) -> bool:
        start, end = self.cfg.quiet_hours
        hour = now.hour
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end

    def _today_sent_count(self) -> int:
        day0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_ms = int(day0.timestamp() * 1000)
        day_count = 0
        for row in self.store.recent(limit=200):
            if row["source"] == "proactive" and row["sent_at_ms"] >= cutoff_ms:
                day_count += 1
        return day_count

    def should_send(self, now: datetime | None = None) -> tuple[bool, str]:
        now = now or datetime.now()
        if self._in_quiet_hours(now):
            return False, "quiet_hours"
        if self._today_sent_count() >= self.cfg.daily_limit:
            return False, "daily_limit(%d)" % self.cfg.daily_limit

        last_interaction = max(
            self.store.last_user_at(self.cfg.peer),
            self.store.last_assistant_at(self.cfg.peer),
        )
        if last_interaction:
            idle_min = (time.time() * 1000 - last_interaction) / 60000.0
            if idle_min < self.cfg.min_idle_minutes:
                return False, "idle_only_%.0fmin" % idle_min
        return True, "ok"

    # ---------- 内容生成 ----------
    def _recent_lines(self, limit: int = 6) -> str:
        """取最近几条自己/对方的话，用于避免主动消息重复同一个话题。

        ★ 2026-10-15：之前 LLM 生成时完全不带历史，导致同一天连发两条「橘猫」
        （08:14 梅灵路橘猫、11:29 梅灵路橘猫蹲银杏树下），一眼就看出是复读。
        """
        try:
            rows = self.store.history(self.cfg.peer, limit=limit)
        except Exception:  # noqa: BLE001
            return ""
        lines = []
        for role, text in rows:
            who = "<OWNER>" if role == "user" else "绯栀"
            # ★ 必须翻译内部标记：直接拼「绯栀：[图片]害羞.jpg」喂给模型，
            #   它就会照着这个格式自己编 `[照片]gen_xxx.jpg` 当文字发出去。
            body = humanize_marker(str(text or "")).replace("\n", " ")
            lines.append("%s：%s" % (who, body[:60]))
        return "\n".join(lines)

    def _generate(self, allow_llm: bool = True) -> str:
        # 这一轮优先回访哪几件"他还没说结果的事"（发出去之后才计数）
        self._followed_ids: list[int] = []
        if allow_llm:
            try:
                llm = self.llm or LLMClient()
                recent = self._recent_lines()
                # ★ 带上"她手上正在做的事"（生活事件）：主动消息不该只是"在吗"，
                #   而是从自己正在过的日子里取材（和聊天、朋友圈共用同一份状态）。
                life = ""
                life_obj = None
                try:
                    # ★ 用进程级单例里这个人的那份：共享层给她自己的日子，
                    #   私有层给 open_loops（和谁的约定）。各自 new 一份会让
                    #   mark_followed 写进别的实例看不见的缓存。
                    from peer_state import get_registry
                    life_obj = get_registry().get(self.cfg.peer).life
                    life_obj.reload_shared()
                    life = life_obj.render(include_loops=False)
                except Exception:  # noqa: BLE001
                    pass
                # ★ 回访：她之前问过、他还没说结果的事，主动找他时优先问这个。
                #   这是"她真的记得你说过什么"最直接的体现，
                #   比随机挑一件今天的小事更有人的味道。
                due = life_obj.due_loops() if life_obj else []
                if due:
                    self._followed_ids = [lp.get("id") for lp in due]
                parts = []
                if due:
                    parts.append(
                        "★ 你之前问过他下面这些事，他到现在还没给你结果 —— "
                        "这次主动找他，优先挑其中一件问结果，不要另起新话题"
                        "（自然点，别像查岗，一句话就够）：\n"
                        + "\n".join("- 「%s」" % lp.get("asked", "") for lp in due))
                if life:
                    parts.append(life)
                if recent:
                    parts.append("你最近刚发过/说过的话（不要重复其中的话题和句式）：\n" + recent)
                parts.append("现在主动发一条。说你手上那件事的具体进展或吐槽，别问「在吗」。")
                user_msg = "\n\n".join(parts)
                txt = llm.chat(PROACTIVE_SYSTEM, user_msg,
                               max_tokens=120, temperature=0.95)
                txt = " ".join(txt.split())
                if txt:
                    return txt[:200]
                LOG.warning("proactive LLM 返回空，回落模板")
            except Exception as exc:  # noqa: BLE001
                LOG.warning("proactive LLM 失败，回落模板: %s", exc)
        return random.choice(FALLBACK_LINES)

    # ---------- 发送 ----------
    def send_once(self, use_llm: bool = True) -> bool:
        text = self._generate(allow_llm=use_llm)
        if not text:
            return False
        # ★ 对外输出检查（与 autoreply 同一条标准）：主动消息也可能把
        #   system prompt 段落或 plan 结构直接吐出来，一样不能发。
        import outguard
        text, gstate = outguard.guard(
            text,
            regenerate=(lambda: self._generate(allow_llm=use_llm)) if use_llm else None,
            log=LOG.warning)
        if not text:
            LOG.warning("proactive outguard：无可用文本，放弃这一轮")
            return False
        if gstate != "pass":
            LOG.info("proactive outguard 处置=%s -> %r", gstate, text[:40])
        for attempt in range(3):
            if self.bridge.send_text(self.cfg.peer, text):
                self.store.add(self.cfg.peer, "assistant", text, "proactive",
                               "proactive:{}".format(int(time.time() * 1000)))
                LOG.info("proactive sent: %r", text[:60])
                # 真发出去了才计一次回访（同一件事最多问两遍，见 life.LOOP_MAX_FOLLOW）
                if self._followed_ids:
                    try:
                        from peer_state import get_registry
                        get_registry().get(self.cfg.peer).life.mark_followed(
                            self._followed_ids)
                        LOG.info("已回访 %d 件旧事", len(self._followed_ids))
                    except Exception as exc:  # noqa: BLE001
                        LOG.warning("标记回访失败: %r", exc)
                return True
            LOG.warning("proactive send attempt %d failed", attempt + 1)
            time.sleep(2)
        return False

    # ---------- 主循环 ----------
    def run_forever(self) -> None:
        LOG.info("proactive started: peer=%s idle>=%dmin limit=%d/day",
                 self.cfg.peer, self.cfg.min_idle_minutes, self.cfg.daily_limit)
        while True:
            try:
                ok, why = self.should_send()
                if ok:
                    delay = random.randint(0, max(0, self.cfg.jitter_seconds))
                    LOG.info("proactive eligible; jitter %ds", delay)
                    time.sleep(delay)
                    ok2, why2 = self.should_send()
                    if ok2:
                        self.send_once()
                    else:
                        LOG.info("proactive cancelled: %s", why2)
                else:
                    LOG.debug("proactive not yet: %s", why)
                time.sleep(self.cfg.check_interval)
            except KeyboardInterrupt:
                LOG.info("proactive stopped")
                break
            except Exception as exc:  # noqa: BLE001
                LOG.exception("proactive loop error: %s", exc)
                time.sleep(30)
