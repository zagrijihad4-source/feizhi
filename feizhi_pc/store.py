"""对话上下文存储（SQLite）。

沿用 Feizhi 的语义：role=user 是<OWNER>发来的，role=assistant 是绯栀发的。
source 区分 inbound / auto_reply / proactive，便于统计与调试。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

DEFAULT_DB = Path(r"<PROJECT_ROOT>\feizhi_pc\state\context.sqlite3")

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_wxid    TEXT NOT NULL,
    role         TEXT NOT NULL,          -- user | assistant
    text         TEXT NOT NULL,
    sent_at_ms   INTEGER NOT NULL,
    source       TEXT NOT NULL,          -- inbound | auto_reply | proactive
    dedupe_key   TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_peer_time ON messages(peer_wxid, sent_at_ms);
-- ★ 出站任务表（审查 R02）。
-- 旧流程是"生成完 → 立刻把入站标记已处理 → 塞进内存队列"，
-- 发送失败、进程退出都会永久丢掉这条回复。
-- 现在改成：先落库(pending) → 发送线程认领(in_flight) → 成功后(submitted)才标记入站。
CREATE TABLE IF NOT EXISTS outbound (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_wxid    TEXT NOT NULL,
    payload      TEXT NOT NULL,          -- JSON: {messages:[...], media, incoming}
    status       TEXT NOT NULL,          -- pending | in_flight | submitted | failed | unknown
    created_ms   INTEGER NOT NULL,
    updated_ms   INTEGER NOT NULL,
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT,
    inbound_key  TEXT                    -- 关联的入站去重键，提交成功后才 mark_processed
);
CREATE INDEX IF NOT EXISTS idx_outbound_status ON outbound(status, id);
"""


