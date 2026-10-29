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

rep("            retry_mode = True\n            LOG.info(\"此前处理未成功，补一次回复: %s\", key)",
    """            # ★★ 2026-10-29：这里必须加时间门槛，否则「正在处理」会被当成「处理失败」。
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
            LOG.info("此前处理未成功（消息已 %.0fs），补一次回复: %s", _age, key)""",
    "retry_mode 时间门槛")

rep("    def _peer_looks_active(self, peer: str, within_sec: float = 300.0) -> bool:",
    "    def _peer_looks_active(self, peer: str, within_sec: float = 900.0) -> bool:",
    "_peer_looks_active 默认窗口")

rep('''        用来给「没有目标地址」的操作（语音按键）兜一层：''',
    '''        ★ 2026-10-29：窗口从 300 秒放宽到 900 秒。原因是 `last_user_at` 用的是
          消息自带的时间戳，而从"他发出去"到"我们处理"实测能差 5 分钟
          （12:55 发的，13:00:45 才走到发语音那一步），300 秒窗口会把正常情况
          判成"他没说话"，于是唱歌被降级成文字 —— 用户的原话是"她怎么不回我"。

        用来给「没有目标地址」的操作（语音按键）兜一层：''',
    "窗口放宽的原因")

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
for x in steps:
    print(" ", x)
