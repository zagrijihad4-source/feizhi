# -*- coding: utf-8 -*-
"""绯栀的语音合成（TTS）—— 文本 → 微信语音可用的 16k 单声道 PCM。

链路：
    text --(MiMo TTS, OpenAI 兼容 chat 端点)--> wav
         --(ffmpeg 重采样)--> 16kHz / 单声道 / s16le PCM
         --(frida 注入 SILK 编码器)--> 微信语音消息

为什么是 16k 单声道：实测微信 4.1.9.23 语音消息的 SILK 编码器
（VoipEngine.dll!SKP_Silk_SDK_Encode）每帧 320 samples @16000 Hz，
所以喂进去的 PCM 必须正好是 16kHz / 单声道 / 16bit。

配置在 tts_config.json（含 key，不要写进代码或日志）。

用法：
    from tts import synthesize_pcm
    pcm = synthesize_pcm("喂，能听到吗")      # -> Path
音色可选：冰糖 / 茉莉 / 苏打 / 白桦 / Mia / Chloe / Milo / Dean / mimo_default
另有 mimo-v2.5-tts-voiceclone（传一段音频样本克隆音色）与 voicedesign（文字描述音色）。
"""
from __future__ import annotations

import base64
import hashlib
import io as _io
import json
import logging
import re
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOG = logging.getLogger("feizhi_pc.tts")

CONFIG_PATH = Path(__file__).with_name("tts_config.json")
CACHE_DIR = Path(r"<PROJECT_ROOT>\tmp\tts_cache")

# 微信语音消息 SILK 编码器的真实参数（2026-10-15 实测）
WECHAT_SAMPLE_RATE = 16000
WECHAT_CHANNELS = 1


class TTSError(RuntimeError):
    pass


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise TTSError("缺少配置文件：%s" % CONFIG_PATH)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def clone_sample_durl(path: str | Path) -> str:
    """把克隆样本音频转成 DataURL。

    voiceclone 模型的 audio.voice 必须是 DataURL（`data:audio/wav;base64,...`），
    传裸 base64 会直接 400：audio.voice must be a DataURL for voice clone model。
    """
    p = Path(path)
    if not p.exists():
        raise TTSError("克隆样本不存在：%s" % p)
    mime = "audio/mpeg" if p.suffix.lower() == ".mp3" else "audio/wav"
    return "data:%s;base64,%s" % (mime, base64.b64encode(p.read_bytes()).decode("ascii"))


def _breeze_synthesize(text: str, instructions: str | None = None,
                       voice: str | None = None, model: str | None = None,
                       timeout: int = 90, guidance: float | None = None,
                       speed: float | None = None) -> bytes:
    """Breeze Blue TTS（2026-10-27 接入，现为第一优先级）。

    与 mimo 的差异（都实测过）：
      * 端点 `POST /v1/text-to-speech/{voice_id}`，OpenAI 兼容体但**不是** chat 格式；
      * `instructions` 是自然语言的表演指令（情境/意图/情绪强度/节奏重音/身心状态）；
      * 文本里可以直接插**中文音频标签**（`[叹气]` `[轻笑]` `[咯咯笑]` `[耳语]`
        `[哼歌]` `[冷笑]` …共 34 个），这是它比 mimo 强的地方。注意 mimo 里
        「停顿」是反向响应会狂插静音，而 breeze 的 `[停顿]` 是官方正常标签；
      * 输出格式必须走 **query 参数** `?output_format=wav`，放进 body 会 422
        （extra_forbidden），Accept 头也无效（仍回 mp3）。
      * 单请求 1000 字符上限；中文超 500 字服务端会自动切段，段间补 0.25 秒静音。

    实测（同一句话，F0 标准差代表语调起伏）：
        mimo 克隆 57.7 / breeze 无标签 87.5 / breeze 带 `[叹气]` **109.8**。
        调 guidance_scale=3 反而降到 85.8，所以**标签比强度参数有效**。
    """
    cfg = load_config()
    b = cfg.get("breeze") or {}
    key = (b.get("api_key") or "").strip()
    if not key:
        raise TTSError("tts_config.json 里没有 breeze.api_key")
    base = str(b.get("base_url") or "https://api.breezeblue.ai").rstrip("/")
    model = model or b.get("model") or "breeze-tts-2"
    voice_id = voice or b.get("voice_id")
    if not voice_id:
        raise TTSError("breeze 需要 voice_id（先克隆或从 /v1/voices 里挑一个）")

    body: dict = {"text": text, "model_id": model,
                  "language_code": b.get("language_code") or "zh"}
    if instructions and instructions.strip():
        body["instructions"] = instructions.strip()
    # voice_settings 是可调的旋钮，比在 instructions 里写「语速偏快」精确得多：
    #   guidance_scale —— 表演强度；speed —— 语速倍率（1=原速）；
    #   volume —— 音量；use_speaker_boost —— 音色保真增强。
    # 2026-10-27：之前只传了 guidance_scale，语速全靠 style 文字暗示，
    # 实测听感"人机感重"，所以把 speed / volume / boost 一并暴露成配置项。
    vs: dict = {}
    gs = guidance if guidance is not None else b.get("guidance_scale")
    if gs is not None:
        vs["guidance_scale"] = float(gs)
    sp = speed if speed is not None else b.get("speed")
    if sp is not None:
        vs["speed"] = float(sp)
    vol = b.get("volume")
    if vol is not None:
        vs["volume"] = float(vol)
    if b.get("use_speaker_boost"):
        vs["use_speaker_boost"] = True
    if vs:
        body["voice_settings"] = vs

    fmt = b.get("output_format") or "wav"
    url = "%s/v1/text-to-speech/%s?output_format=%s" % (base, voice_id, fmt)
    # ★ 这里必须用 requests，不能用 urlopen：
    #   urllib 默认 UA 是 `Python-urllib/3.x`，会被 Cloudflare 以 **error code 1010**
    #   直接拦掉（403，站点按客户端特征封禁）。实测 requests 调同一端点一直正常。
    try:
        import requests
    except ImportError as exc:  # noqa: BLE001
        raise TTSError("breeze 需要 requests 库") from exc
    try:
        r = requests.post(url, json=body, timeout=min(timeout, 180),
                          headers={"Authorization": "Bearer " + key,
                                   "Content-Type": "application/json"})
    except Exception as exc:  # noqa: BLE001
        raise TTSError("breeze 请求失败: %r" % (exc,)) from exc
    if r.status_code != 200:
        raise TTSError("breeze HTTP %s: %s" % (r.status_code, (r.text or "")[:240]))
    data = r.content
    if not data:
        raise TTSError("breeze 返回空音频")
    return data


