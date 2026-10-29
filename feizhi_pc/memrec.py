# -*- coding: utf-8 -*-
"""记忆记录的可追溯、可校验结构（CRUD 前置）。

时间契约 v3 —— 按 YG 复现的五个反例 + 时区问题收紧：

  1. **只用实际引用的来源**：说话者与时间都只看 `source_msg_ids` 指向的消息，
     不用整批（否则"只引用用户消息、批次里还有助手消息"会把 speaker 判成空）。
  2. **相对词按完整表达识别**：`大后天` 不会被当成 `后天`（子串匹配会错算两天）。
  3. **日历有效性 + 显式北京时间**：`13月40日` 不通过；`_parse_ms` 用 UTC+8，
     不依赖主机本地时区。已知年份时 `event_time` 存完整 `YYYY-MM-DD`，
     显示时才简写成「10月22日」。
  4. **正文时间统一规范化**：结构字段有值时，正文里的相对词/日期**全部**替换成
     规范写法（否则「字段对了、正文还写着明天」，长期读取照样错）。
     无法可靠规范化时标 `needs_review=True`，**不自动覆盖**。
  5. 支持 `2026-10-26` 这类 ISO 写法；歧义表达（周末/过几天/下周…）一律未知。

支持换算的只有：前天 / 昨天 / 今天 / 明天 / 后天 / 大后天。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))

TB_EXPLICIT = "explicit_text"
TB_MESSAGE = "message_time"
TB_UNKNOWN = "unknown"
TB_MANUAL = "manual"          # 人工修正：程序不推翻，但永久带 needs_review

# 可换算的相对时间。时段词（早/晚）落到**当天日期**：昨晚=昨天、今早=今天、明晚=明天。
# 这些换算是确定的，不含猜测。
REL_OFFSETS = {"前天": -2, "昨天": -1, "昨晚": -1, "今天": 0, "今早": 0,
               "今晚": 0, "明天": 1, "明早": 1, "明晚": 1, "后天": 2,
               "大后天": 3}
REL_SORTED = sorted(REL_OFFSETS, key=len, reverse=True)   # 长词优先

# 这些仍然无法换算：要么跨度不定，要么依赖说话语境。
# ★ 正文里**不删除**它们 —— 删了会留下「本20点前交作品」这种残句（实测出现）。
AMBIGUOUS = ("周末", "过几天", "过两天", "下周", "上周", "这周", "月底", "月初",
             "下个月", "上个月", "年底", "年初", "改天", "回头",
             "待会儿", "刚才")

CN_DATE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
# 「2025年11月2日」—— 原文已经写明中文年份，必须识别，不能只截出「11月2日」
CN_FULL = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?")
# 「去年11月2日」「前年…」—— 年份由修饰词决定，暂不支持换算；
# 但**绝不能**把里面的「11月2日」当成绝对日期去核验。
REL_YEAR = re.compile(r"(大前年|前年|去年|今年|明年|后年)\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?")
REL_YEAR_WORDS = ("大前年", "前年", "去年", "今年", "明年", "后年")
ISO_DATE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
# 无年份的分隔写法（10-26 / 10.26）。只在**清理正文**时使用，
# 从来源提取事实日期时不用它 —— 定事实要严格，清正文要宽。
# 负向断言排除「体重10.26」「10.26元」这类数值。
_MD_TAIL = r"(?![\d.])(?!\s*(?:元|块|分|个|%|％|kg|g|ml|l|cm|km|m|点|折|倍|岁|斤))"
MD_DATE = re.compile(r"(?<![\d.])(\d{1,2})[-/.](\d{1,2})" + _MD_TAIL, re.I)
UNDETERMINED = "具体日期未确定"

# 有核验日期时，正文里若残留这些词，读者仍会算错「是哪一晚」——
# 但又无法机械改写成准确说法，只能标人工复核。
VAGUE_SLOT = ("今晚", "明晚", "昨晚", "待会儿", "刚才", "回头")

# 纯时段词：只说"一天里的哪一段"，不指向具体哪一天。
# ★ 2026-10-28 实测缺陷（记忆系统 v2 漏网的一类）：
#   原文只有「辣椒炒肉」三个字，模型拿**消息发送时间**推断出"中午"，
#   写成「<OWNER>中午吃的是辣椒炒肉」。结构化字段明明 time_basis=unknown、
#   event_time=None，程序却不管正文 —— 几天后她就拿这句当事实问
#   「你中午不是吃的辣椒炒肉嘛，怎么又饿了呀」。
#   这和 v2 批评的「拿消息时间冒充原文信息」是同一个错的另一种写法。
# ★ **只标记、不删除**：删了会坏语义（「<OWNER>晚上不吃饭」会变成「<OWNER>不吃饭」）。
PERIOD_WORDS = ("中午", "早上", "早晨", "上午", "下午", "傍晚",
                "晚上", "夜里", "半夜", "凌晨", "白天", "深夜")


# ---------------------------------------------------------------- 基础
def norm_text(s: str) -> str:
    return re.sub(r"[\s，。、！？,.!?~～]+", "", str(s or ""))


def parse_ms(sent_at_ms) -> datetime | None:
    """严格解析为**北京时间**；不可解析返回 None（不接受 "abc" 这种真值）。"""
    try:
        v = int(sent_at_ms)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    try:
        return datetime.fromtimestamp(v / 1000, tz=BEIJING)
    except (OSError, OverflowError, ValueError):
        return None


def valid_date(y: int, mo: int, d: int) -> bool:
    try:
        datetime(y, mo, d)
        return True
    except ValueError:
        return False


def iso(event_time: str | None, year: int | None = None) -> str | None:
    """把内部表示统一成 YYYY-MM-DD。

    ★ 实测缺陷（2026-10-25）：旧版对 `"10-22"` 返回 None，于是
      `iso(cand) != iso(et)` 恒成立 —— 正文里本来**相等**的日期每次都被
      "改写"一遍，note 里还会印出一个空日期「正文日期  与核验结果不一致」。
      现在无年份写法补 `year`（缺省当前北京时间年份），比较才成立。
    """
    if not event_time:
        return None
    s = str(event_time).strip()
    m = ISO_DATE.search(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return "%04d-%02d-%02d" % (y, mo, d) if valid_date(y, mo, d) else None
    m = CN_DATE.search(s)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        y = year or datetime.now(BEIJING).year
        return "%04d-%02d-%02d" % (y, mo, d) if valid_date(y, mo, d) else None
    m = MD_DATE.search(s)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        y = year or datetime.now(BEIJING).year
        return "%04d-%02d-%02d" % (y, mo, d) if valid_date(y, mo, d) else None
    return None


def month_day(et: str | None) -> str:
    """只取 MM-DD：正文通常只写月日，比较时不该被年份差异干扰。"""
    v = iso(et)
    return v[5:] if v else ""


def disp_date(event_time: str | None) -> str:
    """显示用简写：2026-10-22 → 10月22日；10-22 → 10月22日。"""
    et = iso(event_time)
    if not et:
        return ""
    parts = et.split("-")
    if len(parts) == 3:
        return "%d月%d日" % (int(parts[1]), int(parts[2]))
    return "%d月%d日" % (int(parts[0]), int(parts[1]))


def extract_rels(text: str) -> list[str]:
    """按**完整表达**抽相对词：大后天 → ['大后天']，不会再抽出 后天。"""
    out, t = [], str(text or "")
    for w in REL_SORTED:
        if w in t:
            out.append(w)
            t = t.replace(w, "\x00")
    return out


def find_dates(text: str, loose: bool = False) -> list[tuple[int | None, int, int]]:
    """返回 [(year|None, month, day)]，**已做日历校验**。

    `loose=True` 时额外认 `10-26` / `10.26` 这类无年份写法 —— 只给
    「清理正文」用；从来源提取事实日期必须严格（避免把数值当日期）。

    ★ 识别顺序是硬要求：
      1. ISO 与「YYYY年M月D日」——**原文写明的年份必须保留**；
      2. 「去年/前年/今年…」这类相对年份日期**先整段挖掉**，
         否则里面的「11月2日」会被当成绝对日期（实测会把
         「去年11月2日」核验成 2026-11-02 并宣布成功）；
      3. 剩下的才当无年份月日。
    """
    out: list[tuple[int | None, int, int]] = []
    s = str(text or "")
    for m in ISO_DATE.finditer(s):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if valid_date(y, mo, d):
            out.append((y, mo, d))
    s1 = ISO_DATE.sub(" ", s)
    for m in CN_FULL.finditer(s1):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if valid_date(y, mo, d):
            out.append((y, mo, d))
    s2 = CN_FULL.sub(" ", s1)
    s3 = REL_YEAR.sub(" ", s2)          # 相对年份日期整段排除
    # 2000 年是闰年，用它做日历校验才不会把「2月29日」判成非法
    for m in CN_DATE.finditer(s3):
        mo, d = int(m.group(1)), int(m.group(2))
        if valid_date(2000, mo, d):
            out.append((None, mo, d))
    s4 = CN_DATE.sub(" ", s3)
    if loose:
        for m in MD_DATE.finditer(s4):
            mo, d = int(m.group(1)), int(m.group(2))
            if valid_date(2000, mo, d):
                out.append((None, mo, d))
    return out


def rel_year_spans(text: str) -> list[str]:
    """「去年11月2日」这类整段原文 —— 供清理正文时整段移除。"""
    return [m.group(0) for m in REL_YEAR.finditer(str(text or ""))]


def _anchor_expr_ok(body: str, raw: str) -> bool:
    """锚点原文是否**真的说过**这段时间表达。

    ★ 相对词必须按**完整表达**比对，不能用子串：
      `time_raw="后天"` 会在锚点原文「大后天考试」里子串命中，
      而 `_resolve_time` 那边是按完整表达正确拒绝的。
      两处规则不一致，就会出现「日期算不出来、却把模型写的『后天』当成原话」。

    整串照抄的表达（「本周末20点前」「10月26日」）没有相对词，才走子串检查。
    """
    body = str(body or "")
    raw = str(raw or "").strip()
    if not raw:
        return True
    raw_rels = extract_rels(raw)
    if raw_rels:
        body_rels = set(extract_rels(body))
        return all(w in body_rels for w in raw_rels)
    return raw in body


def _raw_date_span(text: str, y: int | None, mo: int, d: int) -> str | None:
    if y:
        m = re.search(r"%d\s*[-/.]\s*%d\s*[-/.]\s*%d" % (y, mo, d), text or "")
        if m:
            return m.group(0)
        m = re.search(r"%d\s*年\s*%d\s*月\s*%d\s*[日号]?" % (y, mo, d), text or "")
        if m:
            return m.group(0)
    m = re.search(r"%d\s*月\s*%d\s*[日号]" % (mo, d), text or "")
    if m:
        return m.group(0)
    m = MD_DATE.search(text or "")
    while m:
        if (int(m.group(1)), int(m.group(2))) == (mo, d):
            return m.group(0)
        m = MD_DATE.search(text or "", m.end())
    return None


# ---------------------------------------------------------------- 记录
def new_record(mid: int, kind: str, text: str, certainty: str = "",
               created: str = "", source_msg_ids: list[int] | None = None,
               speaker: str = "", event_time: str | None = None,
               time_basis: str = TB_UNKNOWN, time_raw: str = "",
               time_anchor_msg_id: int | None = None,
               needs_review: bool = False) -> dict:
    return {
        "id": "m%04d" % mid,
        "kind": kind,
        "text": text,
        "certainty": certainty or "",
        "created": created,
        "source_msg_ids": source_id_values(source_msg_ids),
        "speaker": speaker,
        "event_time": iso(event_time),
        "time_basis": time_basis,
        "time_raw": time_raw,
        "time_anchor_msg_id": time_anchor_msg_id,
        "needs_review": bool(needs_review),
        "archived": False,
        "archived_at": "",
        "archive_reason": "",
    }


def speaker_of(msgs: list[dict]) -> str:
    roles = {"<OWNER>" if m.get("role") == "user" else "绯栀"
             for m in (msgs or []) if m.get("role")}
    return roles.pop() if len(roles) == 1 else ""


def _resolve_time(raw: str, anchor, src_by_id: dict) -> tuple[str | None, str, list[str]]:
    """返回 (event_time, time_basis, notes)。**只认来源，不看正文。**"""
    notes: list[str] = []
    raw = str(raw or "").strip()

    # 1) 相对表达 → 唯一锚点，且按完整表达匹配
    #
    # 「今天下午」「明天早上」这类 = 支持词 + 时段修饰。整串不等于支持词，
    # 旧版直接掉进 unknown（实测 A 批里「今天下午」的时间就这么丢的）。
    # 只要串里**恰好含一个**支持词就用它；仍有锚点校验兜底，不会乱算。
    rel = raw if raw in REL_OFFSETS else None
    if rel is None:
        cands = extract_rels(raw)
        if len(cands) == 1:
            rel = cands[0]
    if rel:
        aid = as_msg_id(anchor)
        if aid is None:
            return None, TB_UNKNOWN, ["相对时间 %r 未给锚点 → 未知" % raw]
        m = src_by_id.get(aid)
        if m is None:
            return None, TB_UNKNOWN, ["锚点 %s 不在引用的来源里 → 未知" % aid]
        found = extract_rels(str(m.get("text") or ""))
        if rel not in found:
            return None, TB_UNKNOWN, [
                "锚点消息里的相对词是 %s，与 %r 不符 → 未知" % (found or "无", rel)]
        dt = parse_ms(m.get("sent_at_ms"))
        if dt is None:
            return None, TB_UNKNOWN, ["锚点消息时间不可解析 → 未知"]
        d = dt + timedelta(days=REL_OFFSETS[rel])
        et = "%04d-%02d-%02d" % (d.year, d.month, d.day)
        if rel == raw:
            notes.append("按锚点 %s 的 %r 换算 → %s" % (aid, rel, disp_date(et)))
        else:
            notes.append("原文 %r 含相对词 %r，按锚点 %s 换算 → %s"
                         % (raw, rel, aid, disp_date(et)))
        return et, TB_MESSAGE, notes

    # 2) 明确日期 → 只从来源原文提取
    #
    # ★ 年份只有两种合法来源：**原文写明的年份**，或**明确不支持**（保留 MM-DD）。
    #   绝不靠「月日 ≥ 消息月日」去补 —— 那是拿消息时间冒充原文信息，
    #   实测会把「去年11月2日」「2025年11月2日」都算成 2026-11-02 还宣布核验成功。
    pool_full: list[tuple[int, int, int]] = []
    pool_md: list[tuple[int, int]] = []
    relspans: list[str] = []
    for m in src_by_id.values():
        t = str(m.get("text") or "")
        relspans += rel_year_spans(t)
        for (y, mo, d) in find_dates(t):
            if y:
                pool_full.append((y, mo, d))
            else:
                pool_md.append((mo, d))

    if relspans:
        notes.append("来源含相对年份表达 %s（去年/前年…），暂不支持换算 → 未知"
                     % relspans)
        return None, TB_UNKNOWN, notes

    uniq_full = sorted(set(pool_full))
    uniq_md = sorted(set(pool_md))
    if len(uniq_full) + len(uniq_md) > 1:
        notes.append("来源含多个日期 %s → 无法唯一确定" % (
            ["%04d-%02d-%02d" % t for t in uniq_full]
            + ["%02d-%02d" % t for t in uniq_md]))
        return None, TB_UNKNOWN, notes
    if len(uniq_full) == 1:
        y, mo, d = uniq_full[0]
        et = "%04d-%02d-%02d" % (y, mo, d)
        notes.append("来源原文写明 %s → explicit_text" % et)
        return et, TB_EXPLICIT, notes
    if len(uniq_md) == 1:
        mo, d = uniq_md[0]
        et = "%02d-%02d" % (mo, d)
        notes.append("来源原文只有 %s、没写年份 → 保留 MM-DD，年份未定" % disp_date(et))
        return et, TB_EXPLICIT, notes

    if raw and raw not in REL_OFFSETS:
        notes.append("时间表达 %r 不在支持范围（或本身有歧义）→ 未知" % raw)
    return None, TB_UNKNOWN, notes


def _normalize_text(text: str, et: str | None) -> tuple[str, list[str], bool]:
    """让正文里的时间与已核验结果一致。

    返回 (新正文, notes, 是否需要人工复核)。
    ★ 复核标记的判据是「**信息被改动过**」——删掉模型写的日期是信息损失，
      留下无法机械改写的时段词（今晚/明晚）会让长期读取继续出错。
    """
    notes: list[str] = []
    review = False
    out = text

    if et:
        shown = disp_date(et)
        target = month_day(et)
        # 先替换相对词（长词优先，避免「大后天」被拆）
        # ★ 正文里出现**多个不同**相对词时禁止机械替换：它们各自指向不同日期，
        #   全压成 et 会直接造出错误日期。实测：「昨天不是还气游戏输了，今天缓过来没」
        #   被改写成「10月14日…10月14日」，「今天」凭空变成了昨天。
        rels_in_text = extract_rels(out)
        if len(rels_in_text) > 1:
            notes.append("正文含多个相对词 %s，机械替换会互相污染 → 保留原文待复核"
                         % rels_in_text)
            review = True
        else:
            for w in REL_SORTED:
                if w in out:
                    out = out.replace(w, shown)
                    notes.append("正文相对词 %r → %s" % (w, shown))
        # 「去年11月2日」整段改写：它的年份由修饰词决定，`find_dates` 看不见里面的月日
        for span in rel_year_spans(out):
            out = out.replace(span, shown)
            notes.append("正文相对年份日期 %r → %s" % (span, shown))
            review = True
        left_ry = [w for w in REL_YEAR_WORDS if w in out]
        if left_ry:
            notes.append("正文仍含相对年份 %s，无法机械改写 → 标记复核" % left_ry)
            review = True
        # 再把不一致的日期改成核验值
        for y, mo, d in find_dates(out, loose=True):
            span = _raw_date_span(out, y, mo, d)
            if not span:
                continue
            cand = ("%04d-%02d-%02d" % (y, mo, d)) if y else ("%02d-%02d" % (mo, d))
            # ★ 正文明确写了年份时必须比完整年份：只比月日会让
            #   「正文 2025-10-21 / 字段 2026-10-21」的冲突整条漏掉（实测漏过）。
            if y is not None:
                same = iso(cand) == iso(et)
            else:
                same = month_day(cand) == target
            if same:
                continue
            out = out.replace(span, shown)
            notes.append("正文日期 %s 与核验结果不一致 → 改写为 %s"
                         % ((iso(cand) or disp_date(cand)) if y is not None
                            else disp_date(cand), shown))
            review = True
        left = [w for w in VAGUE_SLOT if w in out]
        if left:
            notes.append("正文仍含无法机械改写的时段词 %s → 标记复核" % left)
            review = True
        return out, notes, review

    # 无时间依据：删掉相对词与日期
    for span in rel_year_spans(out):
        out = out.replace(span, "")
        notes.append("正文含相对年份日期 %r → 移除" % span)
        review = True
    for w in REL_SORTED:
        if w in out:
            out = out.replace(w, "")
            notes.append("正文含相对词 %r → 移除" % w)
            review = True
    for w in REL_YEAR_WORDS:
        if w in out:
            out = out.replace(w, "")
            notes.append("正文含相对年份 %r → 移除" % w)
            review = True
    # ★ 歧义时间词**保留原文**：删掉会出现「本20点前交作品」这种残句（实测过），
    #   保留 + 末尾「具体日期未确定」+ needs_review，既不失真也标明了程序没定日期。
    left_amb = [w for w in AMBIGUOUS if w in out]
    if left_amb:
        notes.append("正文含歧义时间 %s → 保留原文，仅标记日期未定" % left_amb)
        review = True
    # ★ 无时间依据时，正文里的时段词最可疑：原文多半没说，是模型看消息时间推的。
    left_period = [w for w in PERIOD_WORDS if w in out]
    if left_period:
        notes.append("正文含时段词 %s，但来源没有给出任何时间依据 —— "
                     "可能是拿消息发送时间推的，保留原文并标记复核" % left_period)
        review = True
    for y, mo, d in find_dates(out, loose=True):
        span = _raw_date_span(out, y, mo, d)
        if span:
            out = out.replace(span, "")
            notes.append("无依据却出现日期 %s → 移除"
                         % disp_date(("%04d-%02d-%02d" % (y, mo, d)) if y else
                                     ("%02d-%02d" % (mo, d))))
            review = True
    return out, notes, review


STD_FIELDS = (("kind", "fact"), ("text", ""), ("certainty", ""), ("created", ""),
              ("source_msg_ids", []), ("speaker", ""), ("event_time", None),
              ("time_basis", TB_UNKNOWN), ("time_raw", ""),
              ("time_anchor_msg_id", None),
              # ★ 原话的发送时间（epoch ms）。`created` 只是入库日，
              #   拿它冒充"这句话是哪天说的"会直接骗到召回（实测：
              #   来源 10-15 说的「本周末」，渲染成「这条记于 10-26」）。
              ("time_raw_at_ms", None),
              ("needs_review", False),
              ("quarantined", False),
              # ★ 来源闸门状态（v1.3 接线用）：pending / rejected 绝不允许进入召回。
              #   默认给 "legacy" —— 生产已有的 96 条旧记录没有过闸门，
              #   不能被新闸门误伤；只有显式标成 eligible 的新写入才放行。
              ("gate_state", "legacy"),
              ("archived", False), ("archived_at", ""), ("archive_reason", ""))


def ensure_fields(rec: dict) -> dict:
    """补齐标准字段。调用方给最小 dict（只写 text/source_msg_ids）也不至于落成半条。

    ★ 列表默认值必须每次新建，否则 `[]` 会被多条记录共享。
    """
    out = dict(rec or {})
    for k, d in STD_FIELDS:
        if k not in out:
            out[k] = list(d) if isinstance(d, list) else d
    if not out.get("created"):
        out["created"] = datetime.now(BEIJING).strftime("%Y-%m-%d")
    return out


def validate(rec: dict, batch_msgs: list[dict],
             *, strict_sources: bool = True) -> tuple[dict, list[str]]:
    """程序侧校验并规范化。只使用 `source_msg_ids` 实际引用的消息。

    `strict_sources=False`：调用方拿不到消息体（例如只改文案的 patch）时，
    **保留**引用 id 原样，不因“这批里没有”就剔除 —— 否则一次文案修改
    就把溯源码清空，事后再也无法复核记录来历。代价是这些 id 不参与
    时间/说话者推导（消息体确实不在手上，不能凭空推断）。
    """
    notes: list[str] = []
    out = ensure_fields(rec)
    by_id = {}
    for m in (batch_msgs or []):
        n = as_msg_id(m.get("id"))
        if n is not None:
            by_id[n] = m

    # --- 来源先筛：只留真实存在的 id ---
    raw_ids = source_id_values(out.get("source_msg_ids"))
    kept: list[int] = []
    missing: list[int] = []
    for i in raw_ids:
        iv = as_msg_id(i)
        if iv is None:
            notes.append("来源 id %r 不是合法整数 → 丢弃（不做强转）" % (i,))
            continue
        if iv in by_id:
            kept.append(iv)
        else:
            missing.append(iv)
            notes.append("来源 id %s 不在本批消息里 → %s"
                         % (i, "剔除" if strict_sources else "保留（未参与推断）"))
    if strict_sources:
        out["source_msg_ids"] = kept
    else:
        seen, merged = set(), []
        for i in list(raw_ids):
            iv = as_msg_id(i)
            if iv is None or iv in seen:
                continue
            seen.add(iv)
            merged.append(iv)
        out["source_msg_ids"] = merged
    cited = [by_id[i] for i in kept]          # ★ 只用被引用的消息

    # --- 说话者：只看被引用的来源 ---
    derived = speaker_of(cited)
    if derived:
        if out.get("speaker") not in (derived, ""):
            notes.append("speaker 按引用来源校正为 %s" % derived)
        out["speaker"] = derived
    elif kept:
        # 有来源可查、但引用里角色混合：speaker 无法从来源推定，置空。
        # ★ 但要区分两种情况：
        #   · 正文**显式提到双方**（「绯栀追问…<OWNER>说…」）= 双人互动记录，
        #     它本来就没有单一说话者，speaker 为空是正确答案，不该标复核。
        #   · 正文只提一方或都没提 = 真的无法判断主体，才标复核。
        text_now = str(out.get("text") or "")
        both_sides = ("绯栀" in text_now) and ("<OWNER>" in text_now)
        if out.get("speaker"):
            notes.append("引用来源角色混合，speaker 无法确认 → 置空")
        out["speaker"] = ""
        if both_sides:
            notes.append("正文提到双方 → 判为双人互动，speaker 为空属正常，不标复核")
        else:
            out["needs_review"] = True
    else:
        # 完全没有来源可查：原值既不能证实也不能推翻，保留但标记复核
        out["speaker"] = str(out.get("speaker") or "").strip()
        if out["speaker"]:
            out["needs_review"] = True

    # --- 时间 ---
    if str(out.get("time_basis") or "") == TB_MANUAL and out.get("event_time"):
        # 人工修正过的时间：程序**不复算、不推翻**，但永久带复核标记。
        # 否则一条人工订正过的记录，下次跑 validate 又被打回「未知」。
        et = iso(out.get("event_time"))
        basis = TB_MANUAL if et else TB_UNKNOWN
        if et:
            notes.append("时间为人工修正 %s → 不再由来源复算" % disp_date(et))
        else:
            notes.append("人工修正的日期本身不合法 → 置空")
        out["needs_review"] = True
    else:
        et, basis, tnotes = _resolve_time(out.get("time_raw"),
                                          out.get("time_anchor_msg_id"),
                                          {i: by_id[i] for i in kept})
        notes += tnotes
    out["event_time"] = et if basis != TB_UNKNOWN else None
    out["time_basis"] = basis
    # 只存到 MM-DD = 年份未定，精度不足，必须待复核（否则与文档承诺不符）
    if out["event_time"] and len(str(out["event_time"])) == 5:
        out["needs_review"] = True

    # --- 原话发送时间：必须是**有效来源里真的说过这句时间**的那条消息 ---
    # ★ 三个条件缺一不可，任一不满足就置空（渲染成「原话时间未知」）：
    #   1. 锚点被 source_msg_ids 引用（不属于来源的消息不能当基准）
    #   2. 锚点原文真的含这段时间表达（否则就是拿无关消息的时间冒充）
    #   3. sent_at_ms 可解析
    #   绝不用 created（入库日）顶替：那会把「10-15 说的本周末」渲染成「记于 10-26」。
    am_id = as_msg_id(out.get("time_anchor_msg_id"))
    raw_txt = str(out.get("time_raw") or "").strip()
    ok_anchor = False
    amv = by_id.get(am_id) if am_id is not None else None
    if amv is not None and am_id in kept:
        try:
            sent_val = int(amv.get("sent_at_ms"))
        except (TypeError, ValueError):
            sent_val = 0
        if sent_val > 0:
            if not raw_txt:
                ok_anchor = True          # 没有时间表达时，锚点只提供发送时刻
            else:
                body = str(amv.get("text") or "")
                ok_anchor = _anchor_expr_ok(body, raw_txt)
                if not ok_anchor:
                    notes.append("锚点 %s 的原文里没有 %r → 原话时间未知"
                                 % (am_id, raw_txt))
            if ok_anchor:
                out["time_raw_at_ms"] = sent_val
    if not ok_anchor:
        out["time_raw_at_ms"] = None

    # --- 正文与已核验时间统一 ---
    text, xnotes, review = _normalize_text(str(out.get("text") or "").strip(),
                                           out["event_time"])
    notes += xnotes
    out["text"] = re.sub(r"[，、]{2,}", "，", text).strip("，。 、")
    if review:
        out["needs_review"] = True
    if not out["text"]:
        out["text"] = UNDETERMINED
        out["needs_review"] = True
    # 「具体日期未确定」只在**记录自己声称过时间**时才加。
    # 判据从 xnotes 改成 time_raw：删掉模型瞎写的日期，不等于这条记录在讲时间
    # ——「<OWNER>不吃香菜，具体日期未确定」是纯噪音，事实类记录不该长这条尾巴。
    if basis == TB_UNKNOWN and str(out.get("time_raw") or "").strip():
        if UNDETERMINED not in out["text"]:
            out["text"] = out["text"].rstrip("，。 ") + "，" + UNDETERMINED
    out["needs_review"] = bool(out.get("needs_review"))
    return out, notes


def migrate_legacy(items: list[dict], start_mid: int, today: str) -> tuple[list[dict], int]:
    """旧格式 → 新结构：稳定 ID、`added`→`created`、**不补造来源**、不冒充事件时间。"""
    out, mid = [], start_mid
    for x in items:
        mid += 1
        out.append(new_record(
            mid, x.get("kind") or "fact", x.get("text", ""),
            certainty=x.get("certainty", ""),
            created=x.get("added") or x.get("created") or today,
            source_msg_ids=x.get("source_msg_ids"),
            speaker=x.get("speaker", ""),
            event_time=x.get("event_time"),
            time_basis=x.get("time_basis") or TB_UNKNOWN,
            time_raw=x.get("time_raw", ""),
            time_anchor_msg_id=x.get("time_anchor_msg_id"),
            needs_review=x.get("needs_review", False),
        ))
    return out, mid


# ---------------------------------------------------------------- CRUD（纯函数，不碰磁盘）
class RecordError(ValueError):
    """调用方用错了（id 不存在 / 字段不可改 / 改时间没给理由）。"""


def norm_id(rid) -> str:
    """m0007 / "M7" / 7 → "m0007"。"""
    s = str(rid if rid is not None else "").strip().lower()
    if s.startswith("m"):
        s = s[1:]
    if not s.isdigit():
        raise RecordError("记录 id 不合法：%r" % (rid,))
    return "m%04d" % int(s)


def find_index(records, rid) -> int:
    want = norm_id(rid)
    for i, r in enumerate(records or []):
        if str(r.get("id") or "") == want:
            return i
    return -1


def get_record(records, rid) -> dict | None:
    i = find_index(records, rid)
    return dict(records[i]) if i >= 0 else None


def active_records(records) -> list[dict]:
    """未归档的记录。"""
    return [r for r in (records or []) if not r.get("archived")]


GATE_OPEN = ("eligible", "legacy")
GATE_BLOCKED = ("pending", "rejected")
GATE_STATES = ("eligible", "pending", "rejected", "legacy")
GATE_INVALID = "__invalid__"


def gate_of(rec: dict) -> str:
    """取一条记录的闸门状态。

    ★ **只有字段缺失**才视为 legacy（兼容没走过闸门的旧记录）。
      字段存在但值是 ""/None/False/0 这类空值时必须阻断 ——
      用 `or "legacy"` 会把这些非法值全部放行（实测：显式 "" 也能召回）。
      非字符串、去空白后为空、以及不在枚举里的值，一律返回 GATE_INVALID。
    """
    if not isinstance(rec, dict) or "gate_state" not in rec:
        return "legacy"
    v = rec.get("gate_state")
    if not isinstance(v, str):
        return GATE_INVALID
    v = v.strip()
    if not v:
        return GATE_INVALID
    return v if v in GATE_STATES else GATE_INVALID


def normalize_gate(value, default: str = "pending") -> str:
    """把调用方给的 gate_state 规范化。None/空/非法一律收敛到 default。

    ★ 绝不能"省略就继承旧值" —— 那会让旧 eligible 通过一次不带参数的调用复活。
    """
    if isinstance(value, str):
        v = value.strip()
        if v in GATE_STATES:
            return v
    return default



def recallable(records) -> list[dict]:
    """**可以进 prompt 的**记录：未归档、未被隔离、且来源闸门放行。

    隔离区（quarantined）存放「抽取时给不出有效来源」的记录 ——
    不丢掉（丢掉就永远查不到模型到底编了什么），但绝不参与召回。

    ★ 来源闸门（`gate_state`）：pending / rejected 一律不放行。
      生产已有的旧记录没有过闸门，标为 legacy 放行；新写入默认 pending，
      必须由闸门的 eligible 导出显式置位才可召回。
    """
    out = []
    for r in active_records(records):
        if r.get("quarantined"):
            continue
        if gate_of(r) not in GATE_OPEN:
            continue
        out.append(r)
    return out


def count_unreviewed(records) -> int:
    return sum(1 for r in active_records(records) if r.get("needs_review"))


def approve_pending(records, *, ids=None, by: str = "auto",
                    dry_run: bool = False
                    ) -> tuple[list[dict] | None, list[str], dict]:
    """把 `pending` 放行成 `eligible` —— **pending 唯一的出口**。

    ★ 为什么必须有这个函数（2026-10-28）：
      `recallable()` 的注释写着「必须由闸门的 eligible 导出显式置位才可召回」，
      可是这个"导出"从来没实现，于是抽取链路只好把 gate 硬编码成 `legacy`
      让它能跑 —— 结果闸门整套机制（pending 不召回、promote 矩阵、来源校验）
      全成了摆设，模型编的记忆落地即进 prompt。
      实测缺陷：原文只有「辣椒炒肉」，模型写成「<OWNER>中午吃的是辣椒炒肉」，
      三天后她拿这句当事实问「你中午不是吃的辣椒炒肉嘛」。

    ★ 两级放行：
      by="auto"  —— 只放行**没有任何疑点**的：gate 必须 pending、未归档未隔离、
                    `needs_review` 为假、来源非空。有标记的一律留在 pending 等人。
      by="human" —— 人已经看过了，不再要求 `needs_review` 为假；
                    但归档/隔离的记录仍然跳过（那是另一套状态，不该被批准复活）。

    ★ `dark_run=True` 只出报告不改数据。

    返回 (新列表或 None, notes, summary)。新列表为 None 表示这次没有任何放行，
    调用方可以直接跳过写盘。
    """
    if by not in ("auto", "human"):
        raise ValueError("by 只能是 auto / human：%r" % (by,))
    recs = [ensure_fields(dict(r)) for r in (records or [])]
    notes: list[str] = []
    summary: dict = {"approved": [], "kept": [], "skipped": []}

    want = None
    if ids is not None:
        raw = ids if isinstance(ids, (list, tuple, set)) else [ids]
        want = {norm_id(x) for x in raw}

    for i, r in enumerate(recs):
        # ★ 不能假设 id 一定存在：`_view()` 的注释里写着「未迁移的旧记录既没有
        #   kind 也没有 id」。那种记录不参与闸门放行，但**绝不能因此让整批抽取
        #   抛异常中断** —— 实测 _test_memory_input 就是这么炸的。
        try:
            rid = norm_id(r.get("id"))
        except RecordError:
            summary["skipped"].append("(无id)")
            continue
        if want is not None and rid not in want:
            continue
        if r.get("archived"):
            summary["skipped"].append(rid)
            continue
        if r.get("quarantined"):
            # 隔离项要走 promote_quarantined 补来源，不能靠批准直接复活
            summary["skipped"].append(rid)
            continue
        if gate_of(r) != "pending":
            summary["skipped"].append(rid)
            continue
        if by == "auto" and r.get("needs_review"):
            summary["kept"].append(rid)
            notes.append("%s 有复核标记，继续留在 pending" % rid)
            continue
        if not source_id_values(r.get("source_msg_ids")):
            summary["kept"].append(rid)
            notes.append("%s 没有来源消息，继续留在 pending" % rid)
            continue
        if not dry_run:
            r["gate_state"] = "eligible"
            recs[i] = r
        summary["approved"].append(rid)

    if not summary["approved"] or dry_run:
        return None, notes, summary
    return recs, notes, summary


# 纯文案字段：改动**不触发**时间重算，绝不推翻既有核验
PATCH_FIELDS = ("text", "certainty", "kind")
# 要求**按来源重新计算**（不是人工指定）
TIME_RECALC_FIELDS = ("time_raw", "time_anchor_msg_id")
# **人工直接指定日期**，必须给 reason
TIME_MANUAL_FIELDS = ("event_time",)
TIME_FIELDS = TIME_RECALC_FIELDS + TIME_MANUAL_FIELDS      # 兼容旧调用
# 结构性字段，CRUD 一律不碰
LOCKED_FIELDS = ("id", "source_msg_ids", "created",
                 "archived", "archived_at", "archive_reason", "time_basis")


def _clean_text(t: str) -> str:
    return re.sub(r"[，、]{2,}", "，", str(t or "")).strip("，。 、")


def as_msg_id(v) -> int | None:
    """严格的消息 ID。

    ★ 绝不用 `int(v)` 直接强转：`int(True) == 1`、`int(1.9) == 1`
      —— 一个非法的布尔或小数会被**静默变成真实存在的消息 ID**，
      然后来源校验"通过"，等于凭空造出一条有来源的记录。
      只接受正整数与纯数字字符串；bool / float / 其它一律返回 None。
    """
    if isinstance(v, bool) or isinstance(v, float):
        return None
    if isinstance(v, int):
        return v if v > 0 else None
    if isinstance(v, str):
        s = v.strip()
        # isdigit() also accepts characters such as ² and ①, which int()
        # cannot parse. Unicode decimal digits remain supported.
        if s.isdecimal():
            try:
                n = int(s)
            except ValueError:
                # Also covers Python's bound on extremely long decimal input.
                return None
            return n if n > 0 else None
    return None


def source_id_values(value) -> list:
    """Validate the source-ID container without coercing its elements.

    Missing/None is an explicit historical no-source value. Only lists are
    collections: strings, dictionaries and tuples must never be iterated into
    different message IDs. Individual IDs are filtered by as_msg_id at the
    caller, preserving validate's historical mixed-list behavior.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise RecordError("source_msg_ids 必须是列表或 None，不能是 %s"
                          % type(value).__name__)
    return list(value)


