import io
p = "life.py"
s = io.open(p, encoding="utf-8").read()

steps = []
def rep(old, new, tag):
    global s
    n = s.count(old)
    if n != 1:
        steps.append("%s 跳过（命中 %d）" % (tag, n)); return
    s = s.replace(old, new, 1); steps.append("%s ✓" % tag)

# 1) 共享字段加 mood_log
rep('    SHARED_KEYS = ("projects", "mood", "last_tick")',
    '    SHARED_KEYS = ("projects", "mood", "mood_log", "last_tick")', "SHARED_KEYS")

rep('                "mood": {}, "open_loops": [], "last_tick": ""}',
    '                "mood": {}, "mood_log": [], "open_loops": [], "last_tick": ""}',
    "_blank")

# 2) 常量
rep("MAX_PROJECTS = 3          # 手上同时最多几件事（真人也就一两件）",
    "MAX_PROJECTS = 3          # 手上同时最多几件事（真人也就一两件）\n"
    "MAX_MOOD_LOG = 10         # 情绪时间线保留几段（多了没意义，还会稀释当前心情）",
    "MAX_MOOD_LOG")

# 3) 时间线工具
rep('''    @staticmethod
    def _mood_age_hint(since: str) -> str:''',
    '''    def _push_mood_log(self, state: str, cause: str, at: str) -> None:
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
    def _mood_age_hint(since: str) -> str:''',
    "时间线工具")

# 4) 渲染里加时间线
rep('''            line += self._mood_age_hint(mood.get("since") or "")
            parts.append(line)''',
    '''            line += self._mood_age_hint(mood.get("since") or "")
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
                    "这几天的心情是这么过来的：%s → 现在这样。\\n"
                    "（不用主动汇报，但你说\\"这几天"的时候心里要有这个底。）" % seq)''',
    "渲染时间线")

# 5) tick 里写时间线
rep('''        if isinstance(mood, dict) and mood.get("state"):
            self.data["mood"] = {"state": str(mood["state"])[:20],
                                 "cause": str(mood.get("cause") or "")[:40],
                                 "since": time.strftime("%Y-%m-%d %H:%M",
                                                         time.localtime(now))}''',
    '''        if isinstance(mood, dict) and mood.get("state"):
            _stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(now))
            self.data["mood"] = {"state": str(mood["state"])[:20],
                                 "cause": str(mood.get("cause") or "")[:40],
                                 "since": _stamp}
            self._push_mood_log(str(mood["state"])[:20],
                                str(mood.get("cause") or ""), _stamp)''',
    "tick 写时间线")

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
for x in steps:
    print(" ", x)
