import io
p = "autoreply.py"
s = io.open(p, encoding="utf-8").read()

steps = []

def rep(old, new, tag):
    global s
    n = s.count(old)
    if n != 1:
        steps.append("%s 跳过（命中 %d）" % (tag, n))
        return
    s = s.replace(old, new, 1)
    steps.append("%s ✓" % tag)

rep("import threading\nimport time",
    "import threading\nimport time\nfrom concurrent.futures import ThreadPoolExecutor",
    "import")

rep("DEFAULT_ALLOW: set[str] | None = None",
    "# 同时最多几个联系人并行处理（用户定的 5）\nPEER_WORKERS = 5\n\nDEFAULT_ALLOW: set[str] | None = None",
    "PEER_WORKERS")

rep("        self._gens: dict[str, FeizhiReplyGenerator] = {}\n        self._gens_lock = threading.Lock()",
    "        self._gens: dict[str, FeizhiReplyGenerator] = {}\n"
    "        self._gens_lock = threading.Lock()\n"
    "        # 多用户并发：不同人并行，同一个人串行（靠 PeerState.lock）\n"
    "        self._pool = ThreadPoolExecutor(max_workers=PEER_WORKERS,\n"
    "                                        thread_name_prefix=\"peer\")",
    "连接池")

rep("""                    try:
                        self._handle_batch(msgs)
                    except Exception as exc:  # noqa: BLE001
                        LOG.exception("handle error: %s", exc)
                        self.stats["failed"] += 1""",
    """                    # ★ 按联系人分组（2026-10-28 多用户）：不同人各自并行，
                    #   同一个人的连发仍然串行 —— 否则两条回复会互相踩上下文，
                    #   表现为对着同一句话答两遍、或者答到别人的话题上。
                    groups: dict[str, list[InboundMessage]] = {}
                    for m in msgs:
                        groups.setdefault(m.peer_wxid, []).append(m)
                    for peer_wxid, group in groups.items():
                        self._pool.submit(self._run_group, peer_wxid, group)""",
    "分组投递")

rep("    def _handle_batch(self, msgs: list[InboundMessage]) -> None:",
    """    def _run_group(self, peer: str, msgs: list[InboundMessage]) -> None:
        \"\"\"在线程池里处理某个联系人的一批消息。\"\"\"
        st = self.peers.get(peer)
        with st.lock:                       # 同一个人串行，不同人互不等待
            try:
                self._handle_batch(msgs)
            except Exception as exc:  # noqa: BLE001
                LOG.exception("handle error (peer=%s): %s", peer, exc)
                self.stats["failed"] += 1

    def _handle_batch(self, msgs: list[InboundMessage]) -> None:""",
    "_run_group")

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
for x in steps:
    print(" ", x)
