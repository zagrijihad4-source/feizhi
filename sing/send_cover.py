"""把生成的翻唱 wav 转成 16k 单声道 PCM，并当微信语音发出去。"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

WAV = Path(r"<PROJECT_ROOT>\sing\outputs\feizhi_cover\generated.wav")
PCM = Path(r"<PROJECT_ROOT>\sing\outputs\feizhi_cover\cover16k.pcm")
FFMPEG = (r"C:\Users\api62\AppData\Local\Microsoft\WinGet\Packages"
          r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
          r"\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe")

if not WAV.exists():
    raise SystemExit("没有 generated.wav")

print("源文件 %.2f MB" % (WAV.stat().st_size / 1048576))
subprocess.run([FFMPEG, "-y", "-i", str(WAV), "-ar", "16000", "-ac", "1",
                "-f", "s16le", str(PCM)],
               check=True, capture_output=True)
n = PCM.stat().st_size // 2
print("PCM: %s  样本 %d  时长 %.2fs" % (PCM, n, n / 16000.0))

import voice

print("微信窗口 =", voice.find_wechat_window())
t0 = time.time()
ok = voice.VoiceSender().say_pcm(PCM, max_hold=40.0, retries=1)
print("发送结果 =", ok, " 耗时 %.1fs" % (time.time() - t0))
