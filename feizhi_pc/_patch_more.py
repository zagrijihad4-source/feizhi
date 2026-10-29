import io
p = "proactive.py"
s = io.open(p, encoding="utf-8").read()

pairs = [
    ("""                try:
                    from life import FeizhiLife
                    life_obj = FeizhiLife()
                    life = life_obj.render(include_loops=False)""",
     """                try:
                    # ★ 用进程级单例里这个人的那份：共享层给她自己的日子，
                    #   私有层给 open_loops（和谁的约定）。各自 new 一份会让
                    #   mark_followed 写到别的实例看不见的缓存里。
                    from peer_state import get_registry
                    life_obj = get_registry().get(self.cfg.peer).life
                    life_obj.reload_shared()
                    life = life_obj.render(include_loops=False)"""),

    ("""                from life import FeizhiLife
                FeizhiLife().mark_followed(self._followed_ids)""",
     """                from peer_state import get_registry
                get_registry().get(self.cfg.peer).life.mark_followed(
                    self._followed_ids)"""),
]

for old, new in pairs:
    n = s.count(old)
    if n != 1:
        raise SystemExit("命中次数不对（%d）：%r" % (n, old[:60]))
    s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("proactive.py 改好 2 处")

p = "post_moment.py"
s = io.open(p, encoding="utf-8").read()
old = """from life import FeizhiLife
life = FeizhiLife().render()"""
new = """# 朋友圈只讲她自己的日子，读共享层就够（不带任何人的关系私有层）
from peer_state import self_life
life = self_life().render()"""
n = s.count(old)
if n != 1:
    raise SystemExit("post_moment 命中 %d" % n)
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("post_moment.py 改好 1 处")
