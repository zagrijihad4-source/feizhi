import io
p = "autoreply.py"
s = io.open(p, encoding="utf-8").read()

old = '''                '★ messages 和 media 都是格式的一部分：\\n'
                '  messages —— 你要说的文字（2~4 条）。\\n''''
assert s.count(old) == 1
new = '''                '★ messages 和 media 都是格式的一部分：\\n'
                '  messages —— 你要说的文字（**1~3 条**）。\\n'
                '  ★★ 多条 = **把一句话分成几次说完**，不是几个独立的回答。\\n'
                '    每条接着上一条往下说，拆开读要像一段话被切成几口气 ——\\n'
                '    真人打了一半觉得还没说完，隔两秒又补一条，是这个感觉。\\n'
                '    ✗ 反例（三个独立回答，各说各的，像三个人在答同一句）：\\n'
                '      「我就是一个路人呗」/「我就是个普通人」/「你加错了吧」\\n'
                '    ✓ 正例（一句话分三口，顺着往下）：\\n'
                '      「我？」/「你先说清楚你是谁呀」/「这么加过来我一点印象都没有」\\n'
                '  ★ **一条能说完就别硬拆**。为了显得像真人才分成好几条，反而更假；\\n'
                '    微信里真人经常就是一条说完。\\n''''
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("format_rules 已要求多条必须连贯")
