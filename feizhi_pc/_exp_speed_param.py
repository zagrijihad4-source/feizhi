# -*- coding: utf-8 -*-
"""验证 voice_settings.speed 的效力，为「分句变速 + 拼接」做依据。

如果 speed 1.2 / 0.9 能把同一句话的时长拉开 25% 以上，那么分句生成、
每句用不同 speed、再拼起来，就能造出真正的句内快慢 —— 这是 instructions
做不到的（实测：一提「快慢」总时长反而变长）。
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts   # noqa: E402

VID = "voc_f6hmxqkrnj8e"
TEXT = "刚在改稿子呢"


def dur_of(wav_bytes: bytes, tag: str) -> float:
    tmp = Path(tempfile.mkdtemp()) / ("%s.wav" % tag)
    tmp.write_bytes(wav_bytes)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(tmp), "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    import re
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr or "")
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def main() -> int:
    base = None
    for speed in (None, 0.85, 1.0, 1.15, 1.3):
        try:
            wav = tts._breeze_synthesize(TEXT, None, VID, None, 120, speed=speed)
        except Exception as exc:  # noqa: BLE001
            print("speed=%-5s 失败 %r" % (speed, exc))
            continue
        d = dur_of(wav, "s%s" % speed)
        if base is None:
            base = d
        print("speed=%-5s 时长 %.2fs   相对基准 %+.0f%%"
              % (speed, d, (d - base) / base * 100 if base else 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