class ContextStore:
    """线程安全的上下文库。

    `both` 模式下自动回复（主线程）与主动消息（后台线程）共用一个实例，
    而 sqlite3 默认禁止跨线程使用连接，所以这里 check_same_thread=False 并加锁。
    """

    def __init__(self, db_path: Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._con = sqlite3.connect(str(self.db_path), check_same_thread=False)
        with self._lock:
            self._con.executescript(SCHEMA)
            self._con.commit()

    def close(self) -> None:
        try:
            with self._lock:
                self._con.close()
        except Exception:
            pass

    def add(self, peer_wxid: str, role: str, text: str, source: str,
            dedupe_key: str, sent_at_ms: int | None = None) -> bool:
        """写入一条；dedupe_key 重复时返回 False。"""
        ts = sent_at_ms or int(time.time() * 1000)
        try:
            with self._lock:
                self._con.execute(
                    "INSERT INTO messages (peer_wxid, role, text, sent_at_ms, source, dedupe_key)"
                    " VALUES (?,?,?,?,?,?)",
                    (peer_wxid, role, text, ts, source, dedupe_key),
                )
                self._con.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def history(self, peer_wxid: str, limit: int = 20) -> list[tuple[str, str]]:
        """返回 [(role, text)] 升序，供 LLM 上下文使用。"""
        with self._lock:
            cur = self._con.execute(
                "SELECT role, text FROM messages WHERE peer_wxid = ?"
                " ORDER BY sent_at_ms DESC, id DESC LIMIT ?",
                (peer_wxid, limit),
            )
            rows = cur.fetchall()
        return [(r[0], r[1]) for r in reversed(rows)]

    def last_assistant_at(self, peer_wxid: str) -> int:
        with self._lock:
            cur = self._con.execute(
                "SELECT COALESCE(MAX(sent_at_ms),0) FROM messages"
                " WHERE peer_wxid = ? AND role = 'assistant'",
                (peer_wxid,),
            )
            return int(cur.fetchone()[0])

    def last_user_at(self, peer_wxid: str) -> int:
        with self._lock:
            cur = self._con.execute(
                "SELECT COALESCE(MAX(sent_at_ms),0) FROM messages"
                " WHERE peer_wxid = ? AND role = 'user'",
                (peer_wxid,),
            )
            return int(cur.fetchone()[0])

    def counts(self) -> dict:
        with self._lock:
            cur = self._con.execute("SELECT source, COUNT(*) FROM messages GROUP BY source")
            return {src: n for src, n in cur.fetchall()}

    def all_messages(self, peer_wxid: str) -> list[dict]:
        """该会话**全部**消息（id 升序）。

        ★ 供历史压缩用（审查 R12）：旧代码 history.py 用 recent(limit=5000)，
          第 5001 条起永远读不到、也没被摘要覆盖，"全量记忆"名不副实。
        """
        with self._lock:
            rows = self._con.execute(
                "SELECT id, role, text FROM messages WHERE peer_wxid = ? ORDER BY id",
                (peer_wxid,)).fetchall()
        return [{"id": r[0], "role": r[1], "text": r[2]} for r in rows]

    def recent(self, limit: int = 10) -> list[dict]:
        with self._lock:
            cur = self._con.execute(
                "SELECT id, peer_wxid, role, text, sent_at_ms, source FROM messages"
                " ORDER BY id DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
        cols = ["id", "peer_wxid", "role", "text", "sent_at_ms", "source"]
        return [dict(zip(cols, row)) for row in rows]

    # ---------- 出站任务（审查 R02）----------
    def enqueue_outbound(self, peer_wxid: str, payload: dict,
                         inbound_key: str = "") -> int:
        """把一份待发计划落库（pending），返回任务 id。"""
        now = int(time.time() * 1000)
        body = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            cur = self._con.execute(
                "INSERT INTO outbound (peer_wxid, payload, status, created_ms, updated_ms,"
                " attempts, last_error, inbound_key) VALUES (?,?,?,?,?,0,'',?)",
                (peer_wxid, body, "pending", now, now, inbound_key))
            self._con.commit()
            return int(cur.lastrowid)

    def claim_outbound(self, limit: int = 5) -> list[dict]:
        """原子认领 pending 任务（置 in_flight），返回任务列表。"""
        now = int(time.time() * 1000)
        out: list[dict] = []
        with self._lock:
            rows = self._con.execute(
                "SELECT id, peer_wxid, payload, attempts, inbound_key FROM outbound"
                " WHERE status = 'pending' ORDER BY id LIMIT ?", (limit,)).fetchall()
            for oid, peer, body, attempts, ikey in rows:
                self._con.execute(
                    "UPDATE outbound SET status='in_flight', updated_ms=?, attempts=attempts+1"
                    " WHERE id=? AND status='pending'", (now, oid))
                try:
                    payload = json.loads(body)
                except Exception:  # noqa: BLE001
                    payload = {}
                out.append({"id": oid, "peer_wxid": peer, "payload": payload,
                            "attempts": attempts + 1, "inbound_key": ikey})
            self._con.commit()
        return out

    def mark_outbound(self, oid: int, status: str, error: str = "") -> None:
        now = int(time.time() * 1000)
        with self._lock:
            self._con.execute(
                "UPDATE outbound SET status=?, updated_ms=?, last_error=? WHERE id=?",
                (status, now, (error or "")[:300], oid))
            self._con.commit()

    def recover_outbound(self, stale_ms: int = 300_000, max_attempts: int = 3) -> dict:
        """恢复：in_flight 超时→unknown（不自动重发）；failed 且未达上限→重新 pending。"""
        now = int(time.time() * 1000)
        stats = {"unknown": 0, "requeued": 0}
        with self._lock:
            cur = self._con.execute(
                "UPDATE outbound SET status='unknown', updated_ms=?, last_error='in_flight 超时'"
                " WHERE status='in_flight' AND updated_ms < ?", (now, now - stale_ms))
            stats["unknown"] = cur.rowcount
            cur = self._con.execute(
                "UPDATE outbound SET status='pending', updated_ms=? WHERE status='failed'"
                " AND attempts < ?", (now, max_attempts))
            stats["requeued"] = cur.rowcount
            self._con.commit()
        return stats

    def outbound_stats(self) -> dict:
        with self._lock:
            rows = self._con.execute(
                "SELECT status, COUNT(*) FROM outbound GROUP BY status").fetchall()
        return {s: n for s, n in rows}
