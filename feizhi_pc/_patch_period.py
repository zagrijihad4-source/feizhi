import io
p = "memrec.py"
s = io.open(p, encoding="utf-8").read()

# 1) 新增时段词表
old = 'VAGUE_SLOT = ("今晚", "明晚", "昨晚", "待会儿", "刚才", "回头")'
assert s.count(old) == 1
new = '''VAGUE_SLOT = ("今晚", "明晚", "昨晚", "待会儿", "刚才", "回头")

# 纯时段词：只说"一天里的哪一段"，不指向具体哪一天。
# ★ 2026-10-28 实测缺陷（记忆系统 v2 漏网的一类）：
#   原文只有「辣椒炒肉」三个字，模型拿**消息发送时间**推断出"中午"，
#   写成「<OWNER>中午吃的是辣椒炒肉」。结构化字段明明 time_basis=unknown、
#   event_time=None，程序却不管正文 —— 几天后她就拿这句当事实问
#   「你中午不是吃的辣椒炒肉嘛，怎么又饿了呀」。
#   这和 v2 批评的「拿消息时间冒充原文信息」是同一个错的另一种写法。
# ★ **只标记、不删除**：删了会坏语义（「<OWNER>晚上不吃饭」会变成「<OWNER>不吃饭」）。
PERIOD_WORDS = ("中午", "早上", "早晨", "上午", "下午", "傍晚",
                "晚上", "夜里", "半夜", "凌晨", "白天", "深夜")'''
s = s.replace(old, new, 1)

# 2) 无时间依据分支：检测时段词并标复核
old = '''    left_amb = [w for w in AMBIGUOUS if w in out]
    if left_amb:
        notes.append("正文含歧义时间 %s → 保留原文，仅标记日期未定" % left_amb)
        review = True'''
assert s.count(old) == 1
new = '''    left_amb = [w for w in AMBIGUOUS if w in out]
    if left_amb:
        notes.append("正文含歧义时间 %s → 保留原文，仅标记日期未定" % left_amb)
        review = True
    # ★ 无时间依据时，正文里的时段词最可疑：原文多半没说，是模型看消息时间推的。
    left_period = [w for w in PERIOD_WORDS if w in out]
    if left_period:
        notes.append("正文含时段词 %s，但来源没有给出任何时间依据 —— "
                     "可能是拿消息发送时间推的，保留原文并标记复核" % left_period)
        review = True'''
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("时段词检测已接入（仅标记，不删词）")
