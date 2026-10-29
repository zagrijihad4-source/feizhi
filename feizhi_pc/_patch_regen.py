import io
p = "autoreply.py"
s = io.open(p, encoding="utf-8").read()

# _regenerate_text 加 peer，用该 peer 的 generator
old = """    def _regenerate_text(self, incoming: str) -> str:"""
assert s.count(old) == 1
s = s.replace(old, """    def _regenerate_text(self, incoming: str, peer: str = "") -> str:""", 1)

old = """        plan = self.gen.generate_plan(incoming, [])"""
assert s.count(old) == 1
s = s.replace(old, """        # 重新生成也必须用这个联系人的 generator：借用共享那份会把
        # 原轮的 memory_ctx / life_ctx 带走，重生成出来的是别人的语气。
        _g = self._gen_for(peer) if peer else self.gen
        plan = _g.generate_plan(incoming, [])""", 1)

old = """            regenerate=(lambda: self._regenerate_text(incoming)) if incoming else None,"""
assert s.count(old) == 1
s = s.replace(old, """            regenerate=(lambda: self._regenerate_text(incoming, peer)) if incoming else None,""", 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("_regenerate_text 已按 peer 取 generator")
