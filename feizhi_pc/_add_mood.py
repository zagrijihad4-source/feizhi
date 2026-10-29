import io
p = "voice.py"
s = io.open(p, encoding="utf-8").read()

# 在 "温柔" 档后面插入 "明快" 档
anchor = '''    "慵懒": {'''
assert s.count(anchor) == 1
new_block = '''    # 2026-10-29 按用户挑样本加的：同一句话三个变体里他选了这个
    # （另两个是「带笑出声」和原温柔档）。特点是不装温柔也不端着，
    # 声音往上走、有精神，但**不靠提高音调**——升调会把音色整个换掉。
    "明快": {
        "desc": "心情好，说话带笑",
        "style": (
            "说话轻快明亮，语速比平时快一点，尾音带一点笑意；"
            "整段是往上走的、有精神的，像刚碰上件好事还没说完。"
            "别硬装开心，也别拔高音调 —— 高兴是语速和语气的事。"
        ),
    },
    "慵懒": {'''
s = s.replace(anchor, new_block, 1)

# 默认档位也用它：他现在明确说喜欢这个调子
old = 'DEFAULT_MOOD = "娇嗔"'
assert s.count(old) == 1
s = s.replace(old, 'DEFAULT_MOOD = "明快"      # 2026-10-29 用户挑样本后定的默认调子', 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("已加「明快」档并设为默认")
