"""用 MiMo 生成一段"她的声音"当 SVC 的音色参考（和聊天里听到的同一把嗓子）。"""
import sys
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")

from tts import synthesize_pcm
import voice as vmod

SRC = Path(r"<PROJECT_ROOT>\sing\source")

# 挑几句有起伏的话，别用平铺朗读腔 —— 参考音频的语气会影响 SVC 的输出质感
TEXTS = [
    "嗯……你这个人怎么这样啊。我刚才还在想，要是你今天也不来找我，我就真的不理你了。",
    "好啦好啦，我唱就是了。不过说好了啊，我五音不全，你听完不许笑我，听见没有？",
]

for i, txt in enumerate(TEXTS):
    style = vmod.style_for("娇嗔") if i == 0 else vmod.style_for("傲娇")
    pcm = synthesize_pcm(txt, style=style, out_dir=SRC)
    pcm = Path(pcm)
    wav = pcm.with_suffix(".wav")
    n = pcm.stat().st_size // 2
    print("第 %d 条: %s  %.2fs  wav存在=%s" % (i + 1, pcm.name, n / 16000.0, wav.exists()))
    if wav.exists():
        out = SRC / ("feizhi_ref%d.wav" % (i + 1))
        out.write_bytes(wav.read_bytes())
        print("   -> %s  %.2f MB" % (out, out.stat().st_size / 1048576))
