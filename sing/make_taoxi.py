"""《潮汐》翻唱流水线：截取人声片段 → 提 F0 → SVC 换音色 → 16k PCM。"""
import subprocess
import sys
from pathlib import Path

SING = Path(r"<PROJECT_ROOT>\sing")
SRC = SING / "source"
FFMPEG = (r"C:\Users\api62\AppData\Local\Microsoft\WinGet\Packages"
          r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
          r"\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe")

START = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
PROMPT = Path(sys.argv[3]) if len(sys.argv) > 3 else SRC / "feizhi_clean8s.wav"

vocal = SRC / "taoxi_vocal.wav"
clip = SRC / "taoxi_clip.wav"
if not vocal.exists():
    raise SystemExit("没有人声文件，先跑 separate.py")

# 1) 截一段（避开前奏，取主歌/副歌）
subprocess.run([FFMPEG, "-y", "-ss", str(START), "-t", str(DUR), "-i", str(vocal),
                "-ar", "24000", "-ac", "1", str(clip)],
               check=True, capture_output=True)
print("截取 %.0fs~%.0fs -> %s" % (START, START + DUR, clip), flush=True)

sys.path.insert(0, str(SING / "SoulX-Singer"))
from preprocess.tools.f0_extraction import F0Extractor  # noqa: E402

RMVPE = SING / "pretrained_models" / "SoulX-Singer-Preprocess" / "rmvpe" / "rmvpe.pt"
f0ex = F0Extractor(str(RMVPE), device="cuda", is_half=True,
                   target_sr=24000, hop_size=480, verbose=False)

pf0 = SRC / "prompt_f0.npy"
tf0 = SRC / "clip_f0.npy"
p = f0ex.process(str(PROMPT), f0_path=str(pf0))
t = f0ex.process(str(clip), f0_path=str(tf0))
print("prompt F0 %s voiced %.1f%%" % (p.shape, (p > 0).mean() * 100))
print("target F0 %s voiced %.1f%%" % (t.shape, (t > 0).mean() * 100), flush=True)

PITCH = sys.argv[4] if len(sys.argv) > 4 else "0"   # 补正半音数；0 = 保持原唱音高

# 3) SVC
out_dir = SING / "outputs" / "taoxi"
cmd = [str(SING / ".venv" / "Scripts" / "python.exe"), "-u", "-m", "cli.inference_svc",
       "--device", "cuda",
       "--model_path", str(SING / "pretrained_models" / "SoulX-Singer" / "model-svc.pt"),
       "--config", "soulxsinger/config/soulxsinger.yaml",
       "--prompt_wav_path", str(PROMPT),
       "--target_wav_path", str(clip),
       "--prompt_f0_path", str(pf0),
       "--target_f0_path", str(tf0),
       "--save_dir", str(out_dir),
       # ★ 不加 --auto_shift：它会自动把输出音域对齐到参考音频的音域。
       #   实测参考是她说话的 233Hz、原唱是 362Hz，auto_shift 会把整首歌
       #   往下压 7.6 个半音，高音区从 564Hz 砍到 377Hz —— 听感就是"平、没情绪、
       #   高音消失"。保持原唱音高，只换音色。
       "--pitch_shift", PITCH, "--fp16"]
import os
env = os.environ.copy()
env["PYTHONPATH"] = str(SING / "SoulX-Singer")
r = subprocess.run(cmd, cwd=str(SING / "SoulX-Singer"), capture_output=True,
                   text=True, encoding="utf-8", errors="replace", env=env, timeout=1800)
print(r.stdout[-800:] if r.stdout else "")
if r.returncode != 0:
    print("SVC 失败:", (r.stderr or "")[-800:])
    sys.exit(1)
gen = out_dir / "generated.wav"
print("生成:", gen, "%.2f MB" % (gen.stat().st_size / 1048576) if gen.exists() else "缺失")

# 3) 16k PCM
pcm = out_dir / "cover16k.pcm"
subprocess.run([FFMPEG, "-y", "-i", str(gen), "-ar", "16000", "-ac", "1",
                "-f", "s16le", str(pcm)], check=True, capture_output=True)
n = pcm.stat().st_size // 2
print("PCM: %s  样本 %d  时长 %.2fs" % (pcm, n, n / 16000.0))