# ---------------------------------------------------------------- 句内变速
# ★ 2026-10-28 实测结论：Breeze **不听** instructions 里的快慢描述。
#   同一句分三小句，说「第一句又快又急」总时长从 5.28s 涨到 8.16s——
#   越描述越拖，和 MiMo 那条「提停顿就疯狂插静音」是同一个病。
#   真正起作用的只有 voice_settings.speed（1.3 比 1.0 短 44%）。
#   所以句内快慢只能靠「分句 + 各自变速 + 拼接」。
_SENT_SPLIT = re.compile(r"(?<=[。！？…!?])")


def split_sentences(text: str) -> list[str]:
    """按句末标点切句，丢掉只有标点的碎片。

    ★ `……` 会被逐字符切开，蹦出一个 content 只有「…」的"句子"，
      送进 TTS 会生成一段纯静音，白花一次调用。
    """
    raw = [p.strip() for p in _SENT_SPLIT.split(str(text or ""))]
    parts = [p for p in raw if p and re.search(r"[0-9A-Za-z\u4e00-\u9fff]", p)]
    # 被切开的纯标点碎片并回前一句，别让省略号单独成句
    merged: list[str] = []
    for p in raw:
        if not p:
            continue
        if not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", p):
            if merged:
                merged[-1] += p
            continue
        merged.append(p)
    return merged or ([str(text)] if str(text or "").strip() else [])


def sentence_speed(sent: str, idx: int, total: int) -> float:
    """给每一句定一个语速。差异要够大才压得住单次生成的噪声。

    ★ 单次合成本身有 ±20% 的时长抖动（实测同一句话 1.76~2.00s），
      所以快慢档之间至少拉开 25%，否则人耳听不出是「变速」而不是「随机」。
    """
    core = sent.strip("。！？…，,、~～ \t")
    n = len(core)
    tail = sent.rstrip()[-1:] if sent.rstrip() else ""
    if tail in "！!？?" and n <= 8:
        return 1.20          # 短的感叹/追问：抢着说
    if "……" in sent or tail == "…":
        return 0.88          # 拖音、欲言又止
    if n >= 16:
        return 0.93          # 长句放慢，否则一口气念不完
    if n <= 6:
        return 1.12          # 短促的一句
    return 1.0


