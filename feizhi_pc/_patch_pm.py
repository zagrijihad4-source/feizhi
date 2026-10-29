import io
p = "post_moment.py"
s = io.open(p, encoding="utf-8").read()
old = """    try:
        from life import FeizhiLife
        life = FeizhiLife().render()
    except Exception:  # noqa: BLE001
        pass"""
new = """    try:
        # 朋友圈只讲她自己的日子，读共享层就够（不掺任何人的关系私有层）
        from peer_state import self_life
        life = self_life().render()
    except Exception:  # noqa: BLE001
        pass"""
n = s.count(old)
if n != 1:
    raise SystemExit("命中 %d" % n)
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("post_moment.py 改好")
