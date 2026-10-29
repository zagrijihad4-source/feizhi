import io, re
p = "voice.py"
s = io.open(p, encoding="utf-8").read()
start = s.index("    # ---------- 鼠标 ----------")
end = s.index("    def say_pcm(self")
replacement = '''    # 2026-10-28：这里原本有 _dip / _click_dip / open_recent_chat 三个方法，
    # 干的是「用真实鼠标点搜索框、点联系人、点输入框，把会话切到目标再发语音」。
    # 已整段删除，理由写清楚免得以后又长回来：
    #   1. 语音功能的正身是「hook SILK 编码器 + 两条腿按键」，微信自己编码上传发送，
    #      全程不需要前台、不需要焦点、不需要动窗口（技术文档：不抢前台）。
    #   2. 真实鼠标会抢用户前台和输入法，文档 A3 记过事故 —— 他在输验证码时被打断。
    #   3. 实测这套点击还会把微信 Qt 整窗打成白屏（PrintWindow 白 98.7%，语音全挂）。
    #   4. 会话列表是 CEF 渲染的，PostMessage 鼠标消息被忽略，只能靠真实鼠标 ——
    #      也就是说这条路天生就得抢前台，和"不打扰他"根本对立。
    # 需要手动切会话时用 <PROJECT_ROOT>\\sing\\send_voice_robust.py（它的 open_chat 是
    # 显式可选的，SKIP_OPEN_CHAT=1 可跳过），不要在自动回复链路里做这件事。
    # 语音命中不了目标会话时，say_pcm 会在 2.5 秒内放弃，上层降级成文字。

'''
s = s[:start] + replacement + s[end:]
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("done")
