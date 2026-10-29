import sys

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
sys.stdout.reconfigure(encoding="utf-8")

from autoreply import FeizhiReplyGenerator as G

# (输入, 期望)  —— 期望 True = 应该触发语音兜底
CASES = [
    ("不行，我就要听声音", True),          # 2026-10-27 22:14 漏判的那句
    ("宝宝还是没发出来，你再试试", True),
    ("你重新发一遍好不好", True),
    ("还没有，宝宝再试一遍", True),
    ("发条语音吗，想听你说我爱你", True),
    ("唱首歌吧", True),
    ("语音", True),
    ("说句话给我听听", True),
    ("今天天气不错", False),
    ("再说一遍", False),                   # 指把话重说，不是发语音
    ("给我看看你画的", False),
    ("我吃过了", False),
]

bad = 0
for text, want in CASES:
    got = G._wants_voice(text)
    mark = "OK  " if got == want else "FAIL"
    if got != want:
        bad += 1
    print("%s %-24s 期望=%-5s 实际=%s" % (mark, text, want, got))
print()
print("失败 %d / %d" % (bad, len(CASES)))
sys.exit(1 if bad else 0)
