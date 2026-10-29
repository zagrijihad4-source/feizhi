import io
p = "autoreply.py"
s = io.open(p, encoding="utf-8").read()

steps = []
def rep(old, new, tag):
    global s
    n = s.count(old)
    if n != 1:
        steps.append("%s 跳过（命中 %d）" % (tag, n)); return
    s = s.replace(old, new, 1); steps.append("%s ✓" % tag)

# 1) [sing:] 也算"给了声音"
rep('''    @staticmethod
    def _plan_has_voice(plan) -> bool:
        return any(str(getattr(m, "text", "")).lstrip().startswith("[voice:")
                   for m in getattr(plan, "messages", []))''',
    '''    @staticmethod
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
        return False''',
    "_plan_has_voice 认 sing")

# 2) 强制提示词分流：唱歌 -> [sing:]，说话 -> [voice:]
rep('''        forced = system + (
            "\\n\\n【本轮硬性要求 · 覆盖上面所有「大多数时候发文字」的说法】\\n"
            "他这一句明确是在要你的**声音**（唱歌 / 说话给他听）。\\n"
            "你这一轮**必须**至少输出一条 `[voice:档位:内容]`，"
            "不许只写文字；也不许说「唱完了」「我唱给你听」却没有语音 —— 那是骗人。\\n"
            "唱歌就把词念/哼出来（\\"月—亮—绕呀绕……\\"这样），不要只说\\"我唱完了\\"。")''',
    '''        _ask_sing = bool(self.SING_REQUEST.search(incoming or ""))
        if _ask_sing:
            forced = system + (
                "\\n\\n【本轮硬性要求 · 覆盖上面所有「大多数时候发文字」的说法】\\n"
                "他这一句是在点歌。\\n"
                "你这一轮**必须**整条只输出 `[sing:曲名]`，曲名从你录过的里面挑。\\n"
                "★ **绝对不要念歌词** —— 念词不是唱歌，他听得出来。\\n"
                "★ 也不许只写「行吧我唱」「唱完了」这种话却没有标记 —— 那是骗人。")
        else:
            forced = system + (
                "\\n\\n【本轮硬性要求 · 覆盖上面所有「大多数时候发文字」的说法】\\n"
                "他这一句明确是在要你的**声音**，想听你说话。\\n"
                "你这一轮**必须**至少输出一条 `[voice:档位:内容]`，"
                "不许只写文字；也不许说「说完了」「我说给你听」却没有语音 —— 那是骗人。")''',
    "强制提示词分唱歌/说话")

# 3) 点歌词表
rep('''    VOICE_REQUEST = re.compile(''',
    '''    # 点歌：这几句话要的是**唱**，该走 [sing:]（RVC 曲库），不是 [voice:] 念词
    SING_REQUEST = re.compile(r"唱|哼一?两?句|哼一段|哼两句|整一首")

    VOICE_REQUEST = re.compile(''',
    "SING_REQUEST")

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
for x in steps:
    print(" ", x)
