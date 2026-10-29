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

# 1) 在途消息集合
rep("        self._pool = ThreadPoolExecutor(max_workers=PEER_WORKERS,\n"
    "                                        thread_name_prefix=\"peer\")",
    "        self._pool = ThreadPoolExecutor(max_workers=PEER_WORKERS,\n"
    "                                        thread_name_prefix=\"peer\")\n"
    "        # ★ 在途消息（(peer, msg_id, local_id)）。并发化之后主循环不再等\n"
    "        #   _handle_batch 跑完，而 mark_processed 要等回复入队才调用 ——\n"
    "        #   中间这几秒里 poll_new 会把同一条消息**再取一次**，\n"
    "        #   于是同一条被处理两遍、生成两组措辞相近的回复发出去。\n"
    "        #   实测：<OWNER>说「没听，现在回宿舍了早就」，她在 20:49:22 和 20:49:39\n"
    "        #   各回了一条，内容几乎一样。\n"
    "        self._inflight: set[tuple[str, str, str]] = set()\n"
    "        self._inflight_lock = threading.Lock()",
    "在途集合")

# 2) 分组时过滤在途
rep("""                    groups: dict[str, list[InboundMessage]] = {}
                    for m in msgs:
                        groups.setdefault(m.peer_wxid, []).append(m)""",
    """                    groups: dict[str, list[InboundMessage]] = {}
                    for m in msgs:
                        k = (m.peer_wxid, str(m.msg_id), str(m.local_id))
                        with self._inflight_lock:
                            if k in self._inflight:
                                continue          # 还在处理，别重复投递
                            self._inflight.add(k)
                        groups.setdefault(m.peer_wxid, []).append(m)
                    if not groups:
                        msgs = []""",
    "过滤在途")

# 3) 线程池任务结束时清掉
rep("""    def _run_group(self, peer: str, msgs: list[InboundMessage]) -> None:
        \"\"\"在线程池里处理某个联系人的一批消息。\"\"\"
        st = self.peers.get(peer)
        with st.lock:                       # 同一个人串行，不同人互不等待
            try:
                self._handle_batch(msgs)
            except Exception as exc:  # noqa: BLE001
                LOG.exception("handle error (peer=%s): %s", peer, exc)
                self.stats["failed"] += 1""",
    """    def _run_group(self, peer: str, msgs: list[InboundMessage]) -> None:
        \"\"\"在线程池里处理某个联系人的一批消息。\"\"\"
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
                        (m.peer_wxid, str(m.msg_id), str(m.local_id)))""",
    "_run_group 清理在途")

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
for x in steps:
    print(" ", x)
