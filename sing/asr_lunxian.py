"""Transcribe the two fetched clips to confirm they are the 沦陷 cover."""
import glob
import json
import os

from faster_whisper import WhisperModel

HERE = os.path.dirname(os.path.abspath(__file__))
m = WhisperModel("small", device="cpu", compute_type="int8")
out = []
for p in sorted(glob.glob(os.path.join(HERE, "source", "dy_lunxian", "*.wav"))):
    try:
        segs, info = m.transcribe(p, language="zh", beam_size=1, vad_filter=True)
        text = "".join(s.text for s in segs).strip()
        dur = info.duration
    except Exception as e:
        text, dur = "ERR " + str(e)[:80], 0
    out.append({"file": os.path.basename(p), "dur": dur, "text": text})
    print("%s (%.1fs)\n  %s\n" % (os.path.basename(p), dur, text))

with open(os.path.join(HERE, "outputs", "lunxian_asr.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
