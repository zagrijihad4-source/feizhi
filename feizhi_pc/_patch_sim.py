import io
p = "_sim_web.py"
s = io.open(p, encoding="utf-8").read()

old = "from llm import LLMClient                      # noqa: E402"
assert s.count(old) == 1
s = s.replace(old, "import outguard                                # noqa: E402\nfrom llm import LLMClient                      # noqa: E402", 1)

old = '''        msgs = [str(getattr(m, "text", "") or "") for m in (plan.messages or [])]
        msgs = [m for m in msgs if m.strip()]'''
assert s.count(old) == 1
new = '''        raw = [str(getattr(m, "text", "") or "") for m in (plan.messages or [])]
        # ★ 必须过 outguard：实测模型在没有历史时会直接把 system prompt 的标题
        #   吐出来（「【你的来处 · 这不是设定，是你的记忆】 我叫绯栀……」）。
        #   线上是 _send_plan 里拦的，这里单独跑生成链路，得自己拦一遍。
        msgs = []
        for t in raw:
            if not t.strip():
                continue
            clean, gstate = outguard.guard(t, regenerate=None,
                                           log=lambda m: print("  outguard:", m))
            if not clean:
                print("  outguard 丢弃一条（%s）：%r" % (gstate, t[:50]))
                continue
            if gstate != "pass":
                print("  outguard 处置=%s -> %r" % (gstate, clean[:50]))
            msgs.append(clean)'''
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("模拟器已接 outguard")