def _batch_ids(batch_msgs) -> set:
    out = set()
    for m in (batch_msgs or []):
        n = as_msg_id(m.get("id"))
        if n is not None:
            out.add(n)
    return out


def _recalc_ready(rec: dict, batch_msgs) -> tuple[bool, str]:
    """按来源重算所需的消息体是否齐备。缺一条就不能算 —— 不许拿半套来源硬算。"""
    need = set()
    for i in source_id_values(rec.get("source_msg_ids")):
        n = as_msg_id(i)
        if n is not None:
            need.add(n)
    if not need:
        return False, "该记录没有来源，无法按来源重算时间"
    anchor = rec.get("time_anchor_msg_id")
    an = as_msg_id(anchor)
    if an is not None:
        need.add(an)
    miss = sorted(need - _batch_ids(batch_msgs))
    if miss:
        return False, "缺少来源消息体 %s，无法重算（拒绝在半套来源上硬算）" % miss
    return True, ""


def add_record(records, rec: dict, batch_msgs: list[dict],
               last_mid: int = 0, *, trusted: bool = False,
               require_sources: bool = True, gate_state: str = "pending"
               ) -> tuple[list[dict], dict, list[str], int]:
    """插入一条。返回 (新列表, 落库记录, notes, 新 last_mid)。

    ★ 默认**不信任**输入：抽取端（模型）不得设置 `time_basis`，
      也不得自称 `needs_review=False` 把复核标记按掉，更不能带归档状态。
      实测旧实现里模型自报 `time_basis="manual"` + 任意合法日期就能绕过来源核验
      —— 来源里根本没有那个日期，记忆却照收。人工修订走 `add_manual_record`。

    ★ `require_sources=True`（默认）：**必须有非空且在批次里真实存在的来源**。
      旧数据迁移允许无来源是历史兼容；新写入不能沿用这个例外 ——
      否则模型凭空编一条、或引用一个不存在的消息 id，都能正常入库并参与召回。
    """
    r = dict(rec)
    if not r.get("id"):
        r["id"] = "m%04d" % (int(last_mid) + 1)
    rid = norm_id(r["id"])
    r["id"] = rid
    if find_index(records, rid) >= 0:
        raise RecordError("id %s 已存在；更新请用 patch_record" % rid)

    raw_values = source_id_values(r.get("source_msg_ids"))
    r["source_msg_ids"] = raw_values
    if require_sources:
        raw_ids = []
        for i in raw_values:
            n = as_msg_id(i)
            if n is not None:
                raw_ids.append(n)
        if not raw_ids:
            raise RecordError("新增记录必须有来源消息（source_msg_ids 不能为空）；"
                              "无来源只允许走 migrate_legacy 的历史迁移")
        miss = [i for i in raw_ids if i not in _batch_ids(batch_msgs)]
        if miss:
            raise RecordError("来源 id %s 不在本批消息里，拒绝入库" % miss)

    if not trusted:
        if str(r.get("time_basis") or "").strip() == TB_MANUAL:
            raise RecordError("抽取入口不得设置 time_basis=manual；"
                              "人工修订请用 add_manual_record")
        r["time_basis"] = TB_UNKNOWN       # 一律由程序按来源复算
        r["needs_review"] = False          # 由程序判定，不接受自报
        # ★ 闸门状态只能由调用方显式给，**不接受输入里自报**
        r.pop("gate_state", None)
    r["gate_state"] = normalize_gate(gate_state, "pending")
    if r.get("quarantined"):
        r["needs_review"] = True           # 隔离区一律待复核
    r["archived"] = False
    r["archived_at"] = ""
    r["archive_reason"] = ""

    stored, notes = validate(r, batch_msgs)
    mid = int(stored["id"][1:])
    return list(records or []) + [stored], stored, notes, max(int(last_mid), mid)


