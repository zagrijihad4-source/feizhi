"""Breeze 语音质量第一轮对照。

依据官方文档：
  * instructions 应短（示例都是一句话），2-3 个方向就够；
  * guidance_scale 范围 1-10，表现性段落建议 1-3；
  * voice_settings.speed 是语速倍率，比在 instructions 里写「语速偏快」精确。

本轮只动两个变量：instructions 长度、speed。文本与音色固定，其他不动。
产物同时留在桌面供反复听，并可选发送到微信（16k SILK 会压掉高频，最终听感必须在微信里定）。
"""
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402
import voice  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
TEXT = "你今天几点睡的呀，眼睛都睁不开了吧，[叹气] 还嘴硬说没困。"

# 现在生产用的那段（MOODS 温柔档 + 两条节奏），作为基线
LONG = voice.style_for("温柔")

# 文档风格：一句话，两三个方向
SHORT = "像跟男朋友说话那样说：语气软，带点心疼，别念稿。"

CASES = [
    ("A-长三段式", LONG, None),
    ("B-短一句", SHORT, None),
    ("C-短一句-慢0.9", SHORT, 0.9),
    ("D-短一句-快1.1", SHORT, 1.1),
]

cfg = tts.load_config()
made = []
for name, instr, speed in CASES:
    b = dict(cfg.get("breeze") or {})
    if speed is not None:
        b["speed"] = speed
    # 直接调底层，绕开 tts 的 style 通道以便逐项控制
    cfg2 = dict(cfg)
    cfg2["breeze"] = b
    wav = tts._breeze_synthesize(TEXT, instr, None, None, 90)
    wav_path = OUT / ("M-%s.wav" % name)
    wav_path.write_bytes(wav)
    pcm = ROOT / "tmp" / ("_vt_%s.pcm" % name.split("-")[0])
    tts.to_wechat_pcm(wav, pcm)
    made.append((name, wav_path, pcm))
    print("%-14s wav %6.0f KB  指令 %2d 字  speed=%s"
          % (name, len(wav) / 1024.0, len(instr), speed))

print()
print("桌面目录：%s" % OUT)
print("pcm 备好：%d 条" % len(made))
