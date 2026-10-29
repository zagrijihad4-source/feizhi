"""记忆把握程度：三种形态（str / {text} / {text,certainty}）都要正确入库与渲染。"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

from memory import FeizhiMemory

fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name, "->", repr(got), "" if ok else "want " + repr(want))


tmp = Path(tempfile.mkdtemp()) / "mem.json"
M = FeizhiMemory(tmp)

# 三种形态混着喂
M._add("facts", [
    "他不吃香菜",                                    # 纯字符串（老格式）
    {"text": "他最近在赶一个 PPT", "certainty": "mid"},
    {"text": "他说过他怕黑", "certainty": "low"},
    {"text": "他明确说过他不吃辣", "certainty": "high"},
    {"text": "他不吃香菜"},                          # 重复，应被去掉
    {"text": "   "},                                 # 空，应被去掉
    {"text": "", "certainty": "high"},               # 空，应被去掉
], 60)
M.add_event("10月18日 他加班到十点")

check("入库 4 条", len(M.facts()), 4)
check("纯字符串无 certainty", M.facts()[0].get("certainty"), None)
check("mid 保留", M.facts()[1].get("certainty"), "mid")
check("low 保留", M.facts()[2].get("certainty"), "low")
check("high 保留", M.facts()[3].get("certainty"), "high")
# 绝不能把 dict 的 str() 存成事实
check("无 dict 残渣", any("certainty'" in x.get("text", "") for x in M.facts()), False)

r = M.render()
check("render 有 mid 提示", "可能记岔" in r, True)
check("render 有 low 提示", "不太确定" in r, True)
check("high 不加提示", "- 他明确说过他不吃辣（" not in r, True)
check("纯字符串不加提示", "- 他不吃香菜（" not in r, True)
check("render 含记忆段", "你真正记得的事" in r, True)

# 重新加载后仍可读
M2 = FeizhiMemory(tmp)
check("重载后 certainty 还在", M2.facts()[1].get("certainty"), "mid")

# 老文件（只有纯字符串）也要能读
old = Path(tempfile.mkdtemp()) / "old.json"
old.write_text(json.dumps({"facts": [{"text": "旧事实", "added": "2026-10-01"}],
                           "events": [], "last_id": 3, "last_extract_ts": 0},
                          ensure_ascii=False), encoding="utf-8")
M3 = FeizhiMemory(old)
check("老文件可读", M3.facts()[0]["text"], "旧事实")
check("老文件无提示", "（" not in M3.render().split("关于<OWNER>：")[1].split("\n")[1], True)

print("\nFAILS =", fails)
sys.exit(0 if fails == 0 else 1)