def add_manual_record(records, rec: dict, batch_msgs: list[dict],
                      last_mid: int = 0, *, reason: str = ""
                      ) -> tuple[list[dict], dict, list[str], int]:
    """**人工**新增一条带指定日期的记录 —— 唯一合法的 manual 入口。"""
    if not str(reason or "").strip():
        raise RecordError("人工新增带日期的记录必须给 reason")
    r = dict(rec)
    r["time_basis"] = TB_MANUAL
    r["needs_review"] = True
    recs, stored, notes, mid = add_record(records, r, batch_msgs, last_mid,
                                          trusted=True)
    notes.append("人工新增时间 %r（理由：%s）"
                 % (stored.get("event_time"), str(reason).strip()))
    return recs, stored, notes, mid


def patch_record(records, rid, changes: dict, batch_msgs: list[dict] | None = None,
                 *, reason: str = "") -> tuple[list[dict], dict, dict, list[str]]:
    """改一条记录。返回 (新列表, 改前, 改后, notes)。

    三个入口的语义**严格分开**，旧实现把它们混在一起，于是：
      * 只改 `certainty` 也会重跑完整校验，拿不到消息体就判成「无依据」，
        把已核验的 `2026-10-21 / message_time` 抹成 `None / unknown`。

    现在的分工：
      * `text`/`certainty`/`kind` —— 纯文案改动，**不重算**。
        正文里的时间用**已核验的 `event_time`** 归一化；拿不到来源也保留结论。
      * `time_raw`/`time_anchor_msg_id` —— **按来源重新计算**，要求 batch
        覆盖全部来源与锚点，否则拒绝。结果 basis 是 message_time /
        explicit_text / unknown，**不是 manual**。
      * `event_time` —— **人工直接指定日期**，必须给 `reason`，转 manual。
    """
    recs = list(records or [])
    i = find_index(recs, rid)
    if i < 0:
        raise RecordError("没有 id=%s 的记录" % norm_id(rid))
    before = dict(recs[i])
    cur = ensure_fields(before)

    changes = dict(changes or {})
    bad = [k for k in changes if k in LOCKED_FIELDS]
    if bad:
        raise RecordError("字段不可通过 patch 修改：%s" % ", ".join(sorted(bad)))
    allowed = PATCH_FIELDS + TIME_RECALC_FIELDS + TIME_MANUAL_FIELDS
    unknown = [k for k in changes if k not in allowed]
    if unknown:
        raise RecordError("未知字段：%s" % ", ".join(sorted(unknown)))

    notes: list[str] = []
    manual_ch = [k for k in TIME_MANUAL_FIELDS if k in changes]
    recalc_ch = [k for k in TIME_RECALC_FIELDS if k in changes]
    if manual_ch and recalc_ch:
        raise RecordError("不能同时人工指定日期与要求按来源重算：%s / %s"
                          % (manual_ch, recalc_ch))
    if manual_ch and not str(reason or "").strip():
        raise RecordError("人工指定日期必须给 reason：%s" % ", ".join(manual_ch))

    for k in PATCH_FIELDS:
        if k in changes:
            cur[k] = changes[k]

    if manual_ch:
        raw_et = changes.get("event_time")
        new_et = iso(raw_et)
        if raw_et and not new_et:
            raise RecordError("event_time 不是合法日期：%r" % (raw_et,))
        cur["event_time"] = new_et
        cur["time_basis"] = TB_MANUAL if new_et else TB_UNKNOWN
        cur["needs_review"] = True
        notes.append("人工指定时间：%r → %r（理由：%s）"
                     % (before.get("event_time"), new_et, str(reason).strip()))
        text, n2, _rv = _normalize_text(str(cur.get("text") or "").strip(),
                                       cur["event_time"])
        notes += n2
        cur["text"] = _clean_text(text) or UNDETERMINED

    elif recalc_ch:
        for k in recalc_ch:
            cur[k] = changes[k]
        cur["time_basis"] = TB_UNKNOWN     # 先清掉可能的 manual，才允许重算
        okc, why = _recalc_ready(cur, batch_msgs)
        if not okc:
            raise RecordError(why)
        cur, vnotes = validate(cur, batch_msgs)
        notes += vnotes
        notes.append("按来源重算时间：%r → %r（basis=%s）"
                     % (before.get("event_time"), cur.get("event_time"),
                        cur.get("time_basis")))
        cur["needs_review"] = True

    else:
        # 纯文案/把握改动：用**既有核验结论**归一化正文，不重算、不清空。
        et = cur.get("event_time")
        text, n2, rv = _normalize_text(str(cur.get("text") or "").strip(), et)
        notes += n2
        cur["text"] = _clean_text(text)
        if rv:
            cur["needs_review"] = True
        if not cur["text"]:
            cur["text"] = UNDETERMINED
            cur["needs_review"] = True
        cur["needs_review"] = bool(cur.get("needs_review"))

    recs[i] = cur
    return recs, before, cur, notes


