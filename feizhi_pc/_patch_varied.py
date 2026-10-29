import io
p = "tts.py"
s = io.open(p, encoding="utf-8").read()

old = "import base64\nimport hashlib\nimport json\nimport logging\nimport subprocess\nimport tempfile\nimport time"
assert s.count(old) == 1
s = s.replace(old, "import base64\nimport hashlib\nimport io as _io\nimport json\nimport logging\nimport re\nimport subprocess\nimport tempfile\nimport time\nimport wave", 1)

# 在 synthesize_wav 之前插入分句变速
anchor = "def synthesize_wav("
assert s.count(anchor) == 1
block = '''# ---------------------------------------------------------------- 句内变速
# ★ 2026-10-28 实测结论：Breeze **不听** instructions 里的快慢描述。
#   同一句分三小句，说「第一句又快又急」总时长从 5.28s 涨到 8.16s——
#   越描述越拖，和 MiMo 那条「提停顿就疯狂插静音」是同一个病。
#   真正起作用的只有 voice_settings.speed（1.3 比 1.0 短 44%）。
#   所以句内快慢只能靠「分句 + 各自变速 + 拼接」。
_SENT_SPLIT = re.compile(r"(?<=[。！？…!?])")


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(str(text or "")) if p and p.strip()]
    return parts or ([str(text)] if str(text or "").strip() else [])


def sentence_speed(sent: str, idx: int, total: int) -> float:
    """给每一句定一个语速。差异要够大才压得住单次生成的噪声。

    ★ 单次合成本身有 ±20% 的时长抖动（实测同一句话 1.76~2.00s），
      所以快慢档之间至少拉开 25%，否则人耳听不出是「变速」而不是「随机」。
    """
    core = sent.strip("。！？…，,、~～ \\t")
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


''' + anchor
s = s.replace(anchor, block, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("tts.py 已加分句变速")
