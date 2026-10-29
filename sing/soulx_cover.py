"""SoulX-Singer-SVC zero-shot singing voice conversion.

Wraps the upstream CLI so a single command does: f0 extraction (rmvpe) ->
model load -> segment-wise conversion -> wav out.
"""
import argparse
import os
import sys
import time

import numpy as np
import soundfile as sf
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
SX = os.path.join(HERE, "SoulX-Singer")
sys.path.insert(0, SX)

from preprocess.tools.f0_extraction import F0Extractor  # noqa: E402
from cli.inference_svc import build_model  # noqa: E402
from soulxsinger.utils.file_utils import load_config  # noqa: E402
from soulxsinger.utils.audio_utils import load_wav  # noqa: E402


def get_f0(extractor, wav_path, cache_dir, tag, sr):
    os.makedirs(cache_dir, exist_ok=True)
    f0_path = os.path.join(cache_dir, f"{tag}_f0.npy")
    if os.path.exists(f0_path):
        f0 = np.load(f0_path)
        print(f"[f0] cached {tag}: frames={len(f0)} voiced={(f0 > 0).mean():.3f}")
        return f0_path, f0
    f0 = extractor.process(wav_path, f0_path=f0_path, verbose=True)
    return f0_path, f0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="source/clean_vocals/yy_00.wav")
    ap.add_argument("--target", default="outputs/rvc/_taoxi45.wav")
    ap.add_argument("--out", default="outputs/soulx")
    ap.add_argument("--tag", default="")
    ap.add_argument("--model", default="pretrained_models/SoulX-Singer/model-svc.pt")
    ap.add_argument("--config", default="soulxsinger/config/soulxsinger.yaml")
    ap.add_argument("--rmvpe", default="pretrained_models/SoulX-Singer-Preprocess/rmvpe/rmvpe.pt")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--n-steps", type=int, default=32)
    ap.add_argument("--cfg", type=float, default=3.0)
    ap.add_argument("--pitch-shift", type=int, default=0)
    ap.add_argument("--auto-shift", action="store_true")
    ap.add_argument("--fp16", action="store_true")
    args = ap.parse_args()

    absi = lambda p: p if os.path.isabs(p) else os.path.abspath(os.path.join(HERE, p))
    prompt = absi(args.prompt)
    target = absi(args.target)
    out_dir = absi(args.out)
    args.model = absi(args.model)
    args.rmvpe = absi(args.rmvpe)
    os.makedirs(out_dir, exist_ok=True)
    os.chdir(SX)

    config = load_config(args.config)
    sr = config.audio.sample_rate
    print(f"[cfg] sample_rate={sr} hop={config.audio.hop_size} n_steps={args.n_steps} cfg={args.cfg}")

    cache = os.path.join(out_dir, "_f0cache")
    safe = lambda p: os.path.splitext(os.path.basename(p))[0]
    ex = F0Extractor(args.rmvpe, device=args.device, target_sr=sr,
                     hop_size=config.audio.hop_size)
    pt_f0_path, pt_f0 = get_f0(ex, prompt, cache, "pt_" + safe(prompt), sr)
    gt_f0_path, gt_f0 = get_f0(ex, target, cache, "gt_" + safe(target), sr)
    del ex
    torch.cuda.empty_cache()

    print(f"[model] loading {os.path.basename(args.model)} ...")
    t0 = time.time()
    model = build_model(args.model, config, device=args.device, use_fp16=args.fp16)
    print(f"[model] ready in {time.time() - t0:.1f}s")

    pt_wav = load_wav(prompt, sr).to(args.device)
    gt_wav = load_wav(target, sr).to(args.device)
    pt_f0_t = torch.from_numpy(pt_f0).unsqueeze(0).to(args.device)
    gt_f0_t = torch.from_numpy(gt_f0).unsqueeze(0).to(args.device)
    print(f"[io] prompt={pt_wav.shape[-1] / sr:.2f}s target={gt_wav.shape[-1] / sr:.2f}s")

    t0 = time.time()
    with torch.no_grad():
        audio, shift = model.infer(
            pt_wav=pt_wav,
            gt_wav=gt_wav,
            pt_f0=pt_f0_t,
            gt_f0=gt_f0_t,
            auto_shift=args.auto_shift,
            pitch_shift=args.pitch_shift,
            n_steps=args.n_steps,
            cfg=args.cfg,
            use_fp16=args.fp16,
        )
    print(f"[infer] done in {time.time() - t0:.1f}s shift={shift}")

    wav = audio.squeeze().float().cpu().numpy()
    name = (args.tag or "soulx") + ".wav"
    out_path = os.path.join(out_dir, name)
    sf.write(out_path, wav, sr)
    peak = float(np.max(np.abs(wav)))
    rms = float(np.sqrt(np.mean(wav ** 2)))
    print(f"[out] {out_path} dur={len(wav) / sr:.2f}s peak={peak:.3f} rms={rms:.4f}")


if __name__ == "__main__":
    main()