def archive_record(records, rid, reason: str = "",
                   today: str = "") -> tuple[list[dict], dict]:
    """逻辑归档（**绝不物理删除**）。返回 (新列表, 被归档的记录)。

    保留整条记录的理由：`source_msg_ids` 是事后追责与复核的唯一线索，
    删掉就再也无法回答「她凭什么记得这件事」。
    """
    recs = list(records or [])
    i = find_index(recs, rid)
    if i < 0:
        raise RecordError("没有 id=%s 的记录" % norm_id(rid))
    cur = dict(recs[i])
    if cur.get("archived"):
        return recs, cur
    cur["archived"] = True
    cur["archived_at"] = today or datetime.now(BEIJING).strftime("%Y-%m-%d")
    cur["archive_reason"] = str(reason or "").strip()
    recs[i] = cur
    return recs, cur


def restore_record(records, rid) -> tuple[list[dict], dict]:
    """撤销归档。"""
    recs = list(records or [])
    i = find_index(recs, rid)
    if i < 0:
        raise RecordError("没有 id=%s 的记录" % norm_id(rid))
    cur = dict(recs[i])
    cur["archived"] = False
    cur["archived_at"] = ""
    cur["archive_reason"] = ""
    recs[i] = cur
    return recs, cur


def promote_quarantined(records, rid, source_msg_ids, batch_msgs,
                        time_raw: str = "", anchor=None, gate_state=None
                        ) -> tuple[list[dict], dict, list[str]]:
    """把隔离记录提升为可召回 —— **唯一允许补写 `source_msg_ids` 的入口**。

    隔离的成因是「当时给不出有效来源」，不是「内容一定错」。
    后来有了有效证据，应当就地补来源并重新核验，
    而不是再存一条重复文本（否则同一件事会有两条，一条隔离一条有效）。

    ★ **闸门状态矩阵**（否则提升就是一条绕过复核的旁路）：
        旧 pending / rejected → 保持阻断（补来源不等于批准语义复核）
        旧 eligible / legacy  → 接受**本次调用方**给的 gate_state
        其它/非法             → 收敛成 pending（关闭）
      少了这条，一条旧的 eligible 隔离项只要补个来源、这次以 pending 调用，
      就会带着 eligible 身份直接进召回 —— 实测可复现。
    """
    recs = list(records or [])
    i = find_index(recs, rid)
    if i < 0:
        raise RecordError("没有 id=%s 的记录" % norm_id(rid))
    cur = ensure_fields(recs[i])
    if not cur.get("quarantined"):
        raise RecordError("只有隔离记录可以提升：%s" % norm_id(rid))

    old_gate = gate_of(cur)
    if old_gate in GATE_BLOCKED:
        new_gate = old_gate
    elif old_gate in GATE_OPEN:
        # ★ 省略 / None / 非法 gate 一律收敛成 pending，**绝不继承旧 eligible**
        new_gate = normalize_gate(gate_state, "pending")
    else:
        new_gate = "pending"

    ids = []
    for v in source_id_values(source_msg_ids):
        n = as_msg_id(v)
        if n is not None:
            ids.append(n)
    if not ids:
        raise RecordError("提升必须有来源消息（source_msg_ids 不能为空）")
    miss = [x for x in ids if x not in _batch_ids(batch_msgs)]
    if miss:
        raise RecordError("来源 id %s 不在本批消息里，无法提升" % miss)

    cur["source_msg_ids"] = ids
    cur["quarantined"] = False
    cur["needs_review"] = True         # 提升后仍需人看一眼
    if str(time_raw or "").strip():
        cur["time_raw"] = str(time_raw).strip()
    if anchor is not None:
        cur["time_anchor_msg_id"] = anchor
    out, notes = validate(cur, batch_msgs)
    out["quarantined"] = False
    out["gate_state"] = new_gate
    notes.append("隔离记录 %s 已补上来源 %s 并重新核验（闸门 %s → %s）"
                 % (norm_id(rid), ids, old_gate, new_gate))
    recs[i] = out
    return recs, out, notes


def review_queue(records) -> list[dict]:
    """需要人工看的记录（未归档，且 needs_review 或被隔离）。"""
    return [r for r in active_records(records)
            if r.get("needs_review") or r.get("quarantined")]

