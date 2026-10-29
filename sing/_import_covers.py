"""把桌面已交付的 yinyin10 成品整理进 panel/绯栀共用的曲库。

曲库约定：`<PROJECT_ROOT>\\sing\\outputs\\rvc\\*_mix.wav`（44.1k，panel 的 /api/song 按此后缀枚举）。
桌面那批是 mp3，统一转成单声道 44.1k wav；反正最终要塞进 16 kHz SILK，
mp3 的有损在这一步之前就已经注定了，转化不会再多损失可听的频段。
"""
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DESK = Path(r"C:\Users\api62\Desktop\绯栀对比")
LIB = Path(r"<PROJECT_ROOT>\sing\outputs\rvc")

# (桌面源文件, 曲库目标名, 曲名)
JOBS = [
    ("18-绯栀-樱花树下的约定-定稿.mp3", "sakura_final_mix.wav", "樱花树下的约定"),
    ("13-绯栀-沦陷-学过她咬字.mp3", "lunxian_final_mix.wav", "沦陷"),
]

for src_name, dst_name, title in JOBS:
    src = DESK / src_name
    dst = LIB / dst_name
    if not src.exists():
        print("跳过（源不存在）：%s" % src_name)
        continue
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
         "-ac", "1", "-ar", "44100", str(dst)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("失败 %s：%s" % (src_name, (r.stderr or "")[:200]))
        continue
    size = dst.stat().st_size
    print("OK %-24s -> %-22s %5.1f MB  %.1f 秒  《%s》"
          % (src_name[:24], dst_name, size / 1048576.0, size / 176400.0, title))
