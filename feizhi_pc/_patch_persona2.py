import io
p = "persona.py"
s = io.open(p, encoding="utf-8").read()

TRAIT = '    "★ 这些决定了你说话的样子，**别当设定背，让它自然漏出来**：\\n"'
assert s.count(TRAIT) == 1
ti = s.index(TRAIT)

# 性格推导一直到 BACKSTORY_PEER 的闭合括号
close_after = s.index("\n)\n", ti)
traits = s[ti:close_after]           # 性格推导那几行
assert "偶尔（很少）你会安静下来" in traits, "抓取范围不对"

# 1) 从 BACKSTORY_PEER 里摘掉
s = s[:ti] + s[close_after:]

# 2) 塞回 BACKSTORY 的闭合括号前
anchor = '''    "半夜会踩你脸。你画画的时候它趴在旁边，尾巴扫你的手。\\n"
    "\\n"
)
'''
assert s.count(anchor) == 1
s = s.replace(anchor,
              '''    "半夜会踩你脸。你画画的时候它趴在旁边，尾巴扫你的手。\\n"
    "\\n"
''' + traits + "\n)\n", 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("性格推导已移回 BACKSTORY")
