import io
p = "autoreply.py"
s = io.open(p, encoding="utf-8").read()

# 1) import
old = "import threading\nimport time"
assert s.count(old) == 1
s = s.replace(old, "import threading\nimport time\nfrom concurrent.futures import ThreadPoolExecutor", 1)

# 2) 常量
old = "# 2026-10-28 多用户：None = 不再用白名单挡人，所有好友都能找她说话。"
assert s.count(old) == 1
s = s.replace(old, "# 同时最多几个联系人并行处理（用户定的 5）\nPEER_WORKERS = 5\n\n"
                   "# 2026-10-28 多用户：None = 不再用白名单挡人，所有好友都能找她说话。", 1)

# 3) 连接池
old = "        self._gens: dict[str, FeizhiReplyGenerator] = {}\n        self._gens_lock = threading.Lock()"
assert s.count(old) == 1
s = s.replace(old, old + "\n"
    "        # 多用户并发：不同人并行，同一个人串行（靠 PeerState.lock）\n"
    "        self._pool = ThreadPoolExecutor(max_workers=PEER_WORKERS,\n"
    "                                        thread_name_prefix=\"peer\")", 1)

# 4) 分组投递
old = """                if msgs:
                    try:
                        self._handle_batch(msgs)
                    except Exception as exc:  # noqa: BLE001
                        LOG.exception("handle error: %s", exc)
                        self.stats["failed"] += 1"""
assert s.count(old) == 1
new = """                if msgs:
                    # ★ 按联系人分组（2026-10-28 多用户）：不同人各自并行，
                    #   同一个人的连发仍然串行 —— 否则两条回复会互相踩上下文，
                    #   表现为对着同一句话答两遍、或者答到别人的话题上。
                    groups: dict[str, list[InboundMessage]] = {}
                    for m in msgs:
                        groups.setdefault(m.peer_wxid, []).append(m)
                    for peer_wxid, group in groups.items():
                        self._pool.submit(self._run_group, peer_wxid, group)"""
s = s.replace(old, new, 1)

# 5) _run_group
old = "    def _handle_batch(self, msgs: list[InboundMessage]) -> None:"
assert s.count(old) == 1
new = """    def _run_group(self, peer: str, msgs: list[InboundMessage]) -> None:
        \"\"\"在线程池里处理某个联系人的一批消息。\"\"\"
        st = self.peers.get(peer)
        with st.lock:                       # 同一个人串行，不同人互不等待
            try:
                self._handle_batch(msgs)
            except Exception as exc:  # noqa: BLE001
                LOG.exception("handle error (peer=%s): %s", peer, exc)
                self.stats["failed"] += 1

    def _handle_batch(self, msgs: list[InboundMessage]) -> None:"""
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("并发调度已接入（PEER_WORKERS=5）")
