"""微信表情代码表。

这些 `[名称]` 写在文本里，**微信客户端会渲染成表情图标**，
所以不需要扩展 hook 桥就能发表情（发送的仍是 type=1 文本消息）。

来源：wechat-emoji-renderer 的 108 个标准表情。
"""
import difflib
import random
import re as _re

# 全部 108 个标准表情代码
ALL = [
    # 第一排
    "[微笑]", "[撇嘴]", "[色]", "[发呆]", "[得意]", "[流泪]", "[害羞]", "[闭嘴]", "[睡]", "[大哭]",
    # 第二排
    "[尴尬]", "[发怒]", "[调皮]", "[呲牙]", "[惊讶]", "[难过]", "[冷汗]", "[抓狂]", "[吐]", "[偷笑]",
    # 第三排
    "[愉快]", "[白眼]", "[傲慢]", "[困]", "[惊恐]", "[憨笑]", "[悠闲]", "[咒骂]", "[疑问]", "[嘘]",
    # 第四排
    "[晕]", "[衰]", "[骷髅]", "[敲打]", "[再见]", "[擦汗]", "[抠鼻]", "[鼓掌]", "[坏笑]", "[鄙视]",
    # 第五排
    "[委屈]", "[阴险]", "[亲亲]", "[可怜]", "[笑脸]", "[生病]", "[脸红]", "[恐惧]", "[失望]", "[无语]",
    # 第六排
    "[嘿哈]", "[捂脸]", "[奸笑]", "[机智]", "[皱眉]", "[耶]", "[吃瓜]", "[加油]", "[汗]", "[天啊]",
    # 第七排
    "[Emm]", "[旺柴]", "[好的]", "[打脸]", "[哇]", "[666]", "[叹气]", "[苦涩]", "[裂开]", "[嘴唇]",
    # 第八排
    "[爱心]", "[心碎]", "[拥抱]", "[强]", "[弱]", "[握手]", "[胜利]", "[抱拳]", "[勾引]", "[拳头]",
    # 第九排
    "[OK]", "[合十]", "[啤酒]", "[咖啡]", "[蛋糕]", "[玫瑰]", "[凋谢]", "[菜刀]", "[炸弹]", "[便便]",
    # 第十排
    "[月亮]", "[太阳]", "[庆祝]", "[礼物]", "[红包]", "[福]", "[烟花]", "[爆竹]", "[猪头]", "[跳跳]",
    # 第十一排
    "[发抖]", "[转圈]",
]

# 按情绪/场景分组，便于在 prompt 里给出「什么场合用什么」的引导
BY_MOOD = {
    "开心": ["[微笑]", "[愉快]", "[呲牙]", "[憨笑]", "[偷笑]", "[坏笑]", "[耶]", "[庆祝]", "[转圈]", "[跳跳]"],
    "惊喜": ["[惊讶]", "[哇]", "[天啊]", "[惊恐]", "[666]", "[强]", "[鼓掌]", "[胜利]"],
    "无奈": ["[捂脸]", "[无语]", "[汗]", "[擦汗]", "[叹气]", "[Emm]", "[裂开]", "[苦涩]"],
    "不满": ["[撇嘴]", "[白眼]", "[傲慢]", "[鄙视]", "[发怒]", "[敲打]", "[菜刀]", "[炸弹]"],
    "难过": ["[流泪]", "[大哭]", "[难过]", "[失望]", "[心碎]", "[凋谢]", "[衰]"],
    "撒娇": ["[害羞]", "[亲亲]", "[可怜]", "[委屈]", "[爱心]", "[拥抱]", "[勾引]"],
    "困累": ["[困]", "[睡]", "[生病]", "[骷髅]", "[衰]"],
    "敷衍": ["[微笑]", "[好的]", "[OK]", "[合十]", "[抱拳]", "[握手]"],
    "物件": ["[咖啡]", "[啤酒]", "[蛋糕]", "[玫瑰]", "[礼物]", "[红包]", "[福]", "[月亮]", "[太阳]"],
}


def codes_text() -> str:
    return " ".join(ALL)


def prompt_hint() -> str:
    """给 LLM 的表情使用指导（拼进 system prompt）。"""
    lines = ["可用微信表情代码（写在句子里，微信会自动渲染成表情）：", codes_text(), ""]
    lines.append("常见场合：")
    for mood, codes in BY_MOOD.items():
        lines.append("  %s：%s" % (mood, " ".join(codes)))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 本地图片表情库
