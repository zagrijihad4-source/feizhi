"""语音情感 A/B：把「是不是克隆导致平淡」这件事变成可以听的对比。

三组，同一个文本：
  A 当前配置（voiceclone + feizhi_B_sample + 傲娇 style）
  B 改成预设音色「冰糖」，不走克隆
  C 克隆，但把 style 指令写得更具体（推动韵律）

产物放桌面 `语音诊断\\`，synthesize_wav 直接给 wav，不经过微信语音条，
所以听到的是模型原样输出，不被 16k SILK 抹平。
"""
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402
import voice  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
OUT.mkdir(parents=True, exist_ok=True)

TEXT = "月——亮——绕呀绕，樱花树下的约定……唔，后面那句调我老是记不住，你别笑我啊。"
PLAIN = "你今天到底几点睡的，眼睛都睁不开了吧，还嘴硬说没困。"

CUSTOM_STYLE = (
    "角色：19岁杭州女孩，美院大二，嘴硬心软，有点俏皮。\n"
    "场景：跟喜欢的男生微信聊天，她刚唱跑调了，有点不好意思又要强撑。\n"
    "指导：前半句拖着尾音像真的在哼，后半句突然变小、语速变快，"
    "句尾带一点心虚的笑，最后一句轻轻收掉，别平铺直叙。"
)

CASES = [
    ("A-当前克隆-唱歌句", TEXT, dict(model="mimo-v2.5-tts-voiceclone",
                                    style=voice.style_for("傲娇"))),
    ("B-预设音色冰糖-同一句", TEXT, dict(voice="冰糖", model="mimo-v2.5-tts",
                                         style=voice.style_for("傲娇"))),
    ("C-克隆-强情感style-说话", PLAIN, dict(model="mimo-v2.5-tts-voiceclone",
                                            style=CUSTOM_STYLE)),
]

for name, text, kw in CASES:
    try:
        wav = tts.synthesize_wav(text, **kw)
    except Exception as e:  # noqa: BLE001
        print("%-22s 失败 %r" % (name, e))
        continue
    p = OUT / (name + ".wav")
    p.write_bytes(wav)
    print("%-22s %5.2f 秒  %6.0f KB  %s" % (name, len(wav) / 32000.0, len(wav) / 1024.0, p.name))

print()
print("目录：%s" % OUT)
