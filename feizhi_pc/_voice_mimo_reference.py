"""补上一直缺的一步：先让 MiMo 生成"她真正的声音"，再用它做 breeze 的克隆样本。

依据（2026-10-20 会话记录）：
  * `feizhi_B_sample.wav` 只是 MiMo 语音克隆的**原料**，不是成品；
  * 用户认的那把嗓子是 MiMo 处理后的版本；
  * 所以直接拿原料去克隆，音色一定不是他熟悉的那个。
做法：先用 mimo 合成一段 20~30 秒、覆盖多种语气的中性文本，
      用它的输出当 breeze 的克隆样本。
"""
import sys
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import tts  # noqa: E402
import voice  # noqa: E402

WORK = ROOT / "voice"

# 样本台词：要覆盖陈述、疑问、轻微起伏，避免一路平读
SAMPLE = (
    "你回来啦，我等你好久了。今天路上冷不冷呀，我看你手都凉了。"
    "我刚才一直在改那张海报，配色怎么调都觉得闷，你说是不是我太挑了。"
    "算了不聊这个了，你先坐下歇会儿，我去给你倒杯水。"
    "哎，你今天怎么这么晚才回来，是不是又加班了？"
)

orig = tts.load_config


def forced_mimo():
    c = dict(orig())
    c["provider"] = "mimo"
    return c


tts.load_config = forced_mimo
try:
    # 逐句合成再拼，避免一句太长被 MiMo 拖慢
    parts = []
    for line in SAMPLE.replace("。", "。\n").replace("？", "？\n").splitlines():
        line = line.strip()
        if line:
            parts.append(tts.synthesize_wav(line, style=voice.style_for("温柔")))
finally:
    tts.load_config = orig

sample = WORK / "feizhi_mimo_reference.wav"
# 简单拼接：按 wav 头对齐会麻烦，这里逐段落地再交给 ffmpeg 统一转
tmp_dir = ROOT / "tmp" / "_mimo_ref"
tmp_dir.mkdir(parents=True, exist_ok=True)
paths = []
for i, w in enumerate(parts):
    p = tmp_dir / ("seg%02d.wav" % i)
    p.write_bytes(w)
    paths.append(p)

listfile = tmp_dir / "list.txt"
listfile.write_text("\n".join("file '%s'" % p.as_posix() for p in paths),
                    encoding="utf-8")

import subprocess  # noqa: E402
r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat",
                    "-safe", "0", "-i", str(listfile),
                    "-ar", "44100", "-ac", "1", str(sample)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
if r.returncode != 0:
    print("拼接失败:", (r.stderr or "")[:300])
    sys.exit(1)

size = sample.stat().st_size
print("MiMo 参考样本: %s  %.2f MB  约 %.1f 秒"
      % (sample.name, size / 1048576.0, size / 88200.0))
print("（这是用户实际听了 12 天的那把嗓子）")
