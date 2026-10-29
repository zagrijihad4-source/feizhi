# -*- coding: utf-8 -*-
"""绯栀的长期记忆。

发现的问题（2026-10-16）：每轮只把最近 8 条消息喂给模型，更早的对话对她等于不存在；
而 persona 里却写着她「记得小事，他随口说过的话你都记着」——
人格承诺了一套技术上做不到的能力，于是表现成"记忆非常有限"。

这套记忆分三层：
  1. 工作记忆：最近 N 条原始消息（在 autoreply 里调大 limit）
  2. 事实记忆：关于<OWNER>的稳定信息（工作、作息、喜好、朋友、家人、计划、约定）
  3. 情节记忆：最近发生的事（带日期的一句话）

2、3 由模型从新对话里抽取（节流：够多新消息 + 够长时间才跑一次），
落盘 state/feizhi_memory.json，每轮渲染成一段注入 system prompt。
"""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import memrec as R
from extraction_schema import InvalidExtractionShape, validate_extraction

LOG = logging.getLogger("feizhi_pc.memory")


class MemoryLoadError(RuntimeError):
    """记忆文件读取失败后的保护态：拒绝覆盖原文件。"""


def _strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise ValueError("non_finite_json")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)


def _locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return call

HERE = Path(__file__).resolve().parent
DEFAULT_PATH = HERE / "state" / "feizhi_memory.json"

MAX_FACTS = 60
MAX_EVENTS = 40
# 隔离区自己的上限：隔离项不进召回，但也不能无限堆积
MAX_QUARANTINE = 200
# 容量挤掉时的归档原因。**自动归档与手动归档语义不同**：
# 自动归档只是"放不下"，那件事仍然真实发生过，重放时必须仍被去重挡住；
# 手动归档是"她忘掉了"，才有资格被重新记起来。
AUTO_ARCHIVE_REASON = "超出上限，自动归档"

# 北京时间（UTC+8）。微信消息的 sent_at_ms 是 epoch 毫秒，不带时区。
BEIJING = timezone(timedelta(hours=8))


def fmt_msg_time(sent_at_ms) -> str:
    """把 sent_at_ms 转成北京时间字符串。

    ★ 缺失或非法时返回「未知」，**绝不用抽取当天补造** ——
      补一个假日期会让「昨天/明天」的换算整段错掉，比承认不知道更糟。
    """
    try:
        v = int(sent_at_ms)
    except (TypeError, ValueError):
        return "未知"
    if v <= 0:
        return "未知"
    try:
        return datetime.fromtimestamp(v / 1000, tz=BEIJING).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return "未知"


def _salvage_json(s: str) -> str:
    """从**被截断**的模型输出里抢救出完整的条目。

    ★ 实测（2026-10-26 真实小样本 A 批）：提示词从 2 字段改成 5 字段后输出变长，
      `max_tokens=700` 把 JSON 从中间截断（最后停在 `"time_anchor_msg_id":`），
      `json.loads` 整批失败 → **一条记忆都存不下来**。
      这种失败是静默的：看起来只是"这轮没抽到东西"。
    """
    i = s.rfind("}")
    while i > 0:
        cand = s[:i + 1]
        for tail in ("]}", "]", ""):
            try:
                json.loads(cand + tail)
                return cand + tail
            except Exception:  # noqa: BLE001
                continue
        i = s.rfind("}", 0, i)
    return s


