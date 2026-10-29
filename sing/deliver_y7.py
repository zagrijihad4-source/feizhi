"""Wait for yinyin7 training, then render and deliver the samples automatically.

Deliverables:
  1  说话试音（TTS -> yinyin7）            -> WeChat voice + desktop wav/mp3
  2  《潮汐》翻唱（yinyin7 + EQ + 伴奏）    -> WeChat voice + desktop wav/mp3
  3  对比报告（yinyin5 vs yinyin7 vs e500）

Runs unattended in the background; everything is appended to deliver_y7.log.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SING = Path(r"<PROJECT_ROOT>\sing")
RVC = SING / "RVC"
OUT = SING / "outputs" / "rvc"
DESK = Path(os.path.expanduser("~")) / "Desktop" / "绯栀对比"
LOG = SING / "deliver_y7.log"
STATE = SING / "deliver_y7_state.json"

FEIZHI_PY = r"F:\AI课程软件\Python313\python.exe"
SING_PY = str(SING / ".venv" / "Scripts" / "python.exe")
TRAIN_LOG = RVC / "logs" / "yinyin7" / "train_console.log"
NO_WIN = 0x08000000 if os.name == "nt" else 0

SPOKEN = ("嗯，我在呢。今天挺累的吧，我看你从早忙到晚。"
          "先别管了，睡一会儿，明天再说。")


def log(msg):
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd, cwd=SING, timeout=1800, env_extra=None):
    env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    if env_extra:
        env.update(env_extra)
    return subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="ignore", timeout=timeout, creationflags=NO_WIN)


def wait_training(max_min=150):
    log("waiting for training to finish (log %s)" % TRAIN_LOG)
    t0 = time.time()
    while time.time() - t0 < max_min * 60:
        if TRAIN_LOG.exists():
            txt = TRAIN_LOG.read_bytes().decode("gbk", errors="replace")
            if "EXITCODE" in txt:
                m = re.search(r"轮次：(\d+)", txt)
                log("training finished, last epoch seen: %s" % (m.group(1) if m else "?"))
                return True
            if time.time() - TRAIN_LOG.stat().st_mtime > 900:
                log("WARNING: log not updated for 15 min, treating as stalled")
                return False
        time.sleep(20)
    log("TIMEOUT waiting for training")
    return False


def main():
    state = {}
    force = "--now" in sys.argv
    ok = True if force else wait_training()
    if not ok:
        # 训练没正常结束就不覆盖 liveness，只记录
        log("aborting delivery: training did not complete cleanly")
        return 1

    model = RVC / "assets" / "weights" / "yinyin7.pth"
    if not model.exists():
        log("ERROR: %s missing" % model)
        return 2
    log("model ready: %.1f MB" % (model.stat().st_size / 1048576))

    # 1) index
    log("[1/6] build faiss index")
    r = run([SING_PY, "-u", "-m", "train.train_index", "yinyin7", "v2", "logs", "8"], cwd=RVC)
    log("  rc=%s" % r.returncode)
    idx = sorted((RVC / "logs" / "yinyin7").glob("added_*.index"))
    if not idx:
        log("ERROR: no index produced")
        return 3
    index_path = str(idx[0])
    log("  index: %s" % Path(index_path).name)

    # 2) 潮汐 翻唱
    log("[2/6] convert 潮汐")
    conv = OUT / "taoxi_y6.wav"
    r = run([SING_PY, "-u", str(SING / "rvc_cover.py"), str(SING / "source" / "taoxi_vocal.wav"),
             str(conv), "--model", "yinyin7.pth", "--index-rate", "0", "--protect", "0.5"])
    log("  rc=%s" % r.returncode)
    if not conv.exists():
        log("ERROR: conversion failed: %s" % (r.stdout or "")[-300:])
        return 4

    # 3) EQ + 混音
    log("[3/6] EQ + mix")
    eqd = OUT / "taoxi_y6_eq.wav"
    run([SING_PY, str(SING / "eq_boost.py"), str(conv), str(eqd), "1.0"])
    mix = OUT / "taoxi_y6_mix.wav"
    run([SING_PY, str(SING / "mix_cover.py"), str(eqd),
         str(SING / "source" / "taoxi_inst.wav"), str(mix), "1.1", "0.72"])

    # 4) 说话试音
    log("[4/6] spoken sample")
    sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
    import numpy as np
    import soundfile as sf
    import tts
    pcm = tts.synthesize_pcm(SPOKEN, style="平静、像在跟人随口说话")
    raw = np.fromfile(str(pcm), dtype="<i2").astype(np.float32) / 32768.0
    src_wav = OUT / "speak7_src.wav"
    sf.write(str(src_wav), raw, 16000)
    speak_wav = OUT / "speak7_y6.wav"
    r = run([SING_PY, "-u", str(SING / "rvc_cover.py"), str(src_wav), str(speak_wav),
             "--model", "yinyin7.pth", "--index-rate", "0", "--protect", "0.5"])
    log("  rc=%s" % r.returncode)

    # 5) 导出：桌面 wav/mp3 + 微信 pcm
    log("[5/6] export")
    DESK.mkdir(parents=True, exist_ok=True)

    def export(src, stem, cut_window=None):
        x, sr = sf.read(str(src), dtype="float32", always_2d=True)
        if x.shape[1] > 1:
            x = x.mean(axis=1)
        else:
            x = x[:, 0]
        if cut_window:
            a, b = int(cut_window[0] * sr), int(cut_window[1] * sr)
            x = x[a:b]
        x = x / max(float(np.abs(x).max()), 1e-9) * 0.89
        wav = DESK / ("%s.wav" % stem)
        sf.write(str(wav), x, sr)
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "256k",
             str(DESK / ("%s.mp3" % stem))])
        # 微信 16k
        seg = x[83 * sr:128 * sr] if cut_window is None and len(x) > 130 * sr else x
        n16 = int(round(len(seg) * 16000 / sr))
        y = np.interp(np.linspace(0, len(seg) - 1, n16), np.arange(len(seg)), seg).astype(np.float32)
        y = y / max(float(np.abs(y).max()), 1e-9) * 0.92
        p = OUT / ("%s_16k.pcm" % stem)
        p.write_bytes((y * 32767).astype("<i2").tobytes())
        log("  %s: desktop %s  pcm %.1fs" % (stem, wav.name, len(y) / 16000))
        return p

    p_sing = export(mix, "试音-yinyin7-EQ-潮汐")
    p_speak = export(speak_wav, "试音-yinyin7-说话")

    # 6) 发微信
    log("[6/6] send to WeChat")
    for pcm_path, intro, hold in ((p_sing, "新模型唱的潮汐，去掉伴奏污染了", 50),
                                  (p_speak, "她的普通说话声", 22)):
        r = run([FEIZHI_PY, "-X", "utf8", str(SING / "sing_to_wx.py"),
                 str(pcm_path), intro, str(hold)], timeout=180)
        log("  sent %s -> %s" % (pcm_path.name, "ok" if "True" in (r.stdout or "") else "FAILED"))
        time.sleep(2)

    state["done_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    state["model"] = str(model)
    state["desktop"] = str(DESK)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    log("ALL DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
