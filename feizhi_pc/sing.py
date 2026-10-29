"""绯栀唱歌：把 RVC 翻唱成品当成"她给你唱了一段"发出去。

曲库：`<PROJECT_ROOT>\\sing\\outputs\\rvc\\*_mix.wav`（44.1k 单声道，离线管线产出）。
绯栀只负责**取段 + 发送**，不做任何音频生成——RVC 翻唱是离线的，一条 3 分钟的歌
要几分钟去转，不能在对话里现做。

★ 为什么切 42 秒
  微信语音条上限 60 秒，实测 56 秒那版喂到 796160/896000 样本就断了（差 6.2 秒
  没喂完），42 秒留足编码余量，实测每段稳定 42.3~43.8 秒发完。
  （来源：sing/绯栀项目-功能与踩坑总览 3.1.5③）

★ 为什么用 ffmpeg 重采样
  不许用 numpy 线性插值：`np.interp` 会混叠。总览 4.3 明写要用 `resample_poly`
  这类多相滤波。这里直接交给 ffmpeg 一步做「截取 + 16k 单声道 + s16le」，
  既不引 scipy，也避开混叠。

★ 微信语音条只有 16 kHz 单声道 SILK
  8 kHz 以上物理上不存在，所以曲库里的高采样率只是中间产物，不做无谓的高频处理。
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
import time
from pathlib import Path

LOG = logging.getLogger("feizhi.sing")

LIB = Path(r"<PROJECT_ROOT>\sing\outputs\rvc")
CLIP_SEC = 42.0
# 默认从 20 秒开始：跳过前奏，直接进人声段
DEFAULT_START = 20.0

# ★ 交付级成品白名单：只有这里列出的才会进 prompt、才会被模型点名唱。
#   判据不是文件名后缀 —— `taoxi_final_mix.wav` 也以 `_final` 结尾，
#   但它是 10-21 用当时的模型渲染的（总览 6.1：yinyin1~7 音色基础存疑、废弃）。
#   现在库里真正经过认可的是下面两条 yinyin10 成品：
#     18-绯栀-樱花树下的约定-定稿.mp3  -> sakura_final_mix.wav
#     13-绯栀-沦陷-学过她咬字.mp3      -> lunxian_final_mix.wav
DELIVERED = {
    "sakura_final": "樱花树下的约定",
    "lunxian_final": "沦陷",
    # 2026-10-29 新做：他在微信里点名要的这首
    "yua_final": "雨爱",
}

# 文件名 → 曲名。只用于老版本文件的可读命名，不影响是否对外暴露。
TITLES = {
    "taoxi_y7": "潮汐",
    "taoxi_y5_eq": "潮汐",
    "taoxi_y5": "潮汐",
    "taoxi_hi": "潮汐",
    "taoxi_final": "潮汐",
    "taoxi_e500": "潮汐",
    "taoxi_yinyin_eq": "潮汐",
    "taoxi_yinyin": "潮汐",
    "lunxian_idx0": "沦陷",
    "lunxian_D": "沦陷",
    "lunxian": "沦陷",
    "gejian_idx0": "搁浅",
    "gejian": "搁浅",
}


def _stem_key(p: Path) -> str:
    return re.sub(r"_mix$", "", p.stem)


def tracks() -> list[dict]:
    """曲库清单。按修改时间倒序 —— 新渲染的排前面。

    ★ `public` 是**交付级**标记，只有 `*_final_mix.wav` 才算。
      曲库里大量 `taoxi_y5_*` / `taoxi_y7_*` 是废弃模型的试验版本
      （总览 6.1：yinyin1~7 全建在 batch 上，音色基础存疑），
      让模型照着一串「潮汐」去挑，它多半挑到被废弃的那版。
      所以对外只暴露 final，其余留着供排查，不进 prompt。
    """
    out = []
    if not LIB.exists():
        return out
    for p in LIB.glob("*_mix.wav"):
        key = _stem_key(p)
        out.append({
            "file": p.name,
            "title": DELIVERED.get(key) or TITLES.get(key, key),
            "sec": round(p.stat().st_size / 88200.0, 1),
            "mtime": p.stat().st_mtime,
            "public": key in DELIVERED,
        })
    out.sort(key=lambda x: -x["mtime"])
    return out


def catalog_text(limit: int = 6) -> str:
    """给 prompt 用的曲目清单：只列交付级成品，同名只保留最新。"""
    seen, lines = set(), []
    for t in tracks():
        if not t["public"] or t["title"] in seen:
            continue
        seen.add(t["title"])
        lines.append(t["title"])
        if len(lines) >= limit:
            break
    return "、".join(lines)


def find(name: str) -> Path | None:
    """按曲名或文件名定位。交付级成品优先，其次才考虑试验版本。"""
    name = (name or "").strip()
    if not name:
        return None
    items = tracks()
    for pool in ([t for t in items if t["public"]], items):
        for t in pool:
            if t["title"] == name:
                return LIB / t["file"]
    low = name.lower()
    for pool in ([t for t in items if t["public"]], items):
        for t in pool:
            if low in t["file"].lower() or low in t["title"]:
                return LIB / t["file"]
    return None


def make_pcm(name: str, start: float = DEFAULT_START,
             dur: float = CLIP_SEC) -> Path | None:
    """取段并转成微信可用的 16k 单声道 s16le PCM。失败返回 None。"""
    src = find(name)
    if src is None:
        LOG.warning("曲库里没有这首歌：%r（现有：%s）", name,
                    [t["title"] for t in tracks()][:8])
        return None
    total = src.stat().st_size / 88200.0
    # 尾段不足一个 CLIP_SEC 时回退起点，别把结尾截没
    if start + dur > total:
        start = max(0.0, total - dur)
    out = Path(tempfile.gettempdir()) / ("feizhi_sing_%d.pcm" % int(time.time() * 1000))
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-ss", "%.2f" % start, "-t", "%.2f" % dur,
           "-i", str(src), "-ac", "1", "-ar", "16000", "-f", "s16le", str(out)]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not out.exists() or out.stat().st_size < 32000:
        LOG.warning("取段失败：%s", (r.stderr or b"")[:200])
        return None
    return out


def sing(name: str, start: float = DEFAULT_START, dur: float = CLIP_SEC,
         peer: str | None = None) -> bool:
    """唱一段并发送。返回是否真的发出去了。

    ★ peer 会传给 say_pcm 用来按备注名精确切会话 —— 唱歌和语音共用
      「按住说话」，会话没打开同样是 calls=0（2026-10-28 修）。
    """
    import voice  # 延迟导入：voice 依赖 ctypes/hook，别在模块加载时就拉起来

    pcm = make_pcm(name, start, dur)
    if pcm is None:
        return False
    try:
        ok = voice.VoiceSender().say_pcm(pcm, max_hold=60.0, retries=1, peer=peer)
        LOG.info("唱歌 %r %.1fs -> %s", name, pcm.stat().st_size / 32000.0, ok)
        return bool(ok)
    except Exception as e:  # noqa: BLE001
        LOG.warning("唱歌发送异常：%r", e)
        return False
    finally:
        try:
            pcm.unlink(missing_ok=True)
        except OSError:
            pass