EXTRACT_SYSTEM = """你是「绯栀」这个角色的记忆管理员。
下面是绯栀和她男朋友<OWNER>最近的一段对话。请从里面抽出**她以后聊天会用得上**的信息：

1. facts —— 现阶段**持续有效**的属性、关系、偏好、长期状态，或**明确的周期安排**。
2. events —— **某次**经历、行动，或**一次**安排。
   **绯栀自己主动说的话、她主动提起的事也要记**（她自己会记得"我那天跟他说过什么"），
   写成"绯栀跟他说……""绯栀提到……"。这是她的记忆，不只是关于<OWNER>的资料。

★★ 先定 kind，再**单独**定 certainty —— 这是两件不同的事，不要互相暗示。

  facts  = 现阶段持续有效的属性、关系、偏好、长期状态或明确周期安排。
           它们**可以被后续更新**，并不是永不改变。
  events = 某次经历、行动或一次安排。**即使日期完全未知，也仍然是 event。**

  ★ 分类依据只有一条：**来源表达的适用范围**（原话把这件事限定在哪一段）。
    日期是否出现、是否写成引述、certainty 高低，**都不能单独决定分类**。

    例：
      「每周三下午有课」「生日是 3 月 2 日」  → facts（说的是周期性/固定安排）
      「他今天有早八」「上次用 AI 列过提纲」  → events（说的是某一次）
      「他这学期每周三有早八」               → facts（周期性安排）

  ★ 注意：程序后续会把正文里的时间词移走或改写成日期，
    **你不能因为看到的短句里没有时间词，就认为这条信息不受时间限定** ——
    要回到来源原文判断它限定的范围有多大。

  certainty 问的是「我对**忠实于原话**有多大把握」，与 kind 完全无关：
    **单次事件也可以是 high** —— 他明确说了「我明天9点有课」，那就是 high 的 event。
    **稳定事实也可以是 mid** —— 只有间接线索时。
    不要用 certainty 去暗示稳定性，也不要用 kind 去暗示把握。

★★ 写入政策：先问「这是不是对方**自己说过或确认过**的」，再问「范围有多大」。

  1) 对方自己说过或明确确认、且没被纠正
     → **忠实保留他的原意和范围**，certainty = high。
     · 「我每天画画」是他自己说的频率 → 可以写「绯栀说自己每天画画」；
       这里的 high 意思是**"我确定他这样说过"**，不是"系统验证了这是客观事实"。
     · 「明天会交材料」是计划 → 照记计划，不要改写成习惯，也别因为带「会」就降级；
       但正文仍不写时间词：写「<OWNER>要交材料」，time_raw 填「明天」。
     · 引述时原话里的频率词（每天/经常/总是）**可以保留** —— 你是在引述，不是替他归纳。

  2) 你自己从情境里推的
     → 只限**这一次**发生在这段对话里的情境，certainty = mid。
     不得升级成身份或长期规律，**不得伪装成对方说过的话**。
     例：他今天加班到十点 → text 写「<OWNER>加班到十点」，
         time_raw 填「今天」，time_anchor_msg_id 填说这句话的那条消息。

  3) 身份 / 长期规律（学生、学美术、常熬夜、每天画）
     → 只有**直接证据**才写，而且只有两种：
        · 对方自己说过（那就属于第 1 类，按引述写；「他是学生」只有他真说过才能写成断言）
        · 同一类事情在**不同时间**被**多次独立观察到**（不同天发生的不同事件）
     ★ 同一次事件被多条消息反复提到，**只算一次**，不算"多次证据"。
       同一次作业聊十条消息，仍然只有一次作业。
     ★ 即使确有多次独立观察，也只能写你**观察到的范围**，
       **不能**改写成「她说自己经常……」—— 除非她确实说过这个意思。
     ★ 证据不足 → 只记具体那一次，或者干脆不写这一条。

★ 关于时间（很重要）：**不要换算日期，也不要在正文里写日期**。
  - 每条对话前面标了 `#消息ID [北京时间] 角色：正文`。
  - 「昨天/明天/后天」这类说法，**原样抄**进 time_raw，并用 time_anchor_msg_id
    指明是**哪条消息**说的。相对时间以那条消息的发送时间为基准 ——
    **换算是程序的事，不是你的**。
  - 原文写了「10月26日」「2025年11月2日」这类具体日期，也**原样抄**进 time_raw。
  - 你自己写出来的任何日期都会被程序丢掉或改写，所以别费劲算。
  - 已有记忆里标了「入库日」的，那是**这条记忆被记录下来的日期**，
    **不是事情发生的日期**，不要拿它当事件时间。

规则：
- 只记具体的、以后能复用的信息；寒暄、语气词、一次性的情绪宣泄不算
- 每条不超过 40 字，主语要写清是<OWNER>还是绯栀
- ★ 正文里**不要出现任何日期或相对时间**（既不写「明天」，也不写「10月20日」）。
  时间信息只放 time_raw，由程序换算后统一维护。
- ★ 正文里**不要出现你自己归纳的频率/倾向词**（总是 / 经常 / 习惯 / 老是 / 会……）。
  例外：第 1 类里**引述对方原话**时可以保留这些词（「绯栀说自己每天画画」）。
- ★ 第 2、3 类一律写"发生了什么 / 他她说过什么"，把不确定性留在字面上；
  只有第 1 类才可以写"是什么"的断言。
- 已经在「她记得的」里出现过的，不要再记；同一件事换个说法也算重复
- 没有值得记的就返回空数组
- ★ 每条都要标**把握程度** certainty，它表示**你对"忠实于原话"的把握**，
  不是"这件事客观上有多真"：
    high = 对方自己说过或确认过，且没被纠正
    mid  = 你从情境里推出来的，或只有间接线索
    low  = 你自己也记不太准的（语音没听清、说得含糊、隔了很久才想起）
    不许为了"看起来确定"而写 high。
- 只输出一个 JSON 对象，不要解释、不要代码块：
{"facts": [{"text": "...", "certainty": "high", "source_msg_ids": [517],
            "time_raw": "后天", "time_anchor_msg_id": 517}],
 "events": [{"text": "...", "certainty": "mid", "source_msg_ids": [518, 519],
            "time_raw": "", "time_anchor_msg_id": null}]}

★ 五个字段的含义，缺一不可：
  text                一句话说清这条记忆。**不含任何日期/相对时间**；
                      也不含你自己归纳的「总是/经常/习惯/会」（引述原话除外）。
  certainty           high / mid / low（含义见上：忠实于原话的把握，不是客观真实性）
  source_msg_ids      这条记忆是从哪几条对话看出来的，填 `#` 后面的数字。
                      **必填、至少一条**，且只能填上面真实出现过的消息 ID。
                      填错或留空，这条记忆会被隔离、不会进入她的记忆。
  time_raw            这件事的时间在原话里怎么说，**原样抄**：
                      明天 / 后天 / 10月26日 / 去年11月2日 …；没有就填 ""。
  time_anchor_msg_id  当 time_raw 是「明天/后天」这类相对说法时，填**说出这句话**
                      的那条消息 ID；不是相对说法就填 null。
"""

RENDER_TEMPLATE = """【你真正记得的事 —— 这不是设定，是你自己攒下来的记忆】
{body}
用法：像真人一样自然地想起来就用，别一次全倒出来，也别复述成清单；
他提到相关的事时你自然会接上。没把握的细节不要编，宁可说记不清。
标了「可能记岔」「不太确定」的，说的时候要带「好像」「我记得是」这种口气，
并且允许他纠正你 —— 真人的记忆本来就不是数据库。"""


def _norm(s: str) -> str:
    """粗粒度归一化，用于去重。

    ★ 不再截断（审查 R12）：原来只取前 16 个归一化字符，
      两条开头相同的事实（"他说这周末要回家…" / "他说这周末要回家看爸妈…"）
      会被判成重复，第二条直接丢掉。现在用完整内容做键。
    """
    return re.sub(r"[\s，。、！？,.!?~～]+", "", str(s))


