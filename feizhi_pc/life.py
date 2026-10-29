# -*- coding: utf-8 -*-
"""绯栀的"手上正在做的事" —— 让连续性变成可积累的东西。

设计动机（2026-10-18 用户提出）：
单次回复写得像人只解决了一半；真正让人觉得"她在过日子"的是**连续性**——

  1. 一件小事持续几天（海报配色被老师打回 → 改两版 → 最后发成品说"还是第一版顺眼"）
  2. 你说过的话会改变她后来的行为（你说喜欢蓝色 → 几天后她的作品里用了蓝）
  3. 共同维护的小东西（一直画不好的猫、奇怪饮料排行榜）

这套状态同时供给三个出口：聊天回复、主动搭话、朋友圈文案，
避免三路各自编出互相矛盾的日程。

数据放 state/feizhi_life.json，结构：
{
  "projects": [{"id","title","status","started","beats":[{"day","text"}],"next_hint"}],
  "shared":   [{"id","title","notes":[...]}],
  "influences":[{"what","how","date"}],
  "mood":     {"state","cause","since"}
}
"""
from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path

LOG = logging.getLogger("feizhi_pc.life")

HERE = Path(__file__).resolve().parent
DEFAULT_PATH = HERE / "state" / "feizhi_life.json"

MAX_PROJECTS = 3          # 手上同时最多几件事（真人也就一两件）
MAX_MOOD_LOG = 10         # 情绪时间线保留几段（多了没意义，还会稀释当前心情）
MAX_BEATS = 8             # 每件事的进展梗概保留几条
MAX_SHARED = 3
MAX_INFLUENCES = 12
MAX_LOOPS = 12            # 挂念着的"未了结的事"最多记几件
LOOP_MIN_AGE_H = 2.0      # 至少隔这么久才回访（刚问完就追问像查岗）
LOOP_MAX_AGE_H = 72.0     # 超过 3 天就不提了，再提很突兀
LOOP_MAX_FOLLOW = 2       # 同一件事最多回访几次

ADVANCE_SYSTEM = """你在维护「绯栀」的日常生活状态。
她是一个 19 岁的杭州女孩，美院视觉传达大二，住在学校附近的出租屋，养了只叫糊糊的橘猫。

现在只做一件事：**让她的日子往前走一小段**。

★ 她的一天不由聊天推动。有没有人找她，日子都在过：
早上起不来、上午在画室、下午有课、晚上画到一半犯困、糊糊踩键盘、外卖凉了。
你只依据「现在是几点、距上次过了多久、她手上做到哪一步」来推导，
不要假定刚刚有人跟她说过话，也不要等她被谁推动才动。

规则：
- 每件事最多推进**一小步**（不要一次就做完，也不要每次都动）
- 允许退步和推翻（老师又打回、自己不满意），这才像真的
- 有事该结束了就标结束，并说一句她的感受
- 可以新开最多一件小事（但手上的不要超过 3 件）
- **时间要吻合**：深夜就是困、早八就是不想起、饭点就是饿、连着熬两天就该垮，
  别在凌晨三点写"精神很好"，也别在同一个人身上反复出现同一种进展
- 用第一人称内心视角，每条不超过 40 字
- **不要**写"今天心情很好"这类空话；要具体（"配色又被打回，干脆把稿子贴在墙上不看了"）

只输出 JSON：
{"projects":[{"id":"原样返回","status":"ongoing|done|dropped","beat":"这次的一小步"}],
 "new_project":{"title":"...","beat":"..."} 或 null,
 "shared_notes":[{"id":"原样返回","note":"一句新评价"}],
 "mood":{"state":"...","cause":"..."} 或 null}"""


def period_of_day(hour: int) -> str:
    """把钟点说成人话，喂给模型当时段锚点。"""
    if hour < 5:
        return "深夜"
    if hour < 8:
        return "清晨"
    if hour < 11:
        return "上午"
    if hour < 13:
        return "中午"
    if hour < 17:
        return "下午"
    if hour < 19:
        return "傍晚"
    if hour < 23:
        return "晚上"
    return "深夜"

