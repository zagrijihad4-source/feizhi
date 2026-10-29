"""验证 <ds_safety> 泄漏已修复 + 拟人延迟已收敛。"""
import json
import re
import sys

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

import humanize
from llm import strip_meta_tags
import autoreply

DIRTY = ("<ds_safety>[用户未成年]否 [分类]其他 [判定]用户最后一句是询问聊天对象"
         "是否需要文件，属于日常对话，不涉及政治敏感内容。 [规则]无</ds_safety>Safe")

cases = [
    ("纯泄漏", DIRTY, ""),
    ("泄漏+正文", DIRTY + "要，谢谢", "要，谢谢"),
    ("正文夹标签", "要的" + DIRTY + "，你发我吧", "要的，你发我吧"),
    ("无闭合", "<ds_safety>[分类]其他 要的", ""),
    ("正常文本", "我不要，你自己留着", "我不要，你自己留着"),
    ("空串", "", ""),
    ("只 Safe", "Safe", ""),
    ("正常含 Safe 词", "Safe travels，路上小心", "Safe travels，路上小心"),
]

fails = 0
for name, inp, want in cases:
    got = strip_meta_tags(inp)
    ok = got == want
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name, "->", repr(got), "" if ok else ("want " + repr(want)))

# 走一遍完整的 _sanitize_output（这是真正会把标签发出去的路径）
plan_json = json.dumps({"messages": [{"text": DIRTY}], "media": None}, ensure_ascii=False)
out = autoreply.FeizhiReplyGenerator._sanitize_output(plan_json)
data = json.loads(out)
texts = [m["text"] for m in data["messages"]]
print("sanitize 后:", texts)
if any("ds_" in t for t in texts):
    print("FAIL sanitize 仍含 ds_ 标签")
    fails += 1
else:
    print("PASS sanitize 已剥净")

# 延迟收敛验证
long_text = "字" * 105
vals = [humanize.reaction_delay_ms(105) for _ in range(50)]
tv = [humanize.typing_delay_ms(long_text) for _ in range(50)]
print("reaction 105字: max=%dms avg=%dms（原上限 180000）" % (max(vals), sum(vals) // len(vals)))
print("typing  105字: max=%dms avg=%dms（原上限 20000）" % (max(tv), sum(tv) // len(tv)))
if max(vals) > 25000 or max(tv) > 9000:
    print("FAIL 延迟仍超上限")
    fails += 1
else:
    print("PASS 延迟已收敛到 <= 34s/条")

# 空正文判定（决定要不要重试 LLM）
len_cases = [
    ('{"messages":[{"text":"要啥呀"}]}', 3),
    ('{"messages":[{"text":"<ds_safety>x</ds_safety>Safe"}]}', 0),
    ("Safe", 0),
    ("", 0),
    ('{"messages":[{"text":""}]}', 0),
    ("纯文本回复", 5),
]
for s, want in len_cases:
    got = autoreply._reply_text_len(s)
    ok = got == want
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + repr(s[:38]) + " -> " + str(got)
          + ("" if ok else " want " + str(want)))

print("\nFAILS =", fails)
sys.exit(1 if fails else 0)