def _concat_wav(wavs: list[bytes]) -> bytes:
    """把多段 wav 按顺序拼成一段（参数必须一致，Breeze 同端点返回是一致的）。"""
    if not wavs:
        raise TTSError("没有可拼接的音频")
    if len(wavs) == 1:
        return wavs[0]
    out = _io.BytesIO()
    writer = None
    for w in wavs:
        with wave.open(_io.BytesIO(w), "rb") as r:
            if writer is None:
                writer = wave.open(out, "wb")
                writer.setnchannels(r.getnchannels())
                writer.setsampwidth(r.getsampwidth())
                writer.setframerate(r.getframerate())
            writer.writeframes(r.readframes(r.getnframes()))
    writer.close()
    return out.getvalue()


def _breeze_synthesize_varied(text: str, instructions: str | None = None,
                              voice: str | None = None, model: str | None = None,
                              timeout: float = 90) -> bytes:
    """分句合成，每句一个语速，拼成一条。句子多时才有意义。"""
    sents = split_sentences(text)
    if len(sents) <= 1:
        return _breeze_synthesize(text, instructions, voice, model, timeout)
    wavs = []
    for i, sent in enumerate(sents):
        sp = sentence_speed(sent, i, len(sents))
        try:
            wavs.append(_breeze_synthesize(sent, instructions, voice, model,
                                           timeout, speed=sp))
        except TTSError as exc:
            # 单句失败就别整条废掉：退回整段一次生成（至少能出声）
            LOG.warning("分句合成第 %d 句失败（%r），退回整段合成", i + 1, exc)
            return _breeze_synthesize(text, instructions, voice, model, timeout)
    return _concat_wav(wavs)


def synthesize_wav(text: str, voice: str | None = None, model: str | None = None,
                   style: str | None = None, timeout: int = 90) -> bytes:
    """调用 MiMo TTS 拿 wav 字节。

    style 是**风格控制指令**（自然语言，放在 user 消息里），这是让语音有感情的关键。
    文档称之为「导演模式」，可以从【角色】【场景】【指导】三个维度刻画，例如：

        style = (
            "角色：19岁杭州女孩，美院大二，嘴硬心软，说话带点俏皮和慵懒。\\n"
            "场景：跟喜欢的男生微信聊天，他半天没回，她装作不在意。\\n"
            "指导：语速偏快，尾音上扬；前半句故意冷淡，后半句露出心虚和在乎，"
            "句尾轻轻带一点笑意。"
        )

    此外文本本身还能内嵌标签（放在 text 里，不是 style 里）：
      - 开头整体风格：`(高冷 俏皮)` / `(委屈)` / `(温柔)` / `(唱歌)`
      - 句中细粒度：`[轻笑]` `[叹气]` `[撒娇]` `[心虚]` `[语速加快]` `[压低声音]`
    """
    cfg = load_config()
    provider = str(cfg.get("provider") or "mimo").lower()
    if provider == "breeze":
        # 第一优先级。style 在 breeze 侧叫 instructions，语义一致，直接透传。
        # ★ 走分句变速版本：instructions 里的快慢描述实测无效（越描述越拖），
        #   句内快慢只能靠分句各自设置 voice_settings.speed 再拼接。
        return _breeze_synthesize_varied(text, style, voice, model, timeout)
    m = cfg.get("mimo") or {}
    key = (m.get("api_key") or "").strip()
    if not key:
        raise TTSError("tts_config.json 里没有 mimo.api_key")
    url = m.get("base_url") or "https://api.xiaomimimo.com/v1/chat/completions"
    model = model or m.get("model") or "mimo-v2.5-tts"
    voice = voice or m.get("voice") or "冰糖"

    # voiceclone 的 voice 必须是样本的 DataURL：允许显式传 DataURL、传样本文件路径，
    # 或干脆不传（用 tts_config.json 里的 mimo.clone_sample）。
    if "voiceclone" in model:
        if voice and voice.startswith("data:"):
            pass
        elif voice and Path(voice).exists():
            voice = clone_sample_durl(voice)
        else:
            sample = m.get("clone_sample")
            if not sample:
                raise TTSError("voiceclone 需要配置 mimo.clone_sample（样本音频路径）")
            voice = clone_sample_durl(sample)

    # 该端点用 chat 格式做 TTS：
    #   user      -> 风格/情绪/语气指令（内容不会被念出来，可为空）
    #   assistant -> 真正要合成的文本
    messages: list[dict] = []
    if style and style.strip():
        messages.append({"role": "user", "content": style.strip()})
    messages.append({"role": "assistant", "content": text})

    # voicedesign 模型不接受 audio.voice（音色由 user 消息的描述决定）
    audio_cfg: dict = {"format": "wav"}
    if "voicedesign" not in model:
        audio_cfg["voice"] = voice

    payload = {
        "model": model,
        "messages": messages,
        "audio": audio_cfg,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=body, method="POST", headers={
        "api-key": key,
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
    })
    # 429 限流是常态（批量合成时尤其容易踩到），退避重试
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            break
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            last_err = TTSError("MiMo TTS HTTP %s: %s" % (exc.code, detail))
            if exc.code == 429 and attempt < 2:
                wait = 6 * (attempt + 1)
                LOG.warning("TTS 被限流，%d 秒后重试（第 %d 次）", wait, attempt + 1)
                time.sleep(wait)
                continue
            raise last_err from exc
        except URLError as exc:
            raise TTSError("MiMo TTS 网络错误: %s" % exc) from exc
    else:
        raise last_err or TTSError("MiMo TTS 重试耗尽")

    audio = ((data.get("choices") or [{}])[0].get("message") or {}).get("audio") or {}
    b64 = audio.get("data")
    if not b64:
        raise TTSError("响应里没有 audio.data：%s" % json.dumps(data, ensure_ascii=False)[:200])
    return base64.b64decode(b64)


