"""保存新音色并用它合成同一句话，与旧音色对比。"""
import json
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

KEY = "<BREEZE_API_KEY>"
BASE = "https://api.breezeblue.ai"

H = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}
GID = "gvi_rdaucqjahts9"

r = requests.post(BASE + "/v1/voice-previews/%s/save" % GID, headers=H,
                  json={"voice_name": "FeizhiReal", "language_code": "zh"}, timeout=180)
print("save HTTP", r.status_code)
if r.status_code != 200:
    print((r.text or "")[:300])
    sys.exit(1)
vid = r.json().get("voice_id")
print("新 voice_id =", vid)

import tts  # noqa: E402
import voice  # noqa: E402

OUT = Path(r"C:\Users\api62\Desktop\语音诊断")
TEXT = "你今天几点睡的呀，我看你都困成这样了。"
OLD_ID = "voc_uj5qvdgfhuhz"
STYLE = voice.style_for("温柔")

for tag, voice_id in (("旧-合成样本", OLD_ID), ("新-真实样本", vid)):
    wav = tts._breeze_synthesize(TEXT, STYLE, voice_id, None, 90, guidance=8)
    (OUT / ("BB-%s.wav" % tag)).write_bytes(wav)
    pcm = ROOT / "tmp" / ("_bb_%s.pcm" % tag.split("-")[1])
    tts.to_wechat_pcm(wav, pcm)
    print("%-12s %5.0f KB  pcm %.1fs" % (tag, len(wav) / 1024.0,
                                         pcm.stat().st_size / 32000.0))

Path(ROOT / "breeze_voice.json").write_text(
    json.dumps({"voice_id": vid, "voice_name": "FeizhiReal", "language_code": "zh",
                "source_sample": "sing/source/sep_test/yy_12_vocal.wav",
                "note": "音音子真实分离人声克隆；旧 voc_uj5qvdgfhuhz 来自 voicedesign 合成样本"},
               ensure_ascii=False, indent=2), encoding="utf-8")
print("breeze_voice.json 已更新")

print()
A = r'''
import sys, numpy as np, parselmouth, soundfile as sf
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
for p in sorted(Path(r"C:\Users\api62\Desktop\语音诊断").glob("BB-*.wav")):
    x, sr = sf.read(str(p), dtype="float32", always_2d=True)
    x = x.mean(axis=1).astype(np.float64)
    dur = len(x) / sr
    pi = parselmouth.Sound(x, sampling_frequency=sr).to_pitch(
        time_step=0.01, pitch_floor=75, pitch_ceiling=700)
    f0 = pi.selected_array["frequency"]; voiced = f0 > 0; f0v = f0[voiced]
    half = len(f0v)//2
    drift = abs(f0v[:half].mean() - f0v[half:].mean()) if half > 10 else 0
    fr = max(1, int(sr * 0.02)); n = len(x) // fr
    rms = np.array([np.sqrt(np.mean(x[i*fr:(i+1)*fr]**2) + 1e-12) for i in range(n)])
    db = 20 * np.log10(rms + 1e-12)
    loud = db[db > db.max() - 40]
    print("%-16s %5.2fs F0=%6.1f sd=%5.1f 前后差=%5.1f 动态=%4.1f 静音=%4.1f%%"
          % (p.stem, dur, f0v.mean(), f0v.std(), drift,
             np.percentile(loud,95)-np.percentile(loud,5),
             float(np.mean(db < db.max()-35))*100))
'''
rr = subprocess.run([r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe", "-c", A],
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
print(rr.stdout or rr.stderr)
