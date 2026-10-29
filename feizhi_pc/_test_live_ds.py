"""端到端验证：真实调用一次 LLM，确认返回正文不含 <ds_ 元数据。"""
import sys

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

from llm import LLMClient, strip_meta_tags, LLMError
import autoreply

llm = LLMClient()
system = ("你在扮演绯栀，一个 24 岁的女生，在微信上和男朋友聊天。"
          "只输出 JSON：{\"messages\":[{\"text\":\"...\"}],\"media\":null}。"
          "每次只说一两句，口语化，不要解释。")
user = "你还要不"

try:
    raw = llm.chat(system, user, max_tokens=300)
except LLMError as exc:
    print("LLM 调用失败:", exc)
    sys.exit(2)

print("原始返回:", repr(raw[:400]))
print("含 ds_ 标签:", "<ds_" in raw)

clean = autoreply.FeizhiReplyGenerator._sanitize_output(raw)
print("sanitize:", clean)
print("剥后含 ds_ :", "ds_" in clean)

import json
data = json.loads(clean)
texts = [m["text"] for m in data.get("messages", [])]
print("最终会发出的文本:", texts)
bad = [t for t in texts if "ds_" in t or t.strip() in ("Safe", "Unsafe")]
print("FAIL" if bad else "PASS", "污染条目:", bad)
sys.exit(1 if bad else 0)
