"""Segment-wise RVC cover: convert a long vocal into the trained voice.

The single-shot CLI stalls on a full-length song, so we slice the input into
overlapping windows, run vc_single per window with one loaded model, skip
near-silent windows entirely, then cross-fade the pieces back together.

usage: python rvc_cover.py <input.wav> <output.wav> [--model NAME] [--pitch N]
"""
import argparse
import os
import shutil
import sys
import tempfile

import numpy as np
import soundfile as sf

RVC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "RVC")
sys.path.insert(0, RVC)

import infer.cli as C  # noqa: E402  (imports chdir into the RVC project root)

SEG = 25.0
OVERLAP = 0.5
SILENT_RMS = 0.005
XFADE = 0.02


def resample(x, sr_from, sr_to):
    if sr_from == sr_to:
        return x
    n = int(round(len(x) * sr_to / sr_from))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
        # ★ 2026-10-29 定版：统一用 yinyin10（最后一次训练的模型，2026-10-24）。
    #   之前默认 yinyin.pth 是最早那版，音色明显不对。
    #   其余模型保留供报告对比，别删。
    #   index-rate 保持 0：索引会把音素换成检索集里的，音色变"平均值"且容易唱错字。
    ap.add_argument("--model", default="yinyin10.pth")
    ap.add_argument("--index", default=None)
    ap.add_argument("--pitch", type=int, default=0)
    ap.add_argument("--index-rate", type=float, default=0.0,
                    help="0 = 不用索引，内容特征 100%% 忠实原唱（索引会换掉音素导致唱错字）")
    ap.add_argument("--protect", type=float, default=0.5,
                    help="保护原唱清辅音的比例，高一点咬字更清楚")
    ap.add_argument("--seg", type=float, default=SEG)
    args = ap.parse_args()

    src, sr = sf.read(args.input, dtype="float32", always_2d=True)
    src = src.mean(axis=1)
    dur = len(src) / sr
    print("input %.1fs @ %d Hz" % (dur, sr))

    model_path = C.resolve_model(args.model)
    os.environ["weight_root"] = str(model_path.parent)
    model_name = model_path.name
    speaker_count, speakers = C.load_model_metadata(model_path)
    sid = C.select_speaker(speaker_count, speakers, None)
    index_path = C.resolve_index(args.index, model_name, sid, args.index_rate)
    print("model=%s sid=%s index=%s" % (model_name, sid, os.path.basename(index_path or "")))

    from infer.vc.modules import VC

    config = C.create_config()
    vc = VC(config)
    vc.get_vc(model_name)

    tmp = tempfile.mkdtemp(prefix="rvccover_")
    pieces = []
    hop = args.seg - OVERLAP
    t = 0.0
    i = 0
    tgt_sr = None
    try:
        while t < dur:
            a = int(t * sr)
            b = min(int((t + args.seg) * sr), len(src))
            chunk = src[a:b]
            if len(chunk) < sr * 0.2:
                break
            rms = float(np.sqrt(np.mean(chunk * chunk)))
            if rms < SILENT_RMS:
                print("seg %02d %6.1f-%6.1fs  rms=%.4f  pass-through" % (i, t, t + len(chunk) / sr, rms))
                out = resample(chunk, sr, 40000)
                tgt_sr = tgt_sr or 40000
            else:
                seg_path = os.path.join(tmp, "seg_%02d.wav" % i)
                sf.write(seg_path, chunk, sr)
                status, result = vc.vc_single(
                    sid, seg_path, args.pitch, "rmvpe", index_path,
                    args.index_rate, 0, 1.0, args.protect,
                )
                if not result or result[1] is None or len(result[1]) == 0:
                    print("seg %02d %6.1f-%6.1fs  FAILED -> pass-through" % (i, t, t + len(chunk) / sr))
                    print(status)
                    out = resample(chunk, sr, 40000)
                    tgt_sr = tgt_sr or 40000
                else:
                    tgt_sr = result[0]
                    out = result[1]
                    print("seg %02d %6.1f-%6.1fs  rms=%.4f  ok %.2fs" % (i, t, t + len(chunk) / sr, rms, len(out) / tgt_sr))
            pieces.append(out)
            i += 1
            t += hop
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not pieces:
        raise SystemExit("nothing produced")

    # The windows overlap by OVERLAP seconds, so blend exactly that much and
    # keep the tail of the new piece. Anything else changes the total duration.
    n_ov = int(OVERLAP * tgt_sr)
    total = np.zeros(0, dtype=np.float32)
    for k, p in enumerate(pieces):
        p = np.asarray(p, dtype=np.float32)
        if k == 0:
            total = p.copy()
            continue
        if len(p) <= n_ov or len(total) <= n_ov:
            total = np.concatenate([total, p])
            continue
        fade = np.linspace(0.0, 1.0, n_ov, dtype=np.float32)
        blend = total[-n_ov:] * (1.0 - fade) + p[:n_ov] * fade
        total = np.concatenate([total[:-n_ov], blend, p[n_ov:]])

    peak = float(np.abs(total).max())
    if peak > 0.99:
        total = total / peak * 0.99
    sf.write(args.output, total, tgt_sr)
    print("wrote %s  %.2fs @ %d Hz  peak=%.3f" % (args.output, len(total) / tgt_sr, tgt_sr, float(np.abs(total).max())))


if __name__ == "__main__":
    main()
