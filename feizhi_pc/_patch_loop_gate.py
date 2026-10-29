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

# 1) 待回访只对熟人以上登记
rep("""                    try:
                        self.peers.get(peer).life.add_loop(text)
                    except Exception as exc:  # noqa: BLE001
                        LOG.warning("登记待回访失败: %r", exc)""",
    """                    # ★ 边界感（2026-10-28 用户要求）：只对熟人以上登记「待回访」。
                    #   陌生人刚加就被几小时后追问"你上次那个到底怎样了"，
                    #   不是关心，是越界。stranger 阶段她只回应、不追问。
                    try:
                        _lp = self.peers.get(peer)
                        if _lp.relation.level != "stranger":
                            _lp.life.add_loop(text)
                    except Exception as exc:  # noqa: BLE001
                        LOG.warning("登记待回访失败: %r", exc)""",
    "add_loop 门禁")

# 2) 渲染时也不给陌生人看 loops
rep("""            _st_life = self.peers.get(peer).life
            _st_life.reload_shared()     # 她的日子是共享的，每次拿最新那份
            gen.life_ctx = _st_life.render()""",
    """            _st_life = self.peers.get(peer).life
            _st_life.reload_shared()     # 她的日子是共享的，每次拿最新那份
            # 陌生人看不到「你之前问过他……」那一段：那是关系痕迹，
            # 才刚加的人不该出现在她的挂念清单里。
            gen.life_ctx = _st_life.render(
                include_loops=(_st_now is not None
                               and _st_now.relation.level != "stranger"))""",
    "render 隐藏 stranger 的 loops")

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
for x in steps:
    print(" ", x)