#
# 为什么单独一组：微信「收藏表情」的纯 hook 发送尚未打通（TASK_LOG 第二十四、
# 二十五节），但**图片消息通道已实测可用**——任意本地图片都能程序化发出。
# 因此把想发的表情存成图片放进 IMAGE_DIR，回复里写 [img:名字] 即可真正发图，
# 而不只是发 [微笑] 这类文本表情代码。
# 注意：GIF 会被微信静态化（只显示首帧），动图效果无法保留。
# ---------------------------------------------------------------------------
from pathlib import Path as _Path

IMAGE_DIR = _Path(r"<PROJECT_ROOT>\feizhi_pc\images")
# 网络采集的真·表情包（m_<关键词><序号> 命名），见 tmp\fetch_memes.py
MEME_DIR = IMAGE_DIR / "memes"
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def ensure_image_dir() -> _Path:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGE_DIR


_NOISE_PREFIX = ("gen_", "_", "face", "fb_", "fc_")
_NOISE_DIRS = ("faces",)


def list_images(include_noise: bool = False) -> list[_Path]:
    """列出图片库里的图片（递归包含子目录）。

    ★ 2026-10-15 两次修正：
      1. 原来只 iterdir() 根目录，放进 images/emoji/ 后 LLM 完全看不到 —— 改成 rglob。
      2. 改完又发现 faces/ 的换脸候选和根目录一堆 gen_<hash> 无意义文件名
         全被塞进 prompt，40 多个名字把真正可用的 8 个表情图淹没了。
         默认**过滤掉噪音**，只留下有语义命名的图（emoji/ 下的 + 根目录里名字可读的）。
    """
    if not IMAGE_DIR.is_dir():
        return []
    out: list[_Path] = []
    for p in IMAGE_DIR.rglob("*"):
        if not (p.is_file() and p.suffix.lower() in _IMAGE_EXTS):
            continue
        if include_noise:
            out.append(p)
            continue
        rel = p.relative_to(IMAGE_DIR)
        if rel.parts[0] in _NOISE_DIRS:          # images/faces/**
            continue
        if rel.parts[0] == "emoji":              # images/emoji/** 全收
            out.append(p)
            continue
        if p.stem.startswith(_NOISE_PREFIX):     # gen_xxx / _persona_ref / fb_01 ...
            continue
        out.append(p)
    return sorted(out)


def find_image(name: str) -> _Path | None:
    """按文件名（不含扩展名）精确匹配，其次按包含关系模糊匹配。

    另外支持「表情包关键词」：memes/ 里的图按 m_<关键词><序号> 命名，
    写 [img:委屈] 会从该关键词下**随机挑一张**。
    这样既能给 LLM 一个简短的词表（不淹没 prompt），又有多张可换。
    """
    key = (name or "").strip().lower()
    if not key:
        return None
    # 1) emoji/ 与根目录的精确匹配优先（这些是一图一词的）
    imgs = [p for p in list_images() if p.parent != MEME_DIR]
    for p in imgs:
        if p.stem.lower() == key:
            return p
    # 2) memes/ 关键词分组 -> 随机一张
    #    对外暴露成「<关键词>表情包」，因为 emoji/ 里有同名图（委屈/无语/生气…），
    #    不加后缀的话 [img:委屈] 永远优先命中她自己的照片，网络表情包就发不出来了。
    groups = meme_groups()
    for kw, paths in groups.items():
        if not paths:
            continue
        kl = kw.lower()
        if key in (kl, kl + "表情包", "m_" + kl, "meme_" + kl):
            return random.choice(paths)
    # 3) 模糊匹配兜底
    for p in imgs:
        if key in p.stem.lower():
            return p
    for kw, paths in groups.items():
        if key in kw.lower() and paths:
            return random.choice(paths)
    return None


def meme_groups() -> dict[str, list[_Path]]:
    """memes/ 里的表情包按关键词分组：m_委屈1.jpg -> {"委屈": [path, ...]}"""
    out: dict[str, list[_Path]] = {}
    if not MEME_DIR.is_dir():
        return out
    for p in sorted(MEME_DIR.iterdir()):
        if not p.is_file() or p.suffix.lower() not in _IMAGE_EXTS:
            continue
        m = _re.match(r"^m_(.+?)(\d+)$", p.stem)
        kw = m.group(1) if m else p.stem
        out.setdefault(kw, []).append(p)
    return out


def image_prompt_hint() -> str:
    """给 LLM 的图片清单（没有图片时返回空串，不污染 prompt）。

    ★ 表情包只列**关键词**不列文件名：memes/ 里上百张图，逐个列会把
      prompt 淹掉（实测过一次，40 多个无语义名字挤在一起）。
      列关键词 + 数量，她用 [img:关键词] 就能随机发一张。
    """
    named = [p for p in list_images() if p.parent != MEME_DIR]
    groups = meme_groups()
    if not named and not groups:
        return ""
    lines = ["可用图片（在回复里写 [img:名字] 就会真的发出去）："]
    if named:
        lines.append("  你自己的表情：" + "  ".join(p.stem for p in named[:30]))
    if groups:
        parts = ["%s表情包(%d张)" % (kw, len(v)) for kw, v in sorted(groups.items())]
        lines.append("  表情包（写这个词就会随机发一张）：" + "  ".join(parts))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 微信【原生表情】—— 真表情消息，不是图片