def to_wechat_pcm(wav_bytes: bytes, out_path: Path) -> Path:
    """wav -> 16kHz 单声道 s16le（微信 SILK 编码器要求的格式）。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tf.write(wav_bytes)
        tmp_wav = Path(tf.name)
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp_wav),
             "-ac", str(WECHAT_CHANNELS), "-ar", str(WECHAT_SAMPLE_RATE),
             "-f", "s16le", str(out_path)],
            capture_output=True,
        )
        if proc.returncode != 0:
            raise TTSError("ffmpeg 失败: %s" % proc.stderr.decode("utf-8", "replace")[:200])
    finally:
        tmp_wav.unlink(missing_ok=True)
    return out_path


def synthesize_pcm(text: str, voice: str | None = None, model: str | None = None,
                   style: str | None = None, out_dir: Path | None = None) -> Path:
    """文本 -> 16k 单声道 PCM 文件路径（带内容缓存，同样的话+风格不重复调 API）。

    style 见 synthesize_wav：不传就是默认平铺语气，**通常听起来没有感情**。
    """
    cfg = load_config()
    provider = str(cfg.get("provider") or "mimo").lower()
    if provider == "breeze":
        # ★ breeze 的 voice 指 voice_id，绝不能塞 mimo 的音色名（"冰糖" 会被当成
        #   voice_id 传过去直接 404）。留空让 _breeze_synthesize 读配置里的克隆音色。
        voice = voice or None
    else:
        voice = voice or (cfg.get("mimo") or {}).get("voice") or "冰糖"
    out_dir = Path(out_dir or (cfg.get("output") or {}).get("pcm_dir") or CACHE_DIR)

    digest = hashlib.sha1(
        ("%s|%s|%s|%s" % (text, voice, model or "", style or "")).encode("utf-8")
    ).hexdigest()[:16]
    out_path = out_dir / ("tts_%s.pcm" % digest)
    if out_path.exists() and out_path.stat().st_size > 0:
        LOG.debug("TTS 命中缓存: %s", out_path.name)
        return out_path

    t0 = time.time()
    wav = synthesize_wav(text, voice=voice, model=model, style=style)
    # 保留原始 wav：voiceclone 克隆音色时要用它当样本
    # （PCM 是 16k 二次降采样过的，质量不够做克隆样本）
    try:
        out_path.with_suffix(".wav").write_bytes(wav)
    except OSError as exc:  # noqa: BLE001
        LOG.warning("原始 wav 保存失败（不影响本次发送）: %s", exc)
    pcm = to_wechat_pcm(wav, out_path)
    samples = pcm.stat().st_size // 2
    LOG.info("TTS 完成 %.1fs voice=%s style=%s %.2fs (%d samples) -> %s",
             time.time() - t0, voice, "有" if style else "无",
             samples / WECHAT_SAMPLE_RATE, samples, pcm.name)
    return pcm


def voices() -> list[str]:
    """当前 provider 下可用的音色标识。"""
    cfg = load_config()
    if str(cfg.get("provider") or "mimo").lower() == "breeze":
        b = cfg.get("breeze") or {}
        vid = b.get("voice_id")
        return [str(vid)] if vid else []
    return ["冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean", "mimo_default"]


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    text = sys.argv[1] if len(sys.argv) > 1 else "喂，能听到吗？我在电脑上试一下语音。"
    v = sys.argv[2] if len(sys.argv) > 2 else None
    print(synthesize_pcm(text, voice=v))
