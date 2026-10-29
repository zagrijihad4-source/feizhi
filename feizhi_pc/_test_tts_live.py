"""实测 TTS：普通语句 vs (唱歌) 标签，量出真实语速和时长。

目的：验证两件事
  1. mimo voiceclone 现在是否还通（配置是 10-15 的，5 天没验证过）；
  2. `(唱歌)` 这种拖长音风格下，VOICE_MAX_CHARS=40 字会合成多长。
     日志里 10-19 那条 40 字唱歌合成了 21.28 秒，而正常口语约 4 字/秒（≈10 秒）。
"""
import io
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402

PUNCT = set("…—，。、！？;；:：(）)\"'“”‘’ ")


def chars_of(text):
    return len([c for c in text if c not in PUNCT])


CASES = [
    ("普通", "你今天吃饭了没，别又光顾着改稿。"),
    ("唱歌", "(唱歌)月—亮—绕呀绕，潮水退了又涨……我数着浪一遍遍，后面的词我忘了。"),
]

for name, text in CASES:
    n = chars_of(text)
    try:
        wav = tts.synthesize_wav(text)
    except Exception as e:  # noqa: BLE001
        print("%-4s 失败：%r" % (name, e))
        continue
    try:
        with wave.open(io.BytesIO(wav)) as w:
            rate = w.getframerate()
            dur = w.getnframes() / float(rate)
    except Exception as e:  # noqa: BLE001
        print("%-4s 合成成功 %d 字节，但解析 wav 失败：%r" % (name, len(wav), e))
        continue
    print("%-4s 成功  %.2f 秒  采样率=%d  有效字=%d  语速=%.2f 字/秒"
          % (name, dur, rate, n, n / dur if dur else 0))
