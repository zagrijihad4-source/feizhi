import io
p = "autoreply.py"
s = io.open(p, encoding="utf-8").read()

old = """                    for peer_wxid, group in groups.items():
                        self._pool.submit(self._run_group, peer_wxid, group)"""
assert s.count(old) == 1
new = """                    for peer_wxid, group in groups.items():
                        # 系统会话（newsapp / 文件传输助手 / 公众号…）在分组层就挡掉：
                        # 一进 _run_group 就会 peers.get() 建目录，白建一堆空壳。
                        if _is_system_peer(peer_wxid):
                            for m in group:
                                self.stats["seen"] += 1
                                self.stats["skipped"] += 1
                                self.bridge.mark_processed(m)
                            continue
                        self._pool.submit(self._run_group, peer_wxid, group)"""
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("分组层已过滤系统会话")

# warm_from_disk 也跳过系统会话
p2 = "peer_state.py"
s2 = io.open(p2, encoding="utf-8").read()
old2 = """            if not wxid:
                # 目录名就是 safe_name(wxid)，wxid 只含安全字符时可直接还原
                wxid = d.name
            self.get(wxid)"""
assert s2.count(old2) == 1
new2 = """            if not wxid:
                # 目录名就是 safe_name(wxid)，wxid 只含安全字符时可直接还原
                wxid = d.name
            # 系统会话永远不该有 peer 状态（尽早挡住，别让空壳目录越积越多）
            if any(wxid == t or wxid.lower().startswith(t)
                   for t in _SYSTEM_PREFIXES):
                LOG.info("跳过系统会话目录：%s", wxid)
                continue
            self.get(wxid)"""
s2 = s2.replace(old2, new2, 1)

old2 = "RELATION_LEVELS = (\"stranger\", \"friend\", \"intimate\")"
assert s2.count(old2) == 1
new2 = ('RELATION_LEVELS = ("stranger", "friend", "intimate")\n\n'
        '# 与 bridge.IGNORE_PEERS 同源，这里单独列一份是为了不把 bridge 拖进来\n'
        '_SYSTEM_PREFIXES = ("newsapp", "filehelper", "floatbottle", "medianote",\n'
        '                    "weixin", "notifymessage", "gh_", "weixinreminder")')
s2 = s2.replace(old2, new2, 1)
io.open(p2, "w", encoding="utf-8", newline="\n").write(s2)
print("warm_from_disk 已跳过系统会话")
