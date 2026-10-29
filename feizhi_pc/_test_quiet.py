"""允许安静结束：只有「纯应答 + 刚聊过」才可能不接话，其余一律照常回。"""
import sys
import time
import types

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

import autoreply

fails = 0


def check(name, got, want):
    global fails
    ok = got == want
    if not ok:
        fails += 1
    print(("PASS " if ok else "FAIL ") + name, "->", got, "" if ok else "want " + str(want))


class FakeStore:
    def __init__(self, last_ms):
        self.last_ms = last_ms

    def last_assistant_at(self, peer):
        return self.last_ms


def make_r(gap_min):
    r = object.__new__(autoreply.AutoReplier)
    r.store = FakeStore(int(time.time() * 1000) - int(gap_min * 60000))
    return r


def msg(peer="wxid_x"):
    return types.SimpleNamespace(peer_wxid=peer)


class Rnd:
    def __init__(self, v):
        self.v = v

    def __call__(self):
        return self.v


orig_random = autoreply.random.random

try:
    # 1) 纯应答 + 1 分钟前刚聊过 + 随机命中 → 不回
    autoreply.random.random = Rnd(0.0)
    check("纯应答+刚聊+命中", make_r(1)._should_end_quietly(msg(), "嗯"), True)
    check("同上带句号", make_r(1)._should_end_quietly(msg(), "好。"), True)
    check("同上带空格", make_r(1)._should_end_quietly(msg(), " 哈哈 "), True)

    # 2) 随机未命中 → 照常回
    autoreply.random.random = Rnd(0.99)
    check("随机未命中", make_r(1)._should_end_quietly(msg(), "嗯"), False)

    # 3) 隔太久（10 分钟）→ 必须回
    autoreply.random.random = Rnd(0.0)
    check("隔太久必回", make_r(10)._should_end_quietly(msg(), "嗯"), False)

    # 4) 有内容的话 → 必须回
    check("有内容必回", make_r(1)._should_end_quietly(msg(), "嗯我今天被老师骂了"), False)
    check("疑问必回", make_r(1)._should_end_quietly(msg(), "好？"), False)
    check("空串必回", make_r(1)._should_end_quietly(msg(), ""), False)

    # 5) 语音转写文字（长）→ 必须回
    check("语音转写必回", make_r(1)._should_end_quietly(
        msg(), "[他发了条语音，我没听清]"), False)

    # 6) 从没回过（last=0）→ 必须回
    r = object.__new__(autoreply.AutoReplier)
    r.store = FakeStore(0)
    check("从没回过必回", r._should_end_quietly(msg(), "嗯"), False)

    # 7) 开关关掉 → 必须回
    autoreply.QUIET_END_ENABLED = False
    check("开关关闭必回", make_r(1)._should_end_quietly(msg(), "嗯"), False)
    autoreply.QUIET_END_ENABLED = True
finally:
    autoreply.random.random = orig_random

# 8) 概率闸门大致落在 25% 附近
autoreply.random.random = orig_random
hits = sum(1 for _ in range(4000) if make_r(1)._should_end_quietly(msg(), "嗯"))
ratio = hits / 4000
print("命中率 = %.3f（目标 %.2f）" % (ratio, autoreply.QUIET_END_PROB))
check("命中率合理", 0.18 < ratio < 0.32, True)

print("\nFAILS =", fails)
sys.exit(0 if fails == 0 else 1)
