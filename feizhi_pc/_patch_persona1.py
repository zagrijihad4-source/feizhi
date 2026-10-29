import io
p = "persona.py"
s = io.open(p, encoding="utf-8").read()

# 1) 在「认识经历」前后断开：把 73-75 那三行抽成 BACKSTORY_PEER
old_head = '''    "你和<OWNER>是这么认识的：大二那年你在一个公众号上发画，他每篇都留言。"'''
assert s.count(old_head) == 1
idx = s.index(old_head)
# 往前找到这段的起始引号行边界：上一行是 "\\n" 和空串收尾
prefix = s[:idx]
suffix = s[idx:]

old_tail_marker = '''    "★ 这些决定了你说话的样子，**别当设定背，让它自然漏出来**：\\n"'''
assert suffix.count(old_tail_marker) == 1
tidx = suffix.index(old_tail_marker)
peer_block = suffix[:tidx]
rest = suffix[tidx:]

# prefix 末尾是 `    "\\n"\n`，把它收尾成 )
new_prefix = prefix.rstrip()
assert new_prefix.endswith('"\\n"'), repr(new_prefix[-40:])
prefix_code = new_prefix + "\n)\n\n" + (
    "# 和<OWNER>的认识经历 —— **只给亲密档位**。\n"
    "# 对陌生人绝不能出现：她会以为自己认识对方，一开口就是恋人腔。\n"
    "BACKSTORY_PEER = (\n"
) + peer_block.rstrip()

s2 = prefix_code + rest
io.open(p, "w", encoding="utf-8", newline="\n").write(s2)
print("切分完成")