#
# 走 DLL 的载体替换链路（TASK_LOG §26~§31）：type=8 收藏表情 / type=12 表情包，
# **已由对端实测确认送达**（见 bridge.send_sticker）。
# ↑ 2026-10-15 更正：本文件早先写着「收藏表情的纯 hook 发送尚未打通」，
#   那是 §24/§25 时期的旧结论，§26 之后已经打通。
#
# 每个模板对应账号里真实存在的一个收藏表情。md5 取自 DLL 内置模板表
# （wx_sticker_templates.h）。表情文件在
#   D:\xwechat_files\<wxid>\business\emoticon\Persist\<前2位>\<md5>
# 但是**加密的**（熵 7.98 bits/byte，只有约 16 字节明文头），无法离线解码，
# 所以每个模板「长什么样」只能靠肉眼看微信界面来确定，再填进 name。
# ---------------------------------------------------------------------------
FAV_TEMPLATES = [
    {"idx": 0, "md5": "0fbdd73cc59f210845f4d2457b0167b8", "name": "微笑",
     "note": "绯栀自拍：正面看镜头微笑"},
    {"idx": 1, "md5": "53dcede756bc62e5e7cfb3eca4c3b5c5", "name": "嘟嘴",
     "note": "绯栀自拍：嘟嘴卖萌"},
    {"idx": 2, "md5": "7ed206382321db118c4951f1e448166a", "name": "惊讶",
     "note": "绯栀自拍：睁大眼睛微张嘴"},
    {"idx": 3, "md5": "b90ff3bbdb9eb50b8324bb7d6631a3ef", "name": "托脸",
     "note": "绯栀自拍：双手托脸"},
    {"idx": 4, "md5": "cbab1418a65ab56a82b228ea2a27c621", "name": "托腮",
     "note": "绯栀自拍：单手托下巴，眼神平静"},
    {"idx": 5, "md5": "ccfabb49a1904b17159ba9f6bb9b3782", "name": "挥手",
     "note": "绯栀自拍：举手打招呼"},
    {"idx": 6, "md5": "d727ccdf2475c436206cbc8ec3fa30b9", "name": "不高兴",
     "note": "绯栀自拍：抿嘴、有点委屈"},
]

# 表情包（表情商店添加），4 枚同属一个专辑，专辑名「空降」。
# 聊天记录里看到的是狗头梗图系列。
PACK_TEMPLATES = [
    {"idx": 0, "md5": "1b09ef505de4501c4f77569207864e4b", "album": "空降", "name": "忙",
     "note": "狗头戴眼镜敲笔记本电脑"},
    {"idx": 1, "md5": "a6d3a7abb8d7084bff4540c7e5676184", "album": "空降", "name": "稍等",
     "note": "狗头举「稍等」牌子，电脑冒烟"},
    {"idx": 2, "md5": "ebd98e27c7fc8b50a19496d188d359e4", "album": "空降", "name": "大哭",
     "note": "狗头抱头哭"},
    {"idx": 3, "md5": "ca9d0631d936ad6fd5893f663d98650d", "album": "空降", "name": "白球",
     "note": "一个白色圆球（待确认）"},
]

# ⚠️ 上面 name 与图案的对应关系是**看着聊天记录推断**的：表情文件加密（熵 7.98）
#    没法离线解码，只能从微信渲染出来的界面上看；而聊天记录是累积的，
#    单条对应关系不能百分百钉死。如需精确复核，跑：
#      python <PROJECT_ROOT>\tmp\map_stickers.py      （逐条发送并抓图）
#    确认后改这里的 name 即可，代码别处不用动。


def _label(kind: str, tpl: dict) -> str:
    return tpl["name"] or ("%s%d" % ("fav" if kind == "fav" else "pack", tpl["idx"]))


