import io
p = "autoreply.py"
s = io.open(p, encoding="utf-8").read()
orig = s

pairs = [
    ("from store import ContextStore",
     "from peer_state import PeerRegistry, SELF_PATH      # noqa: E402\nfrom store import ContextStore"),

    ("        try:\n            r = self.memory.maybe_extract(self.store, peer, self.llm)",
     "        st = self.peers.get(peer)\n        try:\n            r = st.memory.maybe_extract(self.store, peer, self.llm)"),

    ("        self._reflect_memory()",
     "        self._reflect_memory(peer)"),

    ("    def _reflect_memory(self) -> None:",
     "    def _reflect_memory(self, peer: str) -> None:"),

    ("            r = reflect.maybe_reflect(self.memory)",
     "            r = reflect.maybe_reflect(self.peers.get(peer).memory)"),

    ("                        self.life.add_loop(text)",
     "                        self.peers.get(peer).life.add_loop(text)"),

    ("            if not self.life.need_tick():",
     "            if not self.life_shared.need_tick():"),

    ("            r = self.life.tick(self.llm)",
     "            r = self.life_shared.tick(self.llm)"),

    ("            self.life.note_answered()",
     "            self.peers.get(peer).life.note_answered()"),

    ("                self.gen.memory_ctx = self.memory.render()",
     "                self.gen.memory_ctx = self.peers.get(peer).memory.render()"),

    ("        try:\n            self.gen.life_ctx = self.life.render()",
     "        try:\n            _st_life = self.peers.get(peer).life\n"
     "            _st_life.reload_shared()     # 她的日子是共享的，每次拿最新那份\n"
     "            self.gen.life_ctx = _st_life.render()"),

    ("                        if self.life.need_tick():",
     "                        if self.life_shared.need_tick():"),
]

for old, new in pairs:
    n = s.count(old)
    if n != 1:
        raise SystemExit("命中次数不对（%d）：%r" % (n, old[:60]))
    s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("全部替换完成，", len(pairs), "处")