RENDER_HEAD = "【你手上正在做的事 · 这是你自己的日子，不是设定】"
RENDER_TAIL = (
    "用法：这些是你自己的事，聊到了自然带出来（\"我那张海报又被老师打回了\"），"
    "不用每次都汇报，也不要一次全说完。他问起时你可以讲细节。\n"
)


class FeizhiLife:
    """她的生活状态。

    ★ 2026-10-28 多用户改造：**分两层存**。
      · 共享层（projects / mood / last_tick）—— 她自己过的日子，全进程唯一。
        谁来找她，看到的都是同一份现实：海报改到第几版、今天困不困。
      · 私有层（shared / influences / open_loops）—— 和某个人的关系片段：
        跟他分享过什么、他影响了她什么、和他还有什么没说完的。
        这层必须按 peer 隔离，否则会拿和 A 的约定去问候 B。

      `private_path=None` 时两层都写进 `path`，**行为和改造前完全一致**
      （单用户 / 老数据 / 测试脚本都不会受影响）。
    """

    SHARED_KEYS = ("projects", "mood", "mood_log", "last_tick")
    PRIVATE_KEYS = ("shared", "influences", "open_loops")

    def __init__(self, path: Path | str = DEFAULT_PATH,
                 private_path: Path | str | None = None,
                 write_shared: bool = True,
                 keep_private_keys: bool = True):
        """
        ★ `write_shared=False`：这个实例只负责私有层，`save()` 不碰共享文件。
          必须这么分，否则会出真实竞态 —— PeerState 里那份带私有层的 life，
          一旦 add_loop()/note_answered() 触发 save()，就会拿它内存里的
          projects 快照覆盖掉 life tick 刚写进去的进度，她的日子原地倒退。
        """
        self.path = Path(path)
        self.private_path = Path(private_path) if private_path else None
        self.write_shared = bool(write_shared)
        # keep_private_keys=False：只有共享层、没有私有层时（self_life()），
        # 落盘只写 SHARED_KEYS。否则共享文件里会寄生 shared/influences/
        # open_loops 三个空壳，谁哪天直接读它就会当成"她没有任何未了结的事"。
        self.keep_private_keys = bool(keep_private_keys)
        self.data = self._load()

    # ---------- 存储 ----------
    @staticmethod
    def _blank() -> dict:
        return {"projects": [], "shared": [], "influences": [],
                "mood": {}, "mood_log": [], "open_loops": [], "last_tick": ""}

    @staticmethod
    def _read(path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("生活状态读取失败（%s），当空处理：%r", path.name, exc)
            return {}

    def _load(self) -> dict:
        d = self._blank()
        d.update(self._read(self.path))
        if self.private_path:
            d.update(self._read(self.private_path))
        return d

    def reload_shared(self) -> None:
        """重读共享层（她自己的日子）。

        多用户下共享层会被 life tick 改写，每个 peer 渲染前都要拿最新的那份，
        否则会出现"跟你聊着昨天的海报，跟另一个人聊着今天已经交了"。
        """
        if self.private_path:
            self.data.update(self._read(self.path))

    @staticmethod
    def _write(path: Path, obj: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def save(self) -> None:
        if not self.private_path:
            obj = self.data if self.keep_private_keys else {
                k: self.data.get(k) for k in self.SHARED_KEYS}
            self._write(self.path, obj)
            return
        if self.write_shared:
            self._write(self.path, {k: self.data.get(k) for k in self.SHARED_KEYS})
        self._write(self.private_path,
                    {k: self.data.get(k) for k in self.PRIVATE_KEYS})

    # ---------- 查询 ----------
    def ongoing(self) -> list[dict]:
        return [p for p in self.data.get("projects", []) if p.get("status") == "ongoing"]

    def stats(self) -> dict:
        return {"projects": len(self.ongoing()),
                "shared": len(self.data.get("shared", [])),
                "influences": len(self.data.get("influences", [])),
                "mood": (self.data.get("mood") or {}).get("state", ""),
                "last_tick": self.data.get("last_tick", "")}

    # ---------- 未了结的事（回访） ----------
    @staticmethod
    def _extract_questions(text: str) -> list[str]:
        """从她说的话里挑出「问他的问题」。

        真人会记得自己问过什么、对方还没答；下次聊天能接上「那个到底弄完没」。
        判定很严：必须**真的带问号**，或以「吗/呢/么」收尾。
        早一版按所有标点切句，把「嗯什么嗯呀，你倒是闭眼」这种祈使句也登记成问句了，
        结果她会被自己的命令句触发"回访"，问出来的东西莫名其妙。
        还要求句子里有「你」—— 问自己的（"我今天怎么了？"）不算待回访。
        """
        import re as _re
        out: list[str] = []
        for seg in _re.split(r"[。！!\n]", text or ""):
            seg = seg.strip(" \t，,、…~～")
            if not seg:
                continue
            chunks = _re.findall(r"[^？?]{2,40}[？?]", seg)
            if not chunks and _re.search(r"[吗呢么]$", seg):
                chunks = [seg]          # 口语里常省略问号（"你吃了吗"）
            for c in chunks:
                c = c.rstrip("？?").strip(" \t，,、…~～")
                if 4 <= len(c) <= 40 and "你" in c and c not in out:
                    out.append(c)
        return out

    def add_loop(self, text: str) -> int:
        """把她刚问出口的问题登记成"未了结的事"。返回新增条数。"""
        import difflib
        qs = self._extract_questions(text)
        if not qs:
            return 0
        loops = self.data.setdefault("open_loops", [])
        added = 0
        now_ts = int(time.time())
        for q in qs:
            dup = False
            for lp in loops:
                if difflib.SequenceMatcher(None, lp.get("asked", ""), q).ratio() >= 0.55:
                    dup = True
                    break
            if dup:
                continue
            loops.append({"id": now_ts * 1000 + added, "asked": q,
                          "ts": now_ts,
                          "asked_at": time.strftime("%Y-%m-%d %H:%M"),
                          "follow_ups": 0, "answered": False,
                          "status": "open"})
            added += 1
        if added:
            if len(loops) > MAX_LOOPS:
                del loops[:-MAX_LOOPS]
            self.save()
            LOG.info("登记待回访 %d 条：%s", added, qs[:2])
        return added

    def note_answered(self) -> int:
        """他回话之后调用：把所有待回访标成"他答过了"。

        不删除 —— 「答过了」正是回访的最佳时机（"那最后到底成了没"）。
        """
        n = 0
        for lp in self.data.get("open_loops", []):
            if lp.get("status") == "open":
                lp["status"] = "answered"
                lp["answered_at"] = time.strftime("%Y-%m-%d %H:%M")
                n += 1
        if n:
            self.save()
        return n

    def due_loops(self, limit: int = 2) -> list[dict]:
        """取现在适合回访的几件（够久、没问太多次、也没过期）。"""
        now = time.time()
        out = []
        for lp in self.data.get("open_loops", []):
            if lp.get("status") == "closed":
                continue
            if int(lp.get("follow_ups") or 0) >= LOOP_MAX_FOLLOW:
                continue
            age_h = (now - float(lp.get("ts") or 0)) / 3600.0
            if age_h < LOOP_MIN_AGE_H or age_h > LOOP_MAX_AGE_H:
                continue
            lp["_age_h"] = age_h
            out.append(lp)
        # 他答过的最值得问（"结果如何"），其次按时间倒序
        out.sort(key=lambda x: (x.get("status") != "answered",
                                -float(x.get("ts") or 0)))
        return out[:limit]

    def mark_followed(self, loop_ids: list[int]) -> None:
        for lp in self.data.get("open_loops", []):
            if lp.get("id") in loop_ids:
                lp["follow_ups"] = int(lp.get("follow_ups") or 0) + 1
                lp["last_follow"] = time.strftime("%Y-%m-%d %H:%M")
                if lp["follow_ups"] >= LOOP_MAX_FOLLOW:
                    lp["status"] = "closed"
        self.save()

    def _render_loops(self) -> str:
        due = self.due_loops()
        if not due:
            return ""
        lines = []
        for lp in due:
            age = lp.get("_age_h") or 0
            when = ("刚刚" if age < 1 else
                    ("%.0f 小时前" % age if age < 24 else "%.0f 天前" % (age / 24)))
            tail = "（他说过了，但还没说结果）" if lp.get("answered") else "（他还没接这个话）"
            lines.append("- 你%s问过他「%s」%s" % (when, lp.get("asked", ""), tail))
        return ("【你还惦记着的几件事】\n" + "\n".join(lines) + "\n"
                "用法：聊天时如果话头合适，自然地问一句结果（\"那个到底交了没\"）；"
                "主动找他时优先挑这些事开口。别每次都问，也别像查岗，"
                "他没答就别追第二遍。\n")

    def _push_mood_log(self, state: str, cause: str, at: str) -> None:
        """把一段心情记进时间线（**不覆盖**上一段）。

        ★ 2026-10-28：原来 `mood` 只有一个 {state, cause, since}，每次 tick
          直接覆盖上一次 —— 她永远只知道"此刻什么心情"，说不出"我这几天一直
          没睡好"。记忆架构上这叫「情绪被事实覆盖」：事实（做过什么）留得住，
          情绪留不住，人就不像有连续性，只像一个每六小时重置一次的状态机。
        """
        state = (state or "").strip()
        if not state:
            return
        log = self.data.setdefault("mood_log", [])
        if log and log[-1].get("state") == state:
            log[-1]["at"] = at          # 同一股劲延续，只更新时间，不刷屏
        else:
            log.append({"state": state, "cause": (cause or "").strip()[:40],
                        "at": at})
        if len(log) > MAX_MOOD_LOG:
            del log[:-MAX_MOOD_LOG]

    @staticmethod
    def _short_when(at: str) -> str:
        """"2026-10-26 18:40" -> "26号傍晚"；今天/昨天/前天用相对说法。"""
        if not at:
            return ""
        try:
            t = time.strptime(at, "%Y-%m-%d %H:%M")
        except Exception:  # noqa: BLE001
            return ""
        now = time.localtime()
        def day0(st):
            return time.mktime((st.tm_year, st.tm_mon, st.tm_mday,
                                0, 0, 0, 0, 0, -1))
        diff = int((day0(now) - day0(t)) / 86400)
        if diff == 0:
            day = "今天"
        elif diff == 1:
            day = "昨天"
        elif diff == 2:
            day = "前天"
        else:
            day = "%d号" % t.tm_mday
        return day + period_of_day(t.tm_hour)

    @staticmethod
    def _mood_age_hint(since: str) -> str:
        """把 mood.since 换算成"这股劲持续多久了"的一句提示。"""
        if not since:
            return ""
        try:
            t = time.mktime(time.strptime(since, "%Y-%m-%d %H:%M"))
        except Exception:  # noqa: BLE001
            return ""
        hrs = (time.time() - t) / 3600.0
        if hrs < 0:
            return ""
        if hrs >= 30:
            return "（这股劲儿压了一两天了，还没散，别装作没事）"
        if hrs >= 6:
            return "（从几小时前就这样，还没缓过来）"
        if hrs >= 1:
            return "（刚才的事，情绪还热着）"
        return "（就是当下这一刻）"

    def render(self, include_loops: bool = True) -> str:
        """渲染成注入 prompt 的一段。三路（聊天/主动/朋友圈）共用。

        include_loops=False 时只渲染"日子"部分 —— 主动搭话那边会把
        「挂念着的事」单独拎出来当成明确指令，重复注入反而稀释重点。
        """
        parts = []
        proj = self.ongoing()
        if proj:
            lines = []
            for p in proj:
                beats = p.get("beats") or []
                trail = ("；".join(b.get("text", "") for b in beats[-2:])
                         if beats else "")
                hint = p.get("next_hint") or ""
                line = "- %s" % p.get("title", "")
                if trail:
                    line += "：%s" % trail
                if hint:
                    line += "（接下来大概会：%s）" % hint
                lines.append(line)
            parts.append("手上正在弄的：\n" + "\n".join(lines))

        shared = self.data.get("shared") or []
        if shared:
            lines = []
            for s in shared:
                notes = s.get("notes") or []
                # notes 元素可能是 {"day","text"} 也可能是纯字符串，两种都兼容
                tail = "；".join(
                    str(n.get("text", "")) if isinstance(n, dict) else str(n)
                    for n in notes[-2:])
                lines.append("- %s%s" % (s.get("title", ""), ("：" + tail) if tail else ""))
            parts.append("你们一起弄着的小东西：\n" + "\n".join(lines))

        infl = self.data.get("influences") or []
        if infl:
            lines = ["- %s（%s）" % (i.get("what", ""), i.get("how", ""))
                     for i in infl[-4:]]
            parts.append("他说过的话，真的影响到你了：\n" + "\n".join(lines))

        mood = self.data.get("mood") or {}
        if mood.get("state"):
            line = "你现在的心情：%s（因为%s）" % (
                mood["state"], mood.get("cause") or "些说不上来的事")
            # 情绪的"余温"：写清这股劲已经持续多久，模型才不会一秒切换状态。
            # 真人烦了一整天，不会因为对方换了个话题就立刻轻快起来。
            line += self._mood_age_hint(mood.get("since") or "")
            parts.append(line)
            # 情绪时间线：只列**和当下不同**的最近几段，作为"这几天"的背景。
            # 不让她主动汇报，只是让说话时有底气 —— 她确实过了这么几天。
            _log = [x for x in (self.data.get("mood_log") or [])
                    if x.get("state") and x.get("state") != mood["state"]]
            if _log:
                seq = " → ".join(
                    "%s%s" % (self._short_when(x.get("at")), x.get("state"))
                    for x in _log[-4:])
                parts.append(
                    "这几天的心情是这么过来的：%s → 现在这样。\n"
                    "（不用主动汇报，但你说「这几天」的时候心里要有这个底。）" % seq)

        out = ""
        if parts:
            out = RENDER_HEAD + "\n" + "\n\n".join(parts) + "\n" + RENDER_TAIL
        # 「挂念着的事」放在日子之后：它管的是对话而不是生活本身，
        # 单独成段、带自己的用法说明，避免和上面几条混淆。
        loop_block = self._render_loops() if include_loops else ""
        if loop_block:
            out = (out + "\n" + loop_block) if out else loop_block
        return out

    # ---------- 写入 ----------
    def record_influence(self, what: str, how: str) -> bool:
        """记一条"<OWNER>影响了她"。同一句话只记一次。"""
        what = (what or "").strip()
        if not what:
            return False
        for i in self.data.setdefault("influences", []):
            if i.get("what") == what:
                i["how"] = how or i.get("how", "")
                self.save()
                return False
        self.data["influences"].append(
            {"what": what, "how": (how or "").strip(),
             "date": time.strftime("%Y-%m-%d")})
        if len(self.data["influences"]) > MAX_INFLUENCES:
            del self.data["influences"][:-MAX_INFLUENCES]
        self.save()
        return True

    def set_mood(self, state: str, cause: str = "") -> None:
        stamp = time.strftime("%Y-%m-%d %H:%M")
        self.data["mood"] = {"state": (state or "").strip(),
                             "cause": (cause or "").strip(),
                             "since": stamp}
        # 手动设定也进时间线，否则这条会从"这几天"里消失
        self._push_mood_log(state, cause, stamp)
        self.save()

    # ---------- 推进 ----------
    def hours_since_tick(self) -> float:
        """距上次推进过了多少小时。没记录过就返回一个很大的数。"""
        last = self.data.get("last_tick") or ""
        if not last:
            return 1e9
        try:
            t = time.mktime(time.strptime(last, "%Y-%m-%d %H:%M"))
        except Exception:  # noqa: BLE001
            return 1e9
        return (time.time() - t) / 3600.0

    def need_tick(self, min_gap_hours: float = 6.0) -> bool:
        return self.hours_since_tick() >= min_gap_hours

    def tick(self, llm, now: float | None = None) -> dict:
        """按时间流逝推进她的一天。返回改动摘要。

        ★★ 2026-10-28 因果纠正：**不再吃聊天内容**。
          旧实现是 `tick(llm, chat_snippet)`，由 `_advance_life(peer)` 把那个人
          最近 12 条历史塞进来当主输入 —— 结果她的一天成了别人几句消息的注脚：
          有人找她，日子才往前走一步；没人找她，她就像停在那儿不动。
          现在只喂「现在几点、距上次过了多久、手上做到哪一步」，
          她按自己的节律过日子，聊天只是她一天里的一件事，不是引擎。

        ★ 间隔默认 20h -> 6h：一天推进 2~4 次，她才会有"下午有课""晚上犯困"
          这种连续感，而不是每天醒来直接跳到下一个总结。
        """
        if not llm:
            return {"skipped": "no_llm"}
        if not self.need_tick():
            return {"skipped": "too_soon"}

        now = now if now is not None else time.time()
        lt = time.localtime(now)
        gap_h = self.hours_since_tick()

        cur = []
        for p in self.ongoing():
            trail = "；".join(b.get("text", "") for b in (p.get("beats") or [])[-3:])
            cur.append({"id": p.get("id"), "title": p.get("title"), "trail": trail})
        shared = [{"id": s.get("id"), "title": s.get("title"),
                   "notes": (s.get("notes") or [])[-2:]}
                  for s in (self.data.get("shared") or [])]

        stamp = time.strftime("%Y-%m-%d %H:%M", lt)
        weekday = "一二三四五六日"[lt.tm_wday]
        if gap_h > 168:
            gap_txt = "很久没有记录了，就当是新的一天重新接上"
        else:
            gap_txt = "距上次记录 %.1f 小时" % gap_h

        user = (
            "【现在】%s 星期%s %s（%s）\n\n"
            "【她手上正在做的事】\n%s\n\n"
            "【她此刻的心情】\n%s\n"
            % (stamp, weekday, period_of_day(lt.tm_hour), gap_txt,
               json.dumps(cur, ensure_ascii=False),
               json.dumps(self.data.get("mood") or {}, ensure_ascii=False))
        )
        # ★ 不喂 shared（她跟人分享过什么）。实测代价：只要给了这层，模型就会
        #   顺着编出「<OWNER>说窄边暗红有点闷，建议拿掉」这种根本不存在的对话 —
        #   她的一天被写成了别人意见的注脚。她的日子只看 projects + mood + 时间。
        #   shared 属于关系记忆，等按 peer 拆开之后更不该出现在这里。

        try:
            out = llm.chat(ADVANCE_SYSTEM, user, max_tokens=700, temperature=0.9)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("生活推进调用失败：%r", exc)
            return {"error": "llm"}

        try:
            import re
            m = re.search(r"\{.*\}", out, re.S)
            if not m:
                LOG.warning("生活推进返回非 JSON：%r", out[:160])
                return {"error": "not_json"}
            obj = json.loads(m.group(0))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("生活推进解析失败：%r", exc)
            return {"error": "parse"}

        today = time.strftime("%Y-%m-%d")
        changed = {"beats": 0, "new": 0, "closed": 0, "notes": 0}

        # 推进已有项目
        by_id = {p.get("id"): p for p in self.data.get("projects", [])}
        for item in (obj.get("projects") or []):
            if not isinstance(item, dict):
                continue
            p = by_id.get(item.get("id"))
            if not p:
                continue
            beat = str(item.get("beat") or "").strip()
            if beat:
                p.setdefault("beats", []).append({"day": today, "text": beat})
                if len(p["beats"]) > MAX_BEATS:
                    del p["beats"][:-MAX_BEATS]
                changed["beats"] += 1
            st = item.get("status")
            if st in ("done", "dropped") and p.get("status") == "ongoing":
                p["status"] = st
                p["closed"] = today
                changed["closed"] += 1

        # 新开一件
        np = obj.get("new_project")
        if isinstance(np, dict) and len(self.ongoing()) < MAX_PROJECTS:
            title = str(np.get("title") or "").strip()
            if title:
                self.data["projects"].append({
                    "id": "p%d" % int(time.time()),
                    "title": title[:40],
                    "status": "ongoing",
                    "started": today,
                    "beats": [{"day": today, "text": str(np.get("beat") or "").strip()[:80]}]
                    if np.get("beat") else [],
                })
                changed["new"] += 1

        # 共同小东西的新评价
        sby = {s.get("id"): s for s in (self.data.get("shared") or [])}
        for item in (obj.get("shared_notes") or []):
            if not isinstance(item, dict):
                continue
            s = sby.get(item.get("id"))
            note = str(item.get("note") or "").strip()
            if s and note:
                s.setdefault("notes", []).append({"day": today, "text": note[:60]})
                changed["notes"] += 1

        # 心情
        mood = obj.get("mood")
        if isinstance(mood, dict) and mood.get("state"):
            _stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
            self.data["mood"] = {"state": str(mood["state"])[:20],
                                 "cause": str(mood.get("cause") or "")[:40],
                                 "since": _stamp}
            self._push_mood_log(str(mood["state"])[:20],
                                str(mood.get("cause") or ""), _stamp)

        # 收敛：超出上限的旧项目丢掉
        projs = self.data.get("projects", [])
        if len(projs) > 8:
            projs.sort(key=lambda p: p.get("started", ""))
            self.data["projects"] = projs[-8:]

        # 用传进来的 now 而不是真实时钟：补算历史某一天的推进时才不会错位
        self.data["last_tick"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
        self.save()
        LOG.info("生活推进：%s（在手 %d 件）", changed, len(self.ongoing()))
        return changed

    # ---------- 初始化 ----------
    def seed_if_empty(self) -> bool:
        """首次使用时给两件正在进行的小事，免得她"没有生活"。"""
        if self.data.get("projects"):
            return False
        today = time.strftime("%Y-%m-%d")
        self.data["projects"] = [
            {"id": "poster", "title": "那张被老师说配色脏的海报", "status": "ongoing",
             "started": today, "next_hint": "还得再改一版交上去",
             "beats": [{"day": today, "text": "老师说我配色脏，我嘴上不服，其实心里觉得他说得对"}]},
            {"id": "catdraw", "title": "想画一张糊糊，画了三次都不像", "status": "ongoing",
             "started": today, "next_hint": "可能会再试一次，或者干脆放弃",
             "beats": [{"day": today, "text": "它一躺下就变形，怎么画都不像那只猫"}]},
        ]
        self.data["shared"] = [
            {"id": "catdraw", "title": "那只一直画不好的猫",
             "notes": [{"day": today, "text": "第 3 版被自己否了"}]},
        ]
        self.save()
        return True


if __name__ == "__main__":
    import sys
    life = FeizhiLife()
    if "--seed" in sys.argv:
        print("seed:", life.seed_if_empty())
    print(json.dumps(life.stats(), ensure_ascii=False, indent=2))
    print(life.render() or "（空）")