def find_sticker(name: str) -> tuple[str, int] | None:
    """把名字解析成 (kind, index)。支持语义名、fav0..6 / pack0..3、纯数字。

    纯数字默认当收藏表情（更常用）。

    ★ 精确匹配失败时会做模糊匹配：模型经常给出清单外的近义词
      （实测 2026-10-17 它想发「撇嘴」，而贴纸清单里只有「嘟嘴」）。
      以前这种情况直接返回 None，表情就静默丢了。
    """
    key = (name or "").strip()
    if not key:
        return None
    low = key.lower()
    for kind, table in (("fav", FAV_TEMPLATES), ("pack", PACK_TEMPLATES)):
        for tpl in table:
            if tpl["name"] and tpl["name"] == key:
                return kind, tpl["idx"]
            if low in ("%s%d" % ("fav" if kind == "fav" else "pack", tpl["idx"]),
                       "%s:%d" % (kind, tpl["idx"])):
                return kind, tpl["idx"]
    if low.isdigit():
        idx = int(low)
        if 0 <= idx < len(FAV_TEMPLATES):
            return "fav", idx
    # 模糊：包含关系优先，其次相似度
    best: tuple[float, str, int] | None = None
    for kind, table in (("fav", FAV_TEMPLATES), ("pack", PACK_TEMPLATES)):
        for tpl in table:
            n = (tpl.get("name") or "").lower()
            if not n:
                continue
            if n in low or low in n:
                return kind, tpl["idx"]
            score = difflib.SequenceMatcher(None, n, low).ratio()
            if best is None or score > best[0]:
                best = (score, kind, tpl["idx"])
    if best and best[0] >= 0.5:
        return best[1], best[2]
    return None


def is_text_emoji(name: str) -> bool:
    """是不是「[撇嘴]」这类微信标准文本表情（发出去是文本，客户端渲染成表情）。"""
    key = (name or "").strip().strip("[]")
    if not key:
        return False
    return ("[" + key + "]") in ALL


def sticker_prompt_hint() -> str:
    """给 LLM 的原生表情清单。一个都没命名时返回空串，避免让它盲选。"""
    named = [(k, t) for k, tbl in (("fav", FAV_TEMPLATES), ("pack", PACK_TEMPLATES))
             for t in tbl if t["name"]]
    if not names_or_empty(named):
        return ""
    lines = ["可用微信表情（在回复里写 [sticker:名字]，会作为真表情发出）："]
    for kind, tpl in named:
        lines.append("  %s%s" % (tpl["name"], "（表情包）" if kind == "pack" else ""))
    return "\n".join(lines)


def names_or_empty(items) -> bool:
    return bool(items)


# ---------------------------------------------------------------------------
# 情境选表情 —— 给「代码层自动补表情」用
#
# 为什么不全靠 LLM：实测它极少主动写 [sticker:]，prompt 里写得再清楚也基本不用。
# 所以改成代码按概率补一条，并在这里按对话内容挑合适的表情。
# ---------------------------------------------------------------------------
_KEYWORD_RULES: list[tuple[tuple[str, ...], str]] = [
    (("赢了", "厉害", "牛", "得意", "显摆", "帅", "我强"), "不高兴"),
    (("忙", "等我", "等一下", "稍等", "马上", "在开会", "有事"), "稍等"),
    (("累", "困", "烦", "难受", "不想干", "烦死", "崩溃", "加班"), "大哭"),
    (("哈哈", "好笑", "笑死", "有趣", "逗"), "微笑"),
    (("可爱", "好看", "漂亮", "喜欢你", "想你", "宝宝"), "嘟嘴"),
    (("真的假的", "不会吧", "什么", "啊？", "竟然", "居然"), "惊讶"),
    (("在干嘛", "干嘛呢", "忙什么", "怎么不回"), "托腮"),
    (("走了", "再见", "睡了", "晚安"), "挥手"),
    (("讨厌", "烦人", "气", "过分", "不理你"), "不高兴"),
]

# 兜底（心情好/中性时用）
_FALLBACK = ["微笑", "嘟嘴", "托脸", "托腮", "挥手"]


def pick_for(text: str, exclude: set[str] | None = None) -> tuple[str, int] | None:
    """按对话内容挑一个真表情，返回 (kind, index)。

    命中关键词就用对应表情；没命中就从兜底池里随机挑（排除最近发过的）。
    """
    t = (text or "").strip()
    skip = exclude or set()
    for keys, name in _KEYWORD_RULES:
        if name in skip:
            continue
        if any(k in t for k in keys):
            hit = resolve_name(name, skip)
            if hit:
                return hit
    pool = [n for n in _FALLBACK if n not in skip]
    random.shuffle(pool)
    for name in pool:
        hit = resolve_name(name, skip)
        if hit:
            return hit
    return None


def resolve_name(name: str, skip: set[str] | None = None) -> tuple[str, int] | None:
    """按名字找 (kind, index)；跳过 skip 里的名字。"""
    skip = skip or set()
    for kind, table in (("fav", FAV_TEMPLATES), ("pack", PACK_TEMPLATES)):
        for tpl in table:
            if tpl["name"] == name and tpl["name"] not in skip:
                return kind, tpl["idx"]
    return None

