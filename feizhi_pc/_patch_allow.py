import io
p = "autoreply.py"
s = io.open(p, encoding="utf-8").read()

# 1) 白名单：None = 全部放行
old = 'DEFAULT_ALLOW = {"<WXID_FRIEND_A>"}'
assert s.count(old) == 1
new = ('# ★ 2026-10-28 多用户：None = 不再用白名单挡人，所有好友都能找她说话。\n'
       '#   陌生人靠 relation 档位（persona.style_block）控制口吻 —— 先客气、后熟。\n'
       'DEFAULT_ALLOW: set[str] | None = None')
s = s.replace(old, new, 1)

old = "        self.allow = allow if allow is not None else set(DEFAULT_ALLOW)"
assert s.count(old) == 1
new = ("        if allow is not None:\n"
       "            self.allow = set(allow)\n"
       "        elif DEFAULT_ALLOW is not None:\n"
       "            self.allow = set(DEFAULT_ALLOW)\n"
       "        else:\n"
       "            self.allow = None          # None = 全部放行")
s = s.replace(old, new, 1)

# 2) generator 记住这个人的关系档位与称呼
old = 'def _build_system(self, context: str, complex_query: bool, now_str: str) -> str:'
assert s.count(old) == 1
s = s.replace(old, old, 1)

old = "            block = style_block(include_emoji=True)"
assert s.count(old) == 1
new = ("            block = style_block(include_emoji=True,\n"
       "                               relation=getattr(self, \"relation\", \"intimate\"),\n"
       "                               peer_name=getattr(self, \"peer_name\", \"\"))")
s = s.replace(old, new, 1)

# 3) 每轮把当前这个人的档位交给 generator
old = "                self.gen.memory_ctx = self.peers.get(peer).memory.render()"
assert s.count(old) == 1
new = ("                _st_now = self.peers.get(peer)\n"
       "                self.gen.relation = _st_now.relation.level\n"
       "                self.gen.peer_name = _st_now.relation.display_name(peer)\n"
       "                self.gen.memory_ctx = _st_now.memory.render()")
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("白名单放开 + 档位注入 完成")
