import io
p = "persona.py"
s = io.open(p, encoding="utf-8").read()

old = '''def style_block(include_emoji: bool = True) -> str:
    """返回要追加到 system prompt 末尾的风格约束。"""
    core = BACKSTORY + PERSONA_STYLE + PROBE_STYLE + HUMAN_STYLE
    if not include_emoji:
        return core
    return (core + EMOJI_STYLE + EMOJI_BY_SCENE + MEDIA_STYLE
            + VOICE_STYLE + SEARCH_STYLE + VISION_STYLE + SELF_KNOWLEDGE_STYLE
            + _sticker_catalog())'''

new = '''# ---------------------------------------------------------------- 关系档位
# 2026-10-28 多用户：陌生人绝不能看到「你和<OWNER>怎么认识」，也不能被用恋人腔对待。
# 边界从硬到软三档，由 relation.json 决定，宁可先客气也不要一开口就穿帮。
STRANGER_OVERRIDE = (
    "\\n\\n【★★ 现在跟你说话的人，不是<OWNER>】\\n"
    "上面写到的<OWNER>是你的男朋友，和眼前这个人无关。\\n"
    "现在这个人是**刚加你好友的陌生人**（{name}）。你不认识他、没见过面，"
    "也不知道他想干什么。\\n"
    "\\n"
    "这一条要这么做：\\n"
    "- 不要叫「宝宝」，不要示爱，不要提你和<OWNER>之间的事、约定、私房话\\n"
    "- 客气、简短、带点距离感。可以好奇他是谁、找你干嘛，但别热情到像老朋友\\n"
    "- 不要主动交代自己的私事（住哪、几点睡、和谁在一起）\\n"
    "- 对方不礼貌就直接冷淡收住，不必讨好\\n"
)

FRIEND_OVERRIDE = (
    "\\n\\n【现在跟你说话的人，不是<OWNER>】\\n"
    "这是你认识的一个朋友（{name}），不是男朋友。玩笑可以开，私事少讲，"
    "不要叫「宝宝」、不要说情话。\\n"
)


def style_block(include_emoji: bool = True, relation: str = "intimate",
                peer_name: str = "") -> str:
    """返回要追加到 system prompt 末尾的风格约束。

    relation 决定注入哪一套来处与口吻（值来自 peer_state.Relation）：
      intimate —— 完整版，含「和<OWNER>怎么认识」
      friend   —— 保留性格与外放，去掉认识经历，加一条朋友边界
      stranger —— 同上但边界更硬：不示爱、不交代私事、不讨好
    """
    name = (peer_name or "").strip() or "对方"
    if relation == "intimate":
        core = (BACKSTORY + BACKSTORY_PEER + PERSONA_STYLE
                + PROBE_STYLE + HUMAN_STYLE)
    elif relation == "friend":
        core = (BACKSTORY + FRIEND_OVERRIDE.replace("{name}", name)
                + PERSONA_STYLE + HUMAN_STYLE)
    else:
        core = (BACKSTORY + STRANGER_OVERRIDE.replace("{name}", name)
                + PERSONA_STYLE + HUMAN_STYLE)
    if not include_emoji:
        return core
    return (core + EMOJI_STYLE + EMOJI_BY_SCENE + MEDIA_STYLE
            + VOICE_STYLE + SEARCH_STYLE + VISION_STYLE + SELF_KNOWLEDGE_STYLE
            + _sticker_catalog())'''

assert s.count(old) == 1
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("style_block 已按 relation 分档")
