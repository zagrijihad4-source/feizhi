import io, re
p = "autoreply.py"
lines = io.open(p, encoding="utf-8").read().split("\n")

# 1) handle() 内 1320..1425 行范围内的 self.gen. -> gen.
changed = 0
for i in range(len(lines)):
    ln = lines[i]
    no = i + 1
    if 1300 <= no <= 1435 and "self.gen." in ln and "self.gen =" not in ln:
        lines[i] = ln.replace("self.gen.", "gen.")
        changed += 1
print("handle 内 self.gen -> gen：", changed, "处")

s = "\n".join(lines)

# 2) handle() 里 peer 定了之后创建/取本轮的 generator
old = """        LOG.info("inbound from %s: %r", peer, content[:60])"""
assert s.count(old) == 1
new = """        # ★ 每个联系人一个 generator 实例（2026-10-28 多用户）：
        #   generator 身上挂着 context_text / memory_ctx / life_ctx / search_ctx
        #   四个字段，共用一份的话并发时 A 的记忆块会覆盖 B 的，回复串味。
        gen = self._gen_for(peer)
        LOG.info("inbound from %s: %r", peer, content[:60])"""
s = s.replace(old, new, 1)

# 3) 新增 _gen_for + self._gens
old = """        self.gen = FeizhiReplyGenerator(llm=self.llm, timeout=llm_timeout, attempts=2)"""
assert s.count(old) == 1
new = """        self.gen = FeizhiReplyGenerator(llm=self.llm, timeout=llm_timeout, attempts=2)
        self._llm_timeout = llm_timeout
        # 每个联系人一个 generator（懒创建）。self.gen 留作兼容，正常路径不用。
        self._gens: dict[str, FeizhiReplyGenerator] = {}
        self._gens_lock = threading.Lock()"""
s = s.replace(old, new, 1)

old = """    # ---------- 记忆 ----------
    def _extract_memory(self, peer: str) -> None:"""
assert s.count(old) == 1
new = """    def _gen_for(self, peer: str) -> FeizhiReplyGenerator:
        \"\"\"取这个联系人的 generator（没有就建一个）。

        generator 是有状态的：context_text / memory_ctx / life_ctx / search_ctx
        都是每轮现写、随后被 generate_plan 读取。共用一份在并发下必然串味，
        所以按 peer 分开。它只是个薄壳（持有 llm 引用和两个配置），建造很便宜。
        \"\"\"
        with self._gens_lock:
            g = self._gens.get(peer)
            if g is None:
                g = FeizhiReplyGenerator(llm=self.llm, timeout=self._llm_timeout,
                                         attempts=2)
                self._gens[peer] = g
            return g

    # ---------- 记忆 ----------
    def _extract_memory(self, peer: str) -> None:"""
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("generator 已按 peer 隔离")
