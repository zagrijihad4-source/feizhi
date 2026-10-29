"""诊断：对比目标人声与生成音频的 F0 曲线和能量包络，看起伏是不是被拉平了。"""
import sys
from pathlib import Path

import numpy as np

SING = Path(r"<PROJECT_ROOT>\sing")
sys.path.insert(0, str(SING / "SoulX-Singer"))

from preprocess.tools.f0_extraction import F0Extractor  # noqa: E402

RMVPE = SING / "pretrained_models" / "SoulX-Singer-Preprocess" / "rmvpe" / "rmvpe.pt"
f0ex = F0Extractor(str(RMVPE), device="cuda", is_half=True,
                   target_sr=24000, hop_size=480, verbose=False)


def analyze(path: Path, label: str) -> np.ndarray:
    f0 = f0ex.process(str(path), verbose=False)
    voiced = f0[f0 > 0]
    print("\n=== %s ===" % label)
    print("  %s" % path.name)
    print("  帧数 %d  发声比 %.1f%%" % (len(f0), (f0 > 0).mean() * 100))
    if len(voiced):
        print("  F0 范围 %.1f ~ %.1f Hz  均值 %.1f  标准差 %.1f" % (
            voiced.min(), voiced.max(), voiced.mean(), voiced.std()))
        # 半音标准差 = 音高起伏的客观量
        st = 12 * np.log2(voiced / 55.0)
        print("  音高起伏（半音标准差）%.2f  —— 真人唱歌通常 3~6，<2 就是被拉平了" % st.std())
    return f0


target = SING / "source" / "taoxi_clip.wav"
gen = SING / "outputs" / "taoxi" / "generated.wav"

f_t = analyze(target, "目标（潮汐原唱人声）")
f_g = analyze(gen, "生成（SVC 输出）")

# 对齐长度后算相关性
n = min(len(f_t), len(f_g))
a, b = f_t[:n], f_g[:n]
m = (a > 0) & (b > 0)
if m.sum() > 10:
    ra = 12 * np.log2(a[m] / 55.0)
    rb = 12 * np.log2(b[m] / 55.0)
    corr = float(np.corrcoef(ra, rb)[0, 1])
    print("\n共同发声帧 %d / %d" % (m.sum(), n))
    print("音高曲线相关系数 = %.3f   （1.0 表示完全跟随）" % corr)
    print("目标标准差 %.2f vs 生成标准差 %.2f  收缩 %.0f%%"
          % (ra.std(), rb.std(), (1 - rb.std() / ra.std()) * 100))
else:
    print("\n发声帧太少，无法对比")
