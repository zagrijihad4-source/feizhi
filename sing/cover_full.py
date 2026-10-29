"""整首翻唱：把 target 切成若干段，模型只加载一次，逐段推理后拼接。

为什么不用 cli/inference_svc.py 循环调用：它每次进程启动都要重新加载
2.7GB 权重（约 1-2 分钟），7 段就是十几分钟纯等待。这里加载一次跑完。
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

SING = Path(r"<PROJECT_ROOT>\sing")
ROOT = SING / "SoulX-Singer"
sys.path.insert(0, str(ROOT))

from soulxsinger.utils.file_utils import load_config  # noqa: E402
from soulxsinger.utils.audio_utils import load_wav  # noqa: E402
from soulxsinger.models.soulxsinger_svc import SoulXSingerSVC  # noqa: E402
from preprocess.tools.f0_extraction import F0Extractor  # noqa: E402

PROMPT = SING / "source" / "yinyin_ref30.wav"
TARGET = SING / "source" / "taoxi_vocal.wav"
OUT_DIR = SING / "outputs" / "full"
MODEL = SING / "pretrained_models" / "SoulX-Singer" / "model-svc.pt"
CONFIG = ROOT / "soulxsinger" / "config" / "soulxsinger.yaml"
RMVPE = SING / "pretrained_models" / "SoulX-Singer-Preprocess" / "rmvpe" / "rmvpe.pt"

SEG = 24.0          # 每段秒数
OVERLAP = 0.5       # 交叉淡化重叠
BATCH = int(os.environ.get("COVER_BATCH", "0"))   # 只跑前 N 段（调试用）


def build_model(device="cuda", use_fp16=True):
    cfg = load_config(str(CONFIG))
    m = SoulXSingerSVC(cfg).to(device)
    ckpt = torch.load(str(MODEL), weights_only=False, map_location="cpu")
    m.load_state_dict(ckpt["state_dict"], strict=True)
    if use_fp16 and device.startswith("cuda"):
        m.half()
        m.mel.float()
    m.eval()
    return m, cfg


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("device =", device, flush=True)

    t0 = time.time()
    f0ex = F0Extractor(str(RMVPE), device=device, is_half=True,
                       target_sr=24000, hop_size=480, verbose=False)
    pf0 = f0ex.process(str(PROMPT), verbose=False)
    print("prompt F0 %s voiced %.1f%%" % (pf0.shape, (pf0 > 0).mean() * 100), flush=True)

    audio, sr = sf.read(str(TARGET))
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    dur = len(audio) / sr
    print("target %.2fs  sr=%d" % (dur, sr), flush=True)

    model, cfg = build_model(device)
    print("模型加载 %.1fs" % (time.time() - t0), flush=True)

    seg_samples = int(SEG * sr)
    hop = int((SEG - OVERLAP) * sr)
    starts = list(range(0, max(1, len(audio) - seg_samples + 1), hop))
    if not starts or starts[-1] + seg_samples < len(audio):
        starts.append(max(0, len(audio) - seg_samples))
    if BATCH:
        starts = starts[:BATCH]
    print("共 %d 段: %s" % (len(starts), [round(s / sr, 1) for s in starts]), flush=True)

    pieces = []
    for idx, st in enumerate(starts):
        seg = audio[st: st + seg_samples]
        seg_path = OUT_DIR / ("seg_%02d.wav" % idx)
        sf.write(str(seg_path), seg, sr)
        gf0 = f0ex.process(str(seg_path), verbose=False)
        pt = load_wav(str(PROMPT), cfg.audio.sample_rate).to(device)
        gt = load_wav(str(seg_path), cfg.audio.sample_rate).to(device)
        pt_f0 = torch.from_numpy(pf0).unsqueeze(0).to(device)
        gt_f0 = torch.from_numpy(gf0).unsqueeze(0).to(device)
        t1 = time.time()
        with torch.no_grad():
            gen, _shift = model.infer(
                pt_wav=pt, gt_wav=gt, pt_f0=pt_f0, gt_f0=gt_f0,
                auto_shift=False, pitch_shift=0,
                n_steps=32, cfg=3.0, use_fp16=(device == "cuda"))
        out = gen.squeeze().float().cpu().numpy()
        p = OUT_DIR / ("gen_%02d.wav" % idx)
        sf.write(str(p), out, cfg.audio.sample_rate)
        pieces.append((st / sr, out, cfg.audio.sample_rate))
        print("  段 %d/%d  起点 %.1fs  生成 %.1fs  用时 %.1fs"
              % (idx + 1, len(starts), st / sr, len(out) / cfg.audio.sample_rate,
                 time.time() - t1), flush=True)

    # 拼接（按起点放回全局时间轴，重叠处线性淡入淡出）
    out_sr = pieces[0][2]
    total = int(max(s / sr + len(o) / out_sr for s, o, sr in
                    [(st, o, out_sr) for st, o, _ in pieces]) * out_sr) + out_sr
    canvas = np.zeros(total, dtype=np.float32)
    wsum = np.zeros(total, dtype=np.float32)
    for st_sec, o, osr in pieces:
        st_i = int(st_sec * out_sr)
        n = len(o)
        w = np.ones(n, dtype=np.float32)
        fade = int(OVERLAP * out_sr)
        if fade > 0 and n > 2 * fade:
            w[:fade] = np.linspace(0, 1, fade)
            w[-fade:] = np.linspace(1, 0, fade)
        canvas[st_i: st_i + n] += o * w
        wsum[st_i: st_i + n] += w
    wsum[wsum < 1e-6] = 1.0
    full = canvas / wsum

    final = OUT_DIR / "taoxi_full.wav"
    sf.write(str(final), full, out_sr)
    print("\n完整成品: %s  %.2f MB  %.2fs"
          % (final, final.stat().st_size / 1048576, len(full) / out_sr))
    print("总耗时 %.1f 分钟" % ((time.time() - t0) / 60))
    return 0


if __name__ == "__main__":
    sys.exit(main())
