"""PC hook 桥适配层。

替代 Feizhi 的 adb_client：不再用 ADB 点击手机微信，改为
  - 收：轮询 bridge/inbox/*.json（hook 写入的入站消息）
  - 发：往 bridge/outbox 写 send_text 命令（hook worker 消费后真正发出）
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

LOG = logging.getLogger("feizhi_pc.bridge")

BRIDGE_ROOT = Path(r"<PROJECT_ROOT>\wx-basic-bridge")
INBOX = BRIDGE_ROOT / "bridge" / "inbox"
OUTBOX = BRIDGE_ROOT / "bridge" / "outbox"
CONTROL = BRIDGE_ROOT / "bridge" / "control"

# 系统/服务类会话，不做自动回复
IGNORE_PEERS = {"newsapp", "filehelper", "floatbottle", "medianote",
                "weixin", "notifymessage", "gh_", "weixinreminder"}


@dataclass(frozen=True)
class InboundMessage:
    msg_id: str
    local_id: str
    timestamp: int
    peer_wxid: str
    sender_wxid: str
    direction: str
    is_incoming: bool
    content: str
    raw: dict
    source_file: str

    @property
    def is_text(self) -> bool:
        return str(self.raw.get("type")) == "1"

    @property
    def is_group(self) -> bool:
        return bool(self.raw.get("roomId"))


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


class HookBridge:
    """与 hook 桥交互：读入站、发消息。"""

    def __init__(self, root: Path = BRIDGE_ROOT, state_dir: Path | None = None):
        self.root = root
        self.inbox = root / "bridge" / "inbox"
        self.outbox = root / "bridge" / "outbox"
        self.control = root / "bridge" / "control"
        self.state_dir = state_dir or Path(r"<PROJECT_ROOT>\feizhi_pc\state")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.seen_file = self.state_dir / "seen_inbox.txt"
        self._seen: set[str] = set(self._load_seen())

    # ---------- 去重 ----------
    def _load_seen(self) -> list[str]:
        if self.seen_file.exists():
            return [ln.strip() for ln in self.seen_file.read_text(
                encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        return []

    def _mark_seen(self, name: str) -> None:
        self._seen.add(name)
        with self.seen_file.open("a", encoding="utf-8") as fh:
            fh.write(name + "\n")

    def _msg_key(self, data: dict) -> str:
        """跨文件名的稳定去重键。"""
        return "{}:{}:{}:{}".format(
            data.get("peerWxId", ""), data.get("msgId", ""),
            data.get("localId", ""), data.get("timestamp", ""))

    # ---------- 收 ----------
    def poll_new(self) -> list[InboundMessage]:
        """返回尚未处理过的入站消息（按时间升序）。

        注意：这里**只读不标记**。标记由 mark_processed() 在业务层确认
        处理成功后再做，避免"被跳过/发送失败"的消息被永久吞掉。
        """
        if not self.inbox.is_dir():
            return []
        out: list[InboundMessage] = []
        for path in sorted(self.inbox.glob("*.json"), key=lambda p: p.stat().st_mtime):
            name = path.name
            if name in self._seen:
                continue
            data = _read_json(path)
            if not data:
                continue
            key = self._msg_key(data)
            if key in self._seen:
                continue
            out.append(InboundMessage(
                msg_id=str(data.get("msgId", "")),
                local_id=str(data.get("localId", "")),
                timestamp=int(data.get("timestamp") or 0),
                peer_wxid=str(data.get("peerWxId", "")),
                sender_wxid=str(data.get("senderWxId", "")),
                direction=str(data.get("direction", "")),
                is_incoming=bool(data.get("isIncoming")),
                content=str(data.get("content", "")),
                raw=data,
                source_file=name,
            ))
        return out

    def mark_processed(self, msg: InboundMessage) -> None:
        """确认处理完毕（或明确决定不再处理）后调用。"""
        self._mark_seen(msg.source_file)
        self._mark_seen(self._msg_key(msg.raw))

    def __init_seen_hint(self) -> None:
        pass

    def wait_for_new(self, timeout: float, interval: float = 1.0) -> list[InboundMessage]:
        """阻塞等待新消息，超时返回空列表。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            got = self.poll_new()
            if got:
                return got
            time.sleep(interval)
        return []

    # ---------- 发 ----------
    # ★ DLL 只有一个 next.txt 槽位：自动回复线程和主动消息线程同时写会互相覆盖，
    #   已由审查离线复现（R01：A 写入后 B 覆盖，worker 只消费 B，A 丢失）。
    #   所有发送都走 _submit，整段「写文件 → 等结果」持同一把锁。
    _OUTBOX_LOCK = threading.Lock()

    def _submit(self, kind: str, wxid: str, payload: str, timeout: float) -> dict | None:
        """写一条命令到 next.txt 并等 result_<seq>.json。返回结果 dict（超时 None）。"""
        self.outbox.mkdir(parents=True, exist_ok=True)
        seq = str(int(time.time() * 1000)) + uuid.uuid4().hex[:4]
        line = "{}\t{}\t{}\t{}".format(seq, kind, wxid, payload)
        result = self.control / ("result_{}.json".format(seq))
        with self._OUTBOX_LOCK:
            (self.outbox / "next.txt").write_text(line, encoding="utf-8")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if result.exists():
                    return _read_json(result)
                time.sleep(0.25)
        return None

    def send_text(self, wxid: str, content: str, timeout: float = 25.0) -> bool:
        """通过文件桥发送文本，等 result_<seq>.json 落地。"""
        if not content:
            return False
        # 桥协议: <seq>\t1\t<to_wxid>\t<content>
        payload = content.replace("\n", " ").replace("\t", " ")
        data = self._submit("1", wxid, payload, timeout)
        return bool(data and data.get("ok"))

    def send_image(self, wxid: str, image_path: str, timeout: float = 40.0) -> bool:
        """通过文件桥发送【本地图片】（type=10，图片消息模型）。

        实测结论（TASK_LOG 第二十一节）：
          - 图片消息走的是与文本同族的「普通消息模型」通道，**程序化发送已验证可用**；
          - 通道只接受【类型码 3（图片）】，GIF 会被静态化（只取首帧）；
          - 路径必须是绝对路径，且文件对微信进程可读。
        收藏表情（type=47）走的是信封路径，纯 hook 下仍未打通，故此处不做。
        """
        from pathlib import Path as _Path
        p = _Path(image_path)
        if not p.is_absolute() or not p.is_file():
            return False
        self.outbox.mkdir(parents=True, exist_ok=True)
        # 桥协议: <seq>\t10\t<to_wxid>\t<absolute_path>
        data = self._submit("10", wxid, str(p), timeout)
        return bool(data and data.get("ok"))

    # ★★ 2026-10-19 实测事故，推翻了这里原先的注释：
    #    原话是「上下文失效时只表现为发送失败，不会崩」——**事实是会崩**。
    #    00:12:10 发出一条 type=8 / tpl=4 之后，DLL 在
    #    wx_hook_bridge.dll+0x1b85 访问违例（0xc0000005），
    #    Windows Application Error 1000 直接把整个 Weixin.exe 带走。
    #    原因：ctx_override.txt 还是 19:35（5 小时前）捕获的，结构校验能过，
    #    但里面指向的堆对象早就被微信回收了，DLL 拿它当任务上下文用就踩空。
    #    DLL 侧没有时间戳校验（改它要重编译 + 重注入，会把微信再杀一次），
    #    所以先在 Python 侧挡：上下文太旧就不发需要它的命令，只记日志。
    CTX_MAX_AGE_SEC = 300.0

    def ctx_age_sec(self) -> float | None:
        """ctx_override.txt 距今多少秒；文件不存在返回 None。"""
        p = self.control / "ctx_override.txt"
        try:
            return max(0.0, time.time() - p.stat().st_mtime)
        except OSError:
            return None

    def send_sticker(self, wxid: str, index: int, kind: str = "fav",
                     timeout: float = 30.0) -> bool:
        """发送【微信原生表情】（不是图片消息，是真的表情消息）。

        kind="fav"  -> type=8  收藏表情，DLL 内置 7 个模板（index 0..6）
        kind="pack" -> type=12 表情包（表情商店添加），内置 4 枚（index 0..3）

        这两条走的是「载体替换 + 复用真实任务上下文」链路（TASK_LOG §26~§31），
        **已由对端实测确认送达**。与 send_image 的区别：send_image 发的是图片消息
        模型（type=10），对方看到的是普通图片；这里发的是真表情，会进表情栏样式。

        需要 DLL 侧 pack hook 已激活（`control\\ctx_override.txt` 有**新鲜**上下文）。
        上下文太旧时这里直接返回 False —— 硬发出去会把微信带崩（见上面的注释）。
        """
        if index < 0:
            return False
        age = self.ctx_age_sec()
        if age is None:
            LOG.warning("没有 ctx_override.txt（微信重启后还没捕获到上下文），表情发送跳过")
            return False
        if age > self.CTX_MAX_AGE_SEC:
            LOG.warning("ctx_override 已过期 %.0f 分钟（上限 %.0f）—— 表情发送跳过；"
                        "实测拿过期上下文发会让微信崩溃",
                        age / 60.0, self.CTX_MAX_AGE_SEC / 60.0)
            return False
        type_code = "8" if kind == "fav" else "12"
        # 桥协议: <seq>\t<type>\t<to_wxid>\t<index>
        data = self._submit(type_code, wxid, str(int(index)), timeout)
        return bool(data and data.get("ok"))

    def worker_healthy(self, max_age_sec: float = 30.0) -> bool:
        """DLL 的 worker 线程是否真的在跑。

        ★ 2026-10-19 事故暴露的盲区：`hook_alive()` 只看「DLL 模块在不在进程里」，
          而那次微信崩溃重启后模块还在、worker 线程却已经退出
          （channel.txt: phase=worker_exiting / hooked=0 / status=worker stopped），
          于是 hook_alive 报 True、实际一条也发不出去。
          真正可靠的判据是 channel.txt：worker 每 2 秒刷一次 `phase=running`，
          停止刷新就说明它没了。
        """
        ch = self.control / "channel.txt"
        try:
            st = ch.stat()
        except OSError:
            return False
        if time.time() - st.st_mtime > max_age_sec:
            return False
        try:
            txt = ch.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        return "phase=running" in txt and "hooked=1" in txt

    # ---------- 健康 ----------
    def hook_alive(self) -> bool:
        """hook 是否可用。

        注意：不要看 heartbeat.txt —— 那个文件是**注入器 python 进程**写的，
        注入器退出后就停更，但 DLL worker 仍在微信进程内运行（收发都正常）。
        正确判据是：微信进程里加载了 wx_hook_bridge*.dll。
        """
        owner = self.owner()
        if not owner:
            return False
        pid = owner[0]
        try:
            import subprocess
            ps = (
                "$p=Get-Process -Id %d -ErrorAction SilentlyContinue;"
                "if($p){ ($p.Modules | Where-Object { $_.ModuleName -like 'wx_hook_bridge*' }"
                " | Measure-Object).Count } else { 0 }" % pid
            )
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                                 capture_output=True, text=True, timeout=30).stdout.strip()
            return out.isdigit() and int(out) > 0
        except Exception:
            return False

    def send_capable(self, wxid: str = "filehelper") -> bool:
        """实测一次发送能力，比心跳更可信。"""
        return self.send_text(wxid, "ping", timeout=15)

    def owner(self) -> tuple[int, str] | None:
        f = self.control / "worker_owner.txt"
        if not f.exists():
            return None
        try:
            pid_s, base = f.read_text(encoding="utf-8", errors="replace").strip().split(":")
            return int(pid_s), base
        except Exception:
            return None