def _dedupe_key(rec: dict, kind: str) -> str:
    """「是不是同一件事」的判定键。

    * **fact（稳定事实）**：纯正文。同一事实换说法或重复提交都算同一条。
    * **event（发生过的事）**：正文 + **结构化日期**。
      ★ 新契约要求正文不写日期，只比正文会把不同日期的事件合并成一件 ——
        实测：来源分别说「10月16日去医院抽血」和「11月16日又去医院抽血」，
        程序算出了两个不同日期，第二条仍被判「重复跳过」，直接丢失。
      日期取不到时退回来源集合：同一条消息重放算重复，不同消息不合并。
    """
    t = _norm(rec.get("text") or "")
    if kind == "fact":
        return t
    et = str(rec.get("event_time") or "").strip()
    if et:
        return t + "|" + et
    ids = []
    for i in R.source_id_values(rec.get("source_msg_ids")):
        value = R.as_msg_id(i)
        if value is not None:
            ids.append(value)
    return t + "|" + ",".join(str(i) for i in sorted(ids))


class FeizhiMemory:
    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.data = self._load()

    # ---------- 存储 ----------
    def _load(self) -> dict:
        """读取记忆文件。

        ★ 读失败**绝不能**静默退回空库：那样下一次 save() 会把原文件直接覆盖掉，
          用户攒下的全部记忆就没了。这里备份原文件、置 `_load_error`，
          之后 save() 会拒绝写入（除非调用方显式 override）。
        """
        self._load_error = ""
        if self.path.exists():
            try:
                d = _strict_json(self.path.read_text(encoding="utf-8"))
                if not isinstance(d, dict):
                    raise ValueError("memory_top_level_not_object")
                for bucket in ("facts", "events"):
                    items = d.get(bucket, [])
                    if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
                        raise ValueError("invalid_memory_bucket:" + bucket)
                    if any("text" in x and not isinstance(x["text"], str) for x in items):
                        raise ValueError("invalid_memory_text:" + bucket)
                for counter in ("last_id", "last_mid"):
                    value = d.get(counter, 0)
                    if type(value) is not int or value < 0:
                        raise ValueError("invalid_memory_counter:" + counter)
                stamp = d.get("last_extract_ts", 0.0)
                if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0:
                    raise ValueError("invalid_memory_timestamp")
                d.setdefault("facts", [])
                d.setdefault("events", [])
                d.setdefault("last_id", 0)
                d.setdefault("last_mid", 0)
                d.setdefault("last_extract_ts", 0.0)
                return d
            except Exception as e:  # noqa: BLE001
                self._load_error = "%s: %s" % (type(e).__name__, e)
                LOG.error("记忆文件读取失败，进入保护模式（不自动覆盖）：%r", e)
                try:
                    bak = self.path.with_name(
                        self.path.name + ".corrupt-%s-%s" % (
                            time.strftime("%Y%m%d%H%M%S"), uuid.uuid4().hex))
                    shutil.copy2(self.path, bak)
                    LOG.error("原文件已备份到 %s", bak)
                except Exception as e2:  # noqa: BLE001
                    LOG.error("备份失败（更要谨慎覆盖）：%r", e2)
        return {"facts": [], "events": [], "last_id": 0, "last_mid": 0,
                "last_extract_ts": 0.0}

    def _require_writable(self) -> None:
        if getattr(self, "_load_error", ""):
            raise MemoryLoadError("记忆加载失败，保护态禁止修改或抽取；先人工恢复并重新加载。")

    @contextmanager
    def _mutation(self):
        """Build privately, persist once, then publish the committed data.

        Public readers continue to see the old data until replace succeeds.
        Private _ingest/_add remain batch-building helpers, not commit APIs.
        This is single-instance synchronization, not an interprocess protocol.
        """
        with self._lock:
            self._require_writable()
            work = copy.copy(self)
            work.data = copy.deepcopy(self.data)
            yield work
            if work.data != self.data or not self.path.exists():
                # Detach all references returned by the mutation before saving.
                # A caller must not be able to edit committed memory through a
                # returned record or one of its nested source-ID lists.
                work.data = copy.deepcopy(work.data)
                work.save()
                self.data = work.data

    @_locked
    def save(self, *, override_load_error: bool = False) -> None:
        if getattr(self, "_load_error", "") and not override_load_error:
            raise MemoryLoadError(
                "记忆文件此前读取失败（%s），拒绝覆盖。"
                "请先人工检查并修复文件，或显式 override_load_error=True。"
                % self._load_error)
        payload = json.dumps(self.data, ensure_ascii=False, indent=2, allow_nan=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        tmp = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            tmp.replace(self.path)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError as exc:
                LOG.warning("临时记忆文件清理失败：%s", type(exc).__name__)

    # ---------- 查询 ----------
    @_locked
    def facts(self) -> list[dict]:
        return copy.deepcopy(self.data.get("facts", []))

    @_locked
    def events(self) -> list[dict]:
        return copy.deepcopy(self.data.get("events", []))

    @_locked
    def stats(self) -> dict:
        facts, events = self.facts(), self.events()
        live = [x for x in facts + events if not x.get("archived")]
        return {"facts": sum(1 for x in facts if not x.get("archived")),
                "events": sum(1 for x in events if not x.get("archived")),
                "archived": len(facts) + len(events) - len(live),
                "quarantined": sum(1 for x in live if x.get("quarantined")),
                "needs_review": sum(1 for x in live if x.get("needs_review")),
                "last_id": self.data.get("last_id", 0),      # 消息抽取水位
                "last_mid": self.data.get("last_mid", 0),    # 记忆编号序列
                "last_extract": time.strftime("%Y-%m-%d %H:%M:%S",
                                              time.localtime(self.data.get("last_extract_ts", 0)))
                if self.data.get("last_extract_ts") else None}

    # 把握程度 → 说话口气。真人对记不准的事会含糊，不会当成铁的事实。
    _CERT_HINT = {"mid": "（记得是这样，可能记岔）",
                  "low": "（好像是这样，不太确定）"}

    @staticmethod
    def _stamp(x: dict) -> str:
        """原话的发送日期。取不到返回空 —— **绝不用入库日顶替**。"""
        try:
            v = int(x.get("time_raw_at_ms"))
        except (TypeError, ValueError):
            return ""
        if v <= 0:
            return ""
        try:
            return datetime.fromtimestamp(v / 1000, tz=BEIJING).strftime("%Y-%m-%d")
        except (OSError, OverflowError, ValueError):
            return ""

    @_locked
    def render(self) -> str:
        """渲染成注入 system prompt 的一段。没东西可记就返回空串。

        只读 `recallable`：归档（她已忘掉）与隔离（来源不明，未核验）都不进 prompt。

        ★ 两种时间都要渲染，且不能混：
          * **已核验的事件日期**（`event_time`）必须出现在召回文本里。
            新契约下正文不再写日期，不渲染就等于把核验结果白算
            （实测 render 只剩「<OWNER>要上课」，模型根本不知道是哪天）。
          * **原话的发送时间**（`time_raw_at_ms`）用来锚住「本周末」这类说法。
            它取不到就明说未知 —— 绝不能用入库日 `created` 冒充，
            那会把「10-15 说的本周末」渲染成「记于 10-26」。
        """
        def line(x: dict) -> str:
            t = str(x.get("text", ""))
            cert = self._CERT_HINT.get(str(x.get("certainty") or ""), "")
            et = x.get("event_time")
            raw = str(x.get("time_raw") or "").strip()
            shown = R.disp_date(et) if et else ""
            if et:
                extra = ""
                if shown and shown not in t and str(et) not in t:
                    extra = "（%s）" % shown
                if x.get("needs_review"):
                    extra += "（这条的时间我可能记岔）"
                return "- " + t + extra + cert
            if raw:
                stamp = self._stamp(x)
                when = ("%s 说的" % stamp) if stamp else "原话时间未知"
                return "- " + t + "（原话「%s」，%s）" % (raw, when) + cert
            if x.get("needs_review"):
                return "- " + t + "（这条我记不太准）" + cert
            return "- " + t + cert

        live = [x for x in R.recallable(self._view()) if x.get("text")]
        f = [line(x) for x in live if x.get("kind") != "event"]
        e = [line(x) for x in live if x.get("kind") == "event"][-12:]
        if not f and not e:
            return ""
        parts = []
        if f:
            parts.append("关于<OWNER>：\n" + "\n".join(f[-30:]))
        if e:
            parts.append("最近这些天：\n" + "\n".join(e))
        return RENDER_TEMPLATE.format(body="\n\n".join(parts)) + "\n"

    # ---------- 写入 ----------
    @_locked
    def render_existing(self) -> str:
        """给**抽取器**看的已有记忆全量（不是给聊天用的 render）。

        与 `render()` 的区别：
          * 这里是**全部** facts + events（抽取时需要它来判断重复/更新），
            不是 `facts[-30:]` + `events[-12:]`。
          * 每条带类型标识、certainty，以及 `added`（**入库日期**）。
            必须显式声明 added 不是事件发生日期，否则模型会把它当成时间。

        实测（2026-10-25）：原实现只喂 `facts()[-30:]`、且完全看不到 events，
        导致模型没有依据判断"这条是不是已经记过" —— 这是重复入库的直接成因。
        """
        facts = [x for x in R.recallable(self._view()) if x.get("kind") != "event"]
        events = [x for x in R.recallable(self._view()) if x.get("kind") == "event"]
        if not facts and not events:
            return "（还什么都没记）"

        def line(prefix: str, i: int, x: dict) -> str:
            parts = ["%s%02d" % (prefix, i), str(x.get("text", ""))]
            if x.get("certainty"):
                parts.append("把握=%s" % x["certainty"])
            d = x.get("created") or x.get("added")
            if d:
                parts.append("入库日=%s" % d)
            return "｜".join(parts)

        out = []
        if facts:
            out.append("【已有事实】（%d 条）" % len(facts))
            out += [line("F", i, x) for i, x in enumerate(facts, 1)]
        if events:
            out.append("【已有事件】（%d 条）" % len(events))
            out += [line("E", i, x) for i, x in enumerate(events, 1)]
        out.append("（说明：「入库日」是这些记忆**被记录下来的日期**，"
                   "不是事情发生的日期，不要拿它当事件时间。"
                   "上面已经是全部已有记忆，新增前请先确认是否只是同一件事的另一种说法。）")
        return "\n".join(out)

    def migrate(self) -> dict:
        """旧格式（无 id、只有 added）→ 新结构。**幂等**：已有 id 的一律不动。

        必须在任何 CRUD 之前跑一次：没有 id 的记录 `_locate` 定位不到。
        只补结构字段，**不补造来源**（source_msg_ids 留空），
        也**不把 added 当成事件时间** —— 那是入库日，不是事情发生的日子。

        ★ 记忆编号用 `last_mid`，**绝不碰 `last_id`**。
          `last_id` 是**消息抽取水位**（store 里消息 id 的推进点），
          两者共用一个键会让迁移把尚未抽取的消息直接跳过（实测：
          生产副本迁移后水位 510→606，消息 511-519 全部漏抽）。
        """
        with self._mutation() as work:
            mid = int(work.data.get("last_mid", 0))
            today = time.strftime("%Y-%m-%d")
            touched = 0
            for b, kind in (("facts", "fact"), ("events", "event")):
                for x in work.data.get(b, []):
                    if not isinstance(x, dict):
                        continue
                    if not x.get("id"):
                        mid += 1
                        x["id"] = "m%04d" % mid
                        touched += 1
                    x.setdefault("kind", kind)
                    x.setdefault("created", x.get("added") or today)
                    x.setdefault("source_msg_ids", [])
                    x.setdefault("speaker", "")
                    x.setdefault("event_time", None)
                    x.setdefault("time_basis", R.TB_UNKNOWN)
                    x.setdefault("time_raw", "")
                    x.setdefault("time_anchor_msg_id", None)
                    x.setdefault("time_raw_at_ms", None)
                    x.setdefault("needs_review", False)
                    x.setdefault("gate_state", "legacy")
                    x.setdefault("archived", False)
                    x.setdefault("archived_at", "")
                    x.setdefault("archive_reason", "")
            work.data["last_mid"] = mid
            return {"touched": touched, "last_mid": mid,
                    "last_id": int(work.data.get("last_id", 0)),
                    "total": len(work.data.get("facts", []))
                    + len(work.data.get("events", []))}

    def _trim(self, kind: str, limit: int) -> int:
        """超出上限时把最旧的**可召回**记录归档 —— 绝不物理删除。

        ★ 配额只算「未归档且未隔离」的。隔离项不参与召回，如果把它们也计入
          配额，加一条隔离 event 就会把一条**有效** event 挤掉
          （实测：有效事件 40 → 39，且被自动归档）。
        """
        bucket = self.data.setdefault(kind, [])
        # ★ 配额只算**可召回**的：未归档、未隔离、且闸门放行（eligible/legacy）。
        #   隔离项和 pending/rejected 都不参与召回，把它们计入配额
        #   会让"加一条待复核"直接归档掉一条有效记忆（实测可复现）。
        live = [x for x in bucket
                if not x.get("archived") and not x.get("quarantined")
                and R.gate_of(x) in R.GATE_OPEN]
        over = len(live) - limit
        if over <= 0:
            return 0
        today = time.strftime("%Y-%m-%d")
        for x in live[:over]:
            x["archived"] = True
            x["archived_at"] = today
            x["archive_reason"] = AUTO_ARCHIVE_REASON
        return over

    def _trim_quarantine(self, kind: str, limit: int = MAX_QUARANTINE) -> int:
        """隔离区自己的上限：超了归档最旧的隔离项（仍不物理删除）。"""
        bucket = self.data.setdefault(kind, [])
        q = [x for x in bucket
             if x.get("quarantined") and not x.get("archived")]
        over = len(q) - limit
        if over <= 0:
            return 0
        today = time.strftime("%Y-%m-%d")
        for x in q[:over]:
            x["archived"] = True
            x["archived_at"] = today
            x["archive_reason"] = "隔离区超上限，归档"
        return over

    def _add(self, kind: str, texts: list, limit: int) -> int:
        """texts 元素可以是纯字符串，也可以是 {"text","certainty"} —— 两种都接。"""
        bucket = self.data.setdefault(kind, [])
        # 去重只跟**未归档**的比：她"忘掉"的事可以重新记一次
        have = {_norm(x.get("text", "")) for x in bucket if not x.get("archived")}
        added = 0
        today = time.strftime("%Y-%m-%d")
        for it in texts:
            if isinstance(it, dict):
                t = str(it.get("text") or "").strip()
                cert = str(it.get("certainty") or "").strip().lower()
            else:
                t = str(it).strip()
                cert = ""
            if not t or _norm(t) in have:
                continue
            mid = int(self.data.get("last_mid", 0)) + 1
            self.data["last_mid"] = mid
            rec = {"id": "m%04d" % mid,
                   "kind": "fact" if kind == "facts" else "event",
                   "text": t, "added": today, "created": today,
                   "source_msg_ids": [], "speaker": "", "event_time": None,
                   "time_basis": R.TB_UNKNOWN, "time_raw": "",
                   "time_anchor_msg_id": None, "needs_review": False,
                   "archived": False, "archived_at": "", "archive_reason": ""}
            if cert in ("high", "mid", "low"):
                rec["certainty"] = cert
            bucket.append(rec)
            have.add(_norm(t))
            added += 1
        self._trim(kind, limit)
        return added


    # ---------- CRUD（给抽取端与人工维护用） ----------
    @_locked
    def _view(self) -> list[dict]:
        """facts + events 的统一视图（拷贝，按入库日升序）。

        ★ **按原桶补齐 `kind`**：未迁移的旧记录既没有 `kind` 也没有 `id`，
          只靠 id 认桶覆盖不到它们；少了这一步，`kind != "event"` 对它们恒真，
          96 条会全被判成 fact（实测：`render()` 只剩 30 条旧 events，
          事实记忆被挤出窗口；新增一条 fact 后存储变成 facts 97 / events 0，
          并连带自动归档 37 条）。

        ★ 排序键是**入库日**（`created`/`added`），不是 `id`。
          `id` 是发号顺序，与时间线并不一致：`migrate()` 给 legacy 记录补
          `m0010..` 的号，而早已存在的 `m0001..m0009` 是最新那批 ——
          按 id 排会把最新记录顶到最前，`render()` 取 `events[-12:]`
          就取到十天前的事。实测（2026-10-27 副本）：迁移后 9 条 10-27 的
          事件被 10-19~10-22 的挤掉，「让他别光甩链接」「配色确实有点脏」
          全部消失。改成按入库日后，迁移前后 `render()` 输出完全一致。
          用稳定排序，同一天内保持原桶顺序。
        """
        out = []
        for b in ("facts", "events"):
            kind = "fact" if b == "facts" else "event"
            for x in self.data.get(b, []):
                if isinstance(x, dict):
                    d = copy.deepcopy(x)
                    if not d.get("kind"):
                        d["kind"] = kind
                    out.append(d)
        out.sort(key=lambda x: str(x.get("created") or x.get("added") or ""))
        return out

    def _replace_all(self, recs: list[dict]) -> None:
        """把统一视图按原桶写回，保持各自相对顺序。

        ★ 桶归属靠**已有记录的 id**（而不是 `kind` 字段）判断：
          未迁移的旧记录可能没有 `kind`，若按 kind 分桶会把整批 facts 塞进 events。
        """
        bucket_of = {}
        for b in ("facts", "events"):
            for x in self.data.get(b, []):
                if isinstance(x, dict) and x.get("id"):
                    bucket_of[str(x["id"])] = b
        facts, events = [], []
        for x in recs:
            b = bucket_of.get(str(x.get("id") or ""))
            if b not in ("facts", "events"):
                b = "facts" if x.get("kind") != "event" else "events"
            (facts if b == "facts" else events).append(x)
        self.data["facts"] = facts
        self.data["events"] = events

    def _locate(self, rid) -> tuple[str, int]:
        want = R.norm_id(rid)
        for b in ("facts", "events"):
            for i, x in enumerate(self.data.get(b, [])):
                if str(x.get("id") or "") == want:
                    return b, i
        raise R.RecordError("没有 id=%s 的记录" % want)

    def add_record(self, rec: dict, batch_msgs: list[dict],
                   *, gate_state: str = "legacy") -> dict:
        """新增一条**经过校验**的记录（抽取端入口，不接受自报 manual）。

        `gate_state`：来源闸门状态。默认 `legacy` 表示"未经闸门的普通写入"；
        v1.3 闸门接线时必须显式传 `eligible`（已放行）或 `pending`（等复核）。
        """
        with self._mutation() as work:
            recs, stored, notes, last = R.add_record(
                work._view(), rec, batch_msgs, work.data.get("last_mid", 0),
                gate_state=gate_state)
            work._replace_all(recs)
            work.data["last_mid"] = last
            work._trim("facts" if stored.get("kind") == "fact" else "events",
                       MAX_FACTS if stored.get("kind") == "fact" else MAX_EVENTS)
            return {"record": stored, "notes": notes}

    def add_manual_record(self, rec: dict, batch_msgs: list[dict],
                          *, reason: str = "", gate_state: str = "legacy") -> dict:
        """人工新增带指定日期的记录（唯一合法的 manual 入口，必须给 reason）。"""
        with self._mutation() as work:
            recs, stored, notes, last = R.add_manual_record(
                work._view(), rec, batch_msgs, work.data.get("last_mid", 0),
                reason=reason)
            if gate_state != "legacy":
                # 让闸门侧也能给人工新增的记录指定状态
                idx = R.find_index(recs, stored["id"])
                if idx >= 0:
                    recs[idx]["gate_state"] = gate_state
                    stored["gate_state"] = gate_state
            work._replace_all(recs)
            work.data["last_mid"] = last
            work._trim("facts" if stored.get("kind") == "fact" else "events",
                       MAX_FACTS if stored.get("kind") == "fact" else MAX_EVENTS)
            return {"record": stored, "notes": notes}

    def update_record(self, rid, changes: dict, batch_msgs: list[dict] | None = None,
                      *, reason: str = "") -> dict:
        """改一条记录。改时间必须给 reason（会转成 manual 并永久待复核）。"""
        with self._mutation() as work:
            recs, before, after, notes = R.patch_record(
                work._view(), rid, changes, batch_msgs, reason=reason)
            work._replace_all(recs)
            return {"before": before, "record": after, "notes": notes}

    def archive_record(self, rid, reason: str = "") -> dict:
        """归档 = 她已经忘掉这件事（逻辑删除，保留全部溯源信息）。"""
        with self._mutation() as work:
            recs, rec = R.archive_record(work._view(), rid, reason)
            work._replace_all(recs)
            return rec

    def restore_record(self, rid) -> dict:
        with self._mutation() as work:
            recs, rec = R.restore_record(work._view(), rid)
            work._replace_all(recs)
            return rec

    @_locked
    def review_queue(self) -> list[dict]:
        """需要人工过一眼的记录（时间被改过、日期无依据、来源不明的隔离项等）。"""
        return R.review_queue(self._view())

    @_locked
    def _ingest(self, kind: str, items: list,
                batch_msgs: list[dict], gate_state: str = "pending",
                trim: bool = True
                ) -> tuple[int, int, int, list]:
        """抽取结果逐条走**校验入口**（不再走 `_add` 的裸写入）。

        * 来源为空或无效 → 进**隔离区**（quarantined）：不入召回、进待复核，
          但记录保留。既不认模型凭空编的东西影响回复，也能事后查它编了什么。
        * 同一文本已有**隔离**记录、这次来源有效 → **提升**那条，
          不再新建重复记录。
        * 去重只与**可召回**记录比：隔离项不得挡住有效写入
          （实测旧逻辑里「先隔离、后有效」会一直被"重复跳过"，
          结果是永远没有可召回记录）。
        * 单条失败不拖垮整批。

        返回 (正常生效数, 隔离数, 提升数, 说明列表)。
        """
        self._require_writable()
        bucket_kind = "fact" if kind == "facts" else "event"
        # ★ 调用方传 None/空/非法值都收敛成 pending，不继承、不放行
        gate_state = R.normalize_gate(gate_state, "pending")
        view = self._view()
        recall_have = {_dedupe_key(x, x.get("kind") or bucket_kind)
                       for x in R.recallable(view)}
        # ★ 自动归档（容量挤掉）的记录**仍参与去重**：那件事真实发生过，
        #   只是暂时放不下。少了这一步，重放同一批会把归档的记录重新写一遍
        #   （实测：重放 81 → 121 条，翻了一倍多）。
        #   手动归档（"她忘掉了"）不参与去重，允许重新记起来。
        recall_have |= {_dedupe_key(x, x.get("kind") or bucket_kind)
                        for x in view
                        if x.get("archived")
                        and str(x.get("archive_reason") or "") == AUTO_ARCHIVE_REASON}
        # ★ 同一闸门状态下重放必须幂等：pending 重放 pending 不能长出第二条。
        #   但**跨闸门**不能去重 —— pending 记录遇到 eligible 输入要允许提升/新建
        #   （否则「先隔离、后有效」永远进不了召回）。
        #   隔离项（quarantined）**必须排除在外**：它们要靠提升分支处理，
        #   被去重挡住的话提升永远走不到（实测：W9 四项断言全挂）。
        recall_have |= {_dedupe_key(x, x.get("kind") or bucket_kind)
                        for x in view
                        if not x.get("archived")
                        and not x.get("quarantined")
                        and R.gate_of(x) == gate_state}
        quar = {}
        for x in R.active_records(view):
            if x.get("quarantined"):
                quar.setdefault(_dedupe_key(x, x.get("kind") or bucket_kind), x)
        ok_n, q_n, p_n, fails = 0, 0, 0, []
        for it in items:
            if isinstance(it, dict):
                t = str(it.get("text") or "").strip()
                cert = str(it.get("certainty") or "").strip().lower()
                src_ids = it.get("source_msg_ids") or []
                time_raw = str(it.get("time_raw") or "").strip()
                anchor = it.get("time_anchor_msg_id")
            else:
                t, cert, src_ids, time_raw, anchor = str(it).strip(), "", [], "", None
            if not t:
                continue
            rec = {"kind": bucket_kind, "text": t,
                   "certainty": cert if cert in ("high", "mid", "low") else "",
                   "source_msg_ids": src_ids, "time_raw": time_raw,
                   "time_anchor_msg_id": anchor}
            # ★ 去重必须比较**校验规范化之后**的正文（+ 事件的结构化日期）。
            #   模型给「<OWNER>明天交材料」，规范化后是「<OWNER>10月16日交材料」；
            #   拿裸输入去比，两次相同的模型输出会重复入库（实测）。
            #   而只比正文又会把「10月16日抽血」和「11月16日抽血」合并（实测）。
            try:
                norm_rec, _n = R.validate(dict(rec), batch_msgs)
                nkey = _dedupe_key(norm_rec, bucket_kind)
            except Exception:  # noqa: BLE001
                nkey = _dedupe_key(rec, bucket_kind)
            if nkey in recall_have:
                fails.append("重复跳过：%s" % t[:18])
                continue
            if nkey in quar:
                qrec = quar[nkey]
                try:
                    recs, stored, notes = R.promote_quarantined(
                        self._view(), qrec["id"], src_ids, batch_msgs,
                        time_raw, anchor, gate_state=gate_state)
                except R.RecordError as e:
                    fails.append("隔离项仍无法提升（%s）：%s"
                                 % (str(e)[:20], t[:14]))
                    continue
                self._replace_all(recs)
                recall_have.add(nkey)
                quar.pop(nkey, None)
                p_n += 1
                continue
            quarantined = False
            try:
                recs, stored, notes, mid = R.add_record(
                    self._view(), rec, batch_msgs, self.data.get("last_mid", 0),
                    gate_state=gate_state)
            except R.RecordError as e:
                rec["quarantined"] = True
                try:
                    recs, stored, notes, mid = R.add_record(
                        self._view(), rec, batch_msgs,
                        self.data.get("last_mid", 0), require_sources=False,
                        gate_state=gate_state)
                    quarantined = True
                    fails.append("隔离（%s）：%s" % (str(e)[:24], t[:14]))
                except R.RecordError as e2:
                    fails.append("丢弃（%s / %s）：%s"
                                 % (str(e)[:16], str(e2)[:16], t[:14]))
                    continue
            self._replace_all(recs)
            self.data["last_mid"] = mid
            # 记进集合的键也用**规范化后**的正文 + 结构化日期，重抽时才对得上
            real_key = _dedupe_key(stored or {"text": t, "source_msg_ids": src_ids},
                                   bucket_kind)
            if quarantined:
                q_n += 1
                quar.setdefault(real_key, stored)
            else:
                ok_n += 1
                recall_have.add(real_key)
        if trim:
            self._trim(kind, MAX_FACTS if kind == "facts" else MAX_EVENTS)
            self._trim_quarantine(kind)
        return ok_n, q_n, p_n, fails

    def add_fact(self, text: str) -> bool:
        with self._mutation() as work:
            n = work._add("facts", [text], MAX_FACTS)
            return bool(n)

    def add_event(self, text: str) -> bool:
        with self._mutation() as work:
            n = work._add("events", [text], MAX_EVENTS)
            return bool(n)

    # ---------- 抽取 ----------
    def maybe_extract(self, store, peer: str, llm,
                      min_new: int = 8, min_interval: float = 1200.0) -> dict:
        """够多新消息、且距上次够久，才让模型抽一次记忆。

        min_interval 默认 20 分钟；抽取失败只记日志，绝不影响回复主流程。
        """
        with self._lock:
            self._require_writable()
        now = time.time()
        if now - float(self.data.get("last_extract_ts", 0)) < min_interval:
            return {"skipped": "too_soon"}
        try:
            rows = store.recent(limit=120)
        except Exception as e:  # noqa: BLE001
            LOG.warning("读历史失败：%r", e)
            return {"skipped": "no_history"}

        last_id = int(self.data.get("last_id", 0))
        fresh = [r for r in rows
                 if r.get("peer_wxid") == peer and (R.as_msg_id(r.get("id")) or 0) > last_id]
        if len(fresh) < min_new:
            return {"skipped": "not_enough_new", "new": len(fresh)}
        # store.recent() 给的是「最新在前」，喂给模型前必须转成时间正序，
        # 否则它会读成倒放（实测第一版就是倒着的）。
        fresh.sort(key=lambda r: R.as_msg_id(r.get("id")))
        # ★ 只处理**实际送进模型**的那批，水位也只推进到这批末尾（审查 R12）。
        #   旧代码送 fresh[-60:]（最后 60 条）却把 last_id 推到第 100 条，
        #   前 40 条就这样永久漏抽了。
        batch = fresh[:60]
        # ★ 每条带「消息 ID / 北京时间 / 角色」：模型靠这个把「昨天/明天」换算成
        #   具体日期。时间缺失或非法时 fmt_msg_time 返回「未知」，
        #   prompt 里已说明「未知就不要猜日期」，绝不用抽取当天补造。
        convo = "\n".join(
            "#%s [%s] %s：%s" % (
                r.get("id", "?"),
                fmt_msg_time(r.get("sent_at_ms")),
                "<OWNER>" if r.get("role") == "user" else "绯栀",
                str(r.get("text", ""))[:800])
            for r in batch)
        # ★ 完整已有记忆（全部 facts + events，含类型/把握/入库日），
        #   而不是原来那句 `facts()[-30:]` —— 后者看不到 events，是重复入库的主因。
        known = self.render_existing()
        user = ("【她记得的】\n%s\n\n【最近的对话】\n%s" % (known, convo))

        try:
            out = llm.chat(EXTRACT_SYSTEM, user, max_tokens=1600, temperature=0.4)
        except Exception as e:  # noqa: BLE001
            LOG.warning("记忆抽取调用失败：%r", e)
            return {"error": "llm"}

        if not isinstance(out, str):
            return {"error": "not_json"}
        facts, events = [], []
        partial = False
        try:
            # ★ 允许输出被截断：从头找到尾，再靠 _salvage_json 救回完整条目
            m = re.search(r"\{.*", out, re.S)
            if not m:
                # ★ 没有 JSON = 失败，绝不能当"空结果"推进水位（审查 R12）
                LOG.warning("记忆抽取返回的不是 JSON：%r", out[:160])
                return {"error": "not_json"}
            body = m.group(0)
            try:
                obj = _strict_json(body)
            except json.JSONDecodeError:
                salvaged = _salvage_json(body)
                if salvaged == body:
                    LOG.warning("记忆抽取输出无法抢救：%r", body[:160])
                    return {"error": "parse"}
                obj = _strict_json(salvaged)      # 救不回来就落到外层 except
                # ★ 只救回一部分 = **整批没抽完**。绝不能当成完整结果。
                partial = True
                LOG.warning("抽取输出被截断，只救回部分条目；本批水位不推进")
            # ★ `{}` 或缺少 facts/events 都算**非法结果**，必须当失败处理：
            #   当成"完整空结果"就会推进水位，那批消息从此永久漏抽（实测可复现）。
            # Compatibility only for genuinely truncated JSON: keep known valid
            # recovered items without consuming the batch. A complete JSON
            # object missing a bucket is never silently completed.
            if partial and isinstance(obj, dict):
                obj = dict(obj)
                obj.setdefault("facts", [])
                obj.setdefault("events", [])
            normalized = validate_extraction(obj, parse_id=R.as_msg_id)
            facts, events = normalized["facts"], normalized["events"]
        except InvalidExtractionShape as exc:
            LOG.warning("抽取结构非法，不修改记忆或水位：%s at %s", exc.code, exc.path)
            return {"error": "invalid_shape"}
        except Exception as e:  # noqa: BLE001
            LOG.warning("记忆抽取解析失败：%r / 原文=%r", e, out[:200])
            return {"error": "parse"}
        with self._mutation() as work:
            if int(work.data.get("last_id", 0)) != last_id:
                return {"skipped": "stale_batch"}
            # ★ 写入走**校验入口**（`_ingest` → `memrec.add_record`），
            #   不再直接 `_add`：`_add` 是无校验的裸写入，留在那里等于
            #   提示词改完了、字段也解析了，最后一步却绕过了全部校验。
            # ★★ 闸门接线（2026-10-28）：新写入一律 pending，再由 approve_pending
            #   做自动审核。旧代码这里硬编码 legacy（注释里作者自己也写着"接入后必须
            #   改成 pending"），等于让闸门整套机制空转 —— pending 不召回、promote
            #   矩阵、来源校验全部绕开，模型编的记忆落地即进 prompt。
            #   实测缺陷：原文只有「辣椒炒肉」，模型写成「<OWNER>中午吃的是辣椒炒肉」，
            #   几天后她拿这句当事实问「你中午不是吃的辣椒炒肉嘛」。
            nf, qf, pf, ffails = work._ingest("facts", facts, batch,
                                              gate_state="pending")
            ne, qe, pe, efails = work._ingest("events", events, batch,
                                              gate_state="pending")
            # 自动放行：只有完全干净的记录能立刻变 eligible，
            # 带复核标记（时段词/日期冲突/多相对词…）的留在 pending 等人看。
            # 这样既不会让她"失忆"，也不会让编出来的东西直接开口说话。
            _appr, _anotes, _asum = R.approve_pending(work._view(), by="auto")
            if _appr is not None:
                work._replace_all(_appr)
                LOG.info("闸门自动放行 %d 条；留 pending %d 条",
                         len(_asum["approved"]), len(_asum["kept"]))
            elif _asum["kept"]:
                LOG.info("闸门：%d 条留在 pending 待复核", len(_asum["kept"]))
            if partial:
                # ★ 被截断的批次**不推进水位、也不更新时间戳**：
                #   推进就等于把丢掉的那部分永久漏抽。
                #   下一轮会重抽同一批，已入库的重复文本由 `_ingest` 去重挡掉，
                #   所以重试不会写重复记录。
                LOG.warning("本批抽取不完整，水位停在 %s，下一轮重抽",
                            work.data.get("last_id", 0))
            else:
                # ★ 只推进到这批的末尾（审查 R12）—— 不是 fresh 的末尾
                work.data["last_id"] = max(R.as_msg_id(r.get("id")) for r in batch)
                work.data["last_extract_ts"] = now
            st = work.stats()
        fails = ffails + efails
        if fails:
            LOG.warning("记忆入库有 %d 条未直接生效：%s", len(fails), "；".join(fails[:6]))
        LOG.info("记忆更新：facts +%d（共 %d），events +%d（共 %d）",
                 nf, st["facts"], ne, st["events"])
        return {"facts_added": nf, "events_added": ne,
                "quarantined_added": qf + qe, "promoted": pf + pe,
                "partial": partial,
                "facts": st["facts"], "events": st["events"],
                "archived": st["archived"], "quarantined": st["quarantined"],
                "needs_review": st["needs_review"], "ingest_fails": fails}


if __name__ == "__main__":
    import sys
    m = FeizhiMemory()
    if len(sys.argv) > 1 and sys.argv[1] == "facts":
        print(json.dumps(m.stats(), ensure_ascii=False, indent=2))
        print(m.render() or "（空）")
    else:
        print(json.dumps(m.stats(), ensure_ascii=False, indent=2))
