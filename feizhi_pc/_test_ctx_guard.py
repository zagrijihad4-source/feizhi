"""表情发送的 ctx 过期闸门：过期/缺失一律不发（实测硬发会把微信弄崩）。"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

import bridge as bridge_mod
from bridge import HookBridge

fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name, "->", got, "" if ok else "want " + str(want))


root = Path(tempfile.mkdtemp())
b = HookBridge(root=root)
ctl = root / "bridge" / "control"
ctl.mkdir(parents=True, exist_ok=True)
ctx = ctl / "ctx_override.txt"

calls = []
b._submit = lambda kind, wxid, payload, timeout: (calls.append((kind, payload)),
                                                  {"ok": True})[1]

# 1) 没有 ctx 文件 → 不发
check("无 ctx 不发", b.send_sticker("wxid_a", 4, "fav"), False)
check("无 ctx 无调用", len(calls), 0)
check("ctx_age_sec 缺失", b.ctx_age_sec(), None)

# 2) 过期 ctx（模拟昨晚 19:35 那种 5 小时前）→ 不发
ctx.write_text("deadbeef" * 4, encoding="utf-8")
old = time.time() - 5 * 3600
os.utime(ctx, (old, old))
age = b.ctx_age_sec()
check("过期年龄 > 上限", age > HookBridge.CTX_MAX_AGE_SEC, True)
check("过期不发", b.send_sticker("wxid_a", 4, "fav"), False)
check("过期无调用", len(calls), 0)

# 3) 新鲜 ctx → 正常发
now = time.time()
os.utime(ctx, (now, now))
check("新鲜可发", b.send_sticker("wxid_a", 4, "fav"), True)
check("新鲜有调用", len(calls), 1)
check("type=8", calls[0][0], "8")
check("payload=4", calls[0][1], "4")

# 4) type=12 同样受保护
calls.clear()
os.utime(ctx, (old, old))
check("过期 type12 不发", b.send_sticker("wxid_a", 1, "pack"), False)
os.utime(ctx, (now, now))
check("新鲜 type12 可发", b.send_sticker("wxid_a", 1, "pack"), True)
check("type=12", calls[0][0], "12")

# 5) index 负数仍然拒
check("负 index", b.send_sticker("wxid_a", -1, "fav"), False)

# 6) 上限值合理性：历史记录说上下文真实寿命约 30 秒，5 分钟已经算宽松
check("上限 <= 600 秒", bridge_mod.HookBridge.CTX_MAX_AGE_SEC <= 600, True)
check("上限 >= 60 秒", bridge_mod.HookBridge.CTX_MAX_AGE_SEC >= 60, True)

print("\nFAILS =", fails)
sys.exit(0 if fails == 0 else 1)
