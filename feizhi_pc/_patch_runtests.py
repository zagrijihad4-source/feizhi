import io
p = "_run_all_tests.py"
s = io.open(p, encoding="utf-8").read()
old = '''    "_test_default_branch.py",
    "_test_reflect.py",
]'''
assert s.count(old) == 1
new = '''    "_test_default_branch.py",
    "_test_reflect.py",
    # 2026-10-28 新增：多用户与记忆闸门
    "_test_gate.py",          # pending -> eligible 唯一出口
    "_test_mood_log.py",      # 情绪时间线
    "_test_loops.py",         # 待回访
    "_test_outguard.py",      # 输出守卫
    "_test_ctx_guard.py",     # 上下文闸门
    "_test_memory_input.py",  # 记忆输入校验
    "_test_quiet.py",         # 安静结束
    "_test_dssafety.py",      # 元数据泄漏
    "_test_voice_request.py", # 语音触发词
    "_test_interrupt.py",     # 打断改口
]'''
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("清单已扩充")
