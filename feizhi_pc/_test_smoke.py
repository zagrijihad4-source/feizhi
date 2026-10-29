"""端到端冒烟：新加的人格段落 + 生活状态 + 回访，能不能产出合法回复。"""
import json
import sys

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

from life import FeizhiLife
from memory import FeizhiMemory
import autoreply

print("=== 1. 生活状态渲染（真实文件）===")
L = FeizhiLife()
r = L.render()
print(r or "（空）")
print("stats:", L.stats())
assert "手上正在弄的" in r or "心情" in r, "生活状态渲染异常"

print("\n=== 2. 记忆渲染（真实文件）===")
M = FeizhiMemory()
mr = M.render()
print(mr[:600] or "（空）")

print("\n=== 3. 人格段落是否含新内容 ===")
from persona import style_block
sb = style_block()
for kw in ("我们", "情绪有惯性", "心软是底色", "语气要软"):
    print(("OK  " if kw in sb else "MISS") + "  " + kw)
print("style_block 长度:", len(sb))

print("\n=== 4. 真实生成一次（验证加了新段落没破坏 JSON 输出）===")
gen = autoreply.FeizhiReplyGenerator()
gen.memory_ctx = mr
gen.life_ctx = r
gen.search_ctx = ""
gen.context_text = ("以下是你们最近的微信对话（从早到晚）。\n"
                    "<OWNER>：今天好累啊\n绯栀：那你先躺会儿，我给你说点废话哄你睡。\n"
                    "<OWNER>：嗯")
try:
    plan = gen.generate_plan("嗯")
except Exception as exc:  # noqa: BLE001
    print("生成失败:", exc)
    sys.exit(1)

texts = [getattr(m, "text", "") for m in plan.messages]
print("生成结果:", texts)
print("media:", getattr(gen, "pending_sticker", None), getattr(gen, "pending_image", None))

bad = [t for t in texts if "ds_" in t or t.strip() in ("Safe", "Unsafe") or t.startswith("{")]
if bad:
    print("FAIL 输出被污染:", bad)
    sys.exit(1)
if not any(t.strip() for t in texts):
    print("FAIL 输出为空")
    sys.exit(1)
print("PASS 输出干净、非空")

# 回访提取对生成的文本也能用
qs = FeizhiLife._extract_questions(" ".join(texts))
print("从回复里识别出的问句:", qs)
print("\n全部通过")
