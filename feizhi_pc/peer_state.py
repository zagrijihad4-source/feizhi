# -*- coding: utf-8 -*-
"""多用户：每个联系人一套独立状态。

设计原则（2026-10-28 定案）

  **共享** —— 她自己的日子。life 的 projects / mood / last_tick 全进程唯一：
  海报改到第几版、今天困不困、糊糊有没有踩键盘。谁来找她，面对的都是同一份
  现实。A 陪她熬的夜会影响她第二天对 B 的语气 —— 这是对的，真人就是这样。

  **私有** —— 和某个人的关系。memory 的 facts / events，life 的 shared /
  influences / open_loops。全部落在 `state/peers/<wxid>/`，路径硬隔离。

铁律

  私有数据取不到就是取不到，**绝不"退回默认"或"共用一份"**。那种兜底迟早
  会把 A 的秘密渲染进 B 的 prompt 里，而且不会立刻报错，只会让语气变得莫名
  亲密 —— 这是最难查的一类 bug。

路径

  state/
    feizhi_self.json               ← 她的日子（共享）
    peers/<wxid>/memory.json        ← facts / events
    peers/<wxid>/life_private.json  ← shared / influences / open_loops
    peers/<wxid>/relation.json      ← 她怎么称呼这个人、关系档位
    context.sqlite3                 ← 聊天记录，本来就按 peer 分列
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path

from life import FeizhiLife
from memory import FeizhiMemory

LOG = logging.getLogger("feizhi_pc.peers")

HERE = Path(__file__).resolve().parent
STATE_DIR = HERE / "state"
SELF_PATH = STATE_DIR / "feizhi_self.json"

# 关系档位：决定 prompt 用哪一套口吻，也决定"能说什么"。
# 现在只有<OWNER>是 intimate，其他人的抽取和渲染都按 stranger 起步 ——
# 宁可先客气，也不能对陌生人喊"宝宝"。
RELATION_LEVELS = ("stranger", "friend", "intimate")

# 与 bridge.IGNORE_PEERS 同源，这里单独列一份是为了不把 bridge 拖进来
_SYSTEM_PREFIXES = ("newsapp", "filehelper", "floatbottle", "medianote",
                    "weixin", "notifymessage", "gh_", "weixinreminder")


def safe_name(wxid: str) -> str:
    """把 wxid 变成安全的目录名。wxid 本身只含字母数字下划线，这里只做防御。"""
    s = re.sub(r"[^0-9A-Za-z_.@-]", "_", (wxid or "").strip())
    if not s:
        raise ValueError("空的 peer wxid")
    return s[:80]


class Relation:
    """她和一个联系人的关系元数据。

    `relation.json` 缺字段一律按最保守的档位补，**不做"看起来像恋人"的推测**。
    """

    def __init__(self, path: Path, wxid: str):
        self.path = Path(path)
        self.wxid = wxid
        self.data = self._load()

    def _load(self) -> dict:
        d: dict = {}
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                LOG.warning("关系档位读取失败（%s），按保守默认处理：%r",
                            self.path.name, exc)
        level = str(d.get("relation") or "stranger")
        if level not in RELATION_LEVELS:
            LOG.warning("未知关系档位 %r，按 stranger 处理", level)
            level = "stranger"
        return {
            "peer": self.wxid,
            "relation": level,
            "i_call_them": str(d.get("i_call_them") or "").strip(),
            "they_call_me": str(d.get("they_call_me") or "").strip(),
            "since": str(d.get("since") or "").strip(),
            "note": str(d.get("note") or "").strip(),
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(self.path)

    # ---------- 便捷读取 ----------
    @property
    def level(self) -> str:
        return self.data["relation"]

    @property
    def is_intimate(self) -> bool:
        return self.data["relation"] == "intimate"

    def display_name(self, fallback: str = "他") -> str:
        return self.data.get("i_call_them") or fallback


class PeerState:
    """一个联系人的全部私有状态，外加一把串行锁。

    锁的语义：**同一个人的多条消息串行处理**（免得两条回复互相踩上下文），
    不同人可以并发。语音另有全局锁，只能一条一条录。
    """

    def __init__(self, wxid: str, root: Path | str | None = None):
        self.wxid = wxid
        self.root = Path(root) if root else STATE_DIR
        self.dir = self.root / "peers" / safe_name(wxid)
        self.dir.mkdir(parents=True, exist_ok=True)

        self.relation = Relation(self.dir / "relation.json", wxid)
        self.memory = FeizhiMemory(self.dir / "memory.json")
        # 共享层读 feizhi_self.json、私有层落本目录；write_shared=False 保证
        # add_loop / note_answered 只写自己那份，不会覆盖 life tick 的进度。
        self.life = FeizhiLife(SELF_PATH, self.dir / "life_private.json",
                               write_shared=False)
        self.lock = threading.RLock()

    def stats(self) -> dict:
        return {
            "wxid": self.wxid,
            "relation": self.relation.level,
            "memory": self.memory.stats(),
            "shared": len(self.life.data.get("shared") or []),
            "influences": len(self.life.data.get("influences") or []),
            "loops": len(self.life.data.get("open_loops") or []),
        }

    def __repr__(self) -> str:
        return "<PeerState %s %s>" % (self.wxid, self.relation.level)


class PeerRegistry:
    """按需创建 + 线程安全。同一个 wxid 永远拿到同一个 PeerState 实例。"""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else STATE_DIR
        self._states: dict[str, PeerState] = {}
        self._lock = threading.Lock()

    def get(self, wxid: str) -> PeerState:
        key = safe_name(wxid)
        with self._lock:
            st = self._states.get(key)
            if st is None:
                st = PeerState(wxid, self.root)
                self._states[key] = st
                LOG.info("新建联系人状态：%s（%s）", wxid, st.relation.level)
            return st

    def peek(self, wxid: str) -> PeerState | None:
        with self._lock:
            return self._states.get(safe_name(wxid))

    def known(self) -> list[str]:
        with self._lock:
            return sorted(self._states)

    def warm_from_disk(self) -> list[str]:
        """启动时把磁盘上已有的 peer 目录都加载进来（不新建）。"""
        base = self.root / "peers"
        if not base.is_dir():
            return []
        found = []
        for d in sorted(base.iterdir()):
            if not d.is_dir():
                continue
            rel_file = d / "relation.json"
            wxid = ""
            if rel_file.exists():
                try:
                    wxid = str(json.loads(rel_file.read_text(encoding="utf-8"))
                               .get("peer") or "")
                except Exception:  # noqa: BLE001
                    wxid = ""
            if not wxid:
                # 目录名就是 safe_name(wxid)，wxid 只含安全字符时可直接还原
                wxid = d.name
            # 系统会话永远不该有 peer 状态（尽早挡住，别让空壳目录越积越多）
            if any(wxid == t or wxid.lower().startswith(t)
                   for t in _SYSTEM_PREFIXES):
                LOG.info("跳过系统会话目录：%s", wxid)
                continue
            self.get(wxid)
            found.append(wxid)
        return found


# ---------------------------------------------------------------- 进程级单例
# ★ 必须共用一份。autoreply / proactive / post_moment 各自 new 一个的话，
#   每个实例memory 和 life 都是自己缓存的一份 dict：A 写了 open_loops，
#   B 手里还是旧的，下一次 B.save() 就把 A 的改动覆盖掉 —— 表现为
#   「回访过的旧事又冒出来」「刚记的事没了」，而且完全看不出是谁覆盖的。
_registry: PeerRegistry | None = None
_registry_lock = threading.Lock()


def get_registry() -> PeerRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = PeerRegistry()
        return _registry


def self_life() -> FeizhiLife:
    """她自己的日子（共享层，读写）。

    只给 life tick 和「只关心她今天过得怎样」的地方用；
    要连关系私有层一起渲染，走 get_registry().get(wxid).life。
    """
    return FeizhiLife(SELF_PATH, keep_private_keys=False)
