# -*- coding: utf-8 -*-
"""语音接收：自动听懂<OWNER>发来的语音消息。

链路（2026-10-15 全部实测打通）：
    收到 type=34 语音消息
      → PostMessage 往语音气泡位置投一个鼠标点击（**不抢前台**）
      → 微信自己去「下载 CDN → AES 解密 → SILK 解码」
      → 我们 hook 住 VoipEngine.dll!SKP_Silk_SDK_Decode，
        从第 6 个参数（samplesOut，每帧 320 样本 / 640 字节）读出 PCM
      → 拼成 16k 单声道 wav
      → MiMo ASR 转文字

关键参数（探出来的，别乱改）：
    SKP_Silk_SDK_Decode 的参数布局不是标准 SILK SDK：
      arg1 = decControl（首字段 16000，每帧样本数 320）
      arg3 = inData（每帧递增 14 字节）
      arg5 = samplesOut ← PCM 输出缓冲，进入时全 0，地址每帧 +640 字节
    标准签名里 samplesOut 是第 6 个参数，这里也是 arg5，但中间少了 nBytesIn。

点击坐标来自 voice_pos.json（用 calibrate_voice_pos.py 标定，存的是相对窗口比例，
所以窗口移动/缩放都不影响）。PostMessage 的鼠标消息 Qt 接受，键盘消息同理，
两者都不需要窗口有焦点。
"""
from __future__ import annotations

import base64
import ctypes
import json
import logging
import struct
import threading
import time
from ctypes import wintypes
from pathlib import Path

import frida

LOG = logging.getLogger("feizhi_pc.voice_in")

FRAME_SAMPLES = 320
SR = 16000
POS_FILE = Path(r"<PROJECT_ROOT>\tmp\voice_pos.json")
OUT_DIR = Path(r"<PROJECT_ROOT>\tmp\voice_capture")

u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
u32.FindWindowW.restype = wintypes.HWND
u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
u32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]

WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
MK_LBUTTON = 0x0001

JS = r"""
'use strict';
function exp(n) {
    try { if (Module.getGlobalExportByName) return Module.getGlobalExportByName(n); } catch (e) {}
    try { return Module.findExportByName(null, n); } catch (e) {}
    return null;
}
var voip = Process.findModuleByName('VoipEngine.dll');
var frames = 0;
var collecting = false;
var buf = [];
var lastAt = 0;

if (voip) {
    var p = voip.findExportByName('SKP_Silk_SDK_Decode');
    Interceptor.attach(p, {
        onEnter: function (a) { this.out = a[5]; },
        onLeave: function () {
            if (!collecting || !this.out || this.out.isNull()) return;
            try {
                var b = this.out.readByteArray(320 * 2);
                var u8 = new Uint8Array(b);
                for (var i = 0; i < u8.length; i++) buf.push(u8[i]);
                frames++;
                lastAt = Date.now();
            } catch (e) {}
        }
    });
    send({ t: 'ok', msg: 'decoder hooked' });
} else {
    send({ t: 'err', msg: 'VoipEngine 未加载' });
}

rpc.exports = {
    begin: function () { buf = []; frames = 0; collecting = true; lastAt = Date.now(); return true; },
    // 静默超过 idleMs 就认为播完了
    poll: function (idleMs) {
        var idle = Date.now() - lastAt;
        return { frames: frames, bytes: buf.length, done: collecting && frames > 0 && idle > idleMs };
    },
    take: function () {
        collecting = false;
        var out = new Uint8Array(buf);
        buf = [];
        return out.buffer;
    },
    abort: function () { collecting = false; buf = []; frames = 0; return true; }
};
"""


def _pick_pid() -> int | None:
    try:
        procs = frida.get_local_device().enumerate_processes()
    except Exception:
        procs = frida.enumerate_processes()
    for p in procs:
        if "weixin" in (p.name or "").lower():
            return p.pid
    return None


def voice_pos() -> tuple[float, float] | None:
    if not POS_FILE.exists():
        return None
    try:
        d = json.loads(POS_FILE.read_text(encoding="utf-8"))
        rx, ry = d["ratio"]
        return float(rx), float(ry)
    except Exception:  # noqa: BLE001
        return None


def write_wav(pcm: bytes, path: Path) -> Path:
    n = len(pcm)
    hdr = b"RIFF" + struct.pack("<I", 36 + n) + b"WAVEfmt "
    hdr += struct.pack("<IHHIIHH", 16, 1, 1, SR, SR * 2, 2, 16)
    hdr += b"data" + struct.pack("<I", n)
    path.write_bytes(hdr + pcm)
    return path


def asr_wav(wav: Path, cfg_path: Path | None = None) -> str:
    """送 MiMo ASR 转文字（ws 端点与 TTS 同一个，走 input_audio）。"""
    cfg_path = cfg_path or Path(r"<PROJECT_ROOT>\feizhi_pc\tts_config.json")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    m = cfg["mimo"]
    key = m["api_key"]
    url = m["base_url"]
    b64 = base64.b64encode(wav.read_bytes()).decode("ascii")
    payload = {
        "model": "mimo-v2.5-asr",
        "messages": [{"role": "user", "content": [
            {"type": "input_audio",
             "input_audio": {"data": "data:audio/wav;base64," + b64, "format": "wav"}}
        ]}],
    }
    import urllib.error
    from urllib.request import Request, urlopen
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method="POST", headers={
        "api-key": key, "Authorization": "Bearer " + key,
        "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("ASR 请求失败: %s", exc)
        return ""
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:  # noqa: BLE001
        return ""


class VoiceListener:
    """常驻的语音转写器。线程安全。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session = None
        self._script = None

    # ---------- 连接 ----------
    def _connect(self) -> bool:
        pid = _pick_pid()
        if not pid:
            LOG.warning("找不到微信进程，语音接收不可用")
            return False
        try:
            session = frida.attach(pid)
            script = session.create_script(JS)
            script.on("message", lambda m, d: LOG.debug("frida: %s", m.get("payload", m)))
            script.load()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("frida attach 失败: %s", exc)
            return False
        self._session, self._script = session, script
        LOG.info("语音接收通道就绪 pid=%d", pid)
        return True

    def _ensure(self) -> bool:
        if self._script is None and not self._connect():
            return False
        return self._script is not None

    def close(self) -> None:
        try:
            if self._session:
                self._session.detach()
        except Exception:  # noqa: BLE001
            pass
        self._session = self._script = None

    @property
    def _ex(self):
        return getattr(self._script, "exports_sync", None) or self._script.exports

    # ---------- 点击语音气泡 ----------
    @staticmethod
    def _click_voice(rx: float, ry: float) -> bool:
        hwnd = int(u32.FindWindowW(None, "微信") or 0)
        if not hwnd:
            return False
        wr = wintypes.RECT()
        u32.GetWindowRect(hwnd, ctypes.byref(wr))
        W, H = wr.right - wr.left, wr.bottom - wr.top
        sx = int(wr.left + rx * W)
        sy = int(wr.top + ry * H)
        pt = wintypes.POINT(sx, sy)
        u32.ScreenToClient(hwnd, ctypes.byref(pt))
        lp = ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)
        u32.PostMessageW(hwnd, WM_MOUSEMOVE, ctypes.c_void_p(0), ctypes.c_void_p(lp))
        time.sleep(0.05)
        u32.PostMessageW(hwnd, WM_LBUTTONDOWN, ctypes.c_void_p(MK_LBUTTON), ctypes.c_void_p(lp))
        time.sleep(0.08)
        u32.PostMessageW(hwnd, WM_LBUTTONUP, ctypes.c_void_p(0), ctypes.c_void_p(lp))
        return True

    # ---------- 主流程 ----------
    def transcribe(self, max_wait: float = 25.0, idle_ms: int = 900,
                   expected_sec: float = 0.0) -> tuple[str, Path | None]:
        """点击语音气泡 → 抓 PCM → ASR。返回 (文字, wav 路径)。

        expected_sec：消息里写的语音时长（voicelength/1000），用于校验有没有抓全。
        """
        pos = voice_pos()
        if not pos:
            LOG.warning("还没标定语音气泡位置，先跑 calibrate_voice_pos.py")
            return "", None

        with self._lock:
            if not self._ensure():
                return "", None
            try:
                self._ex.begin()
            except Exception as exc:  # noqa: BLE001
                LOG.warning("begin 失败: %s", exc)
                self.close()
                return "", None

            rx, ry = pos
            shot = self._click_voice(rx, ry)
            if not shot:
                return "", None

            t0 = time.time()
            done = False
            info = {"frames": 0, "bytes": 0}
            # 前 3 秒没动静就往上挪一点重点（气泡位置会随消息条数浮动）
            retried = False
            while time.time() - t0 < max_wait:
                time.sleep(0.2)
                try:
                    info = self._ex.poll(idle_ms)
                except Exception:  # noqa: BLE001
                    break
                if info.get("done"):
                    done = True
                    break
                if not retried and info.get("frames", 0) == 0 and time.time() - t0 > 3.0:
                    retried = True
                    LOG.info("第一次点击没抓到，往上挪 3%% 重试")
                    self._click_voice(rx, max(0.2, ry - 0.03))

            if not done:
                LOG.warning("抓语音超时（frames=%s bytes=%s）", info.get("frames"), info.get("bytes"))
                try:
                    self._ex.abort()
                except Exception:  # noqa: BLE001
                    pass
                return "", None

            try:
                raw = self._ex.take()
            except Exception as exc:  # noqa: BLE001
                LOG.warning("取 PCM 失败: %s", exc)
                return "", None

        if not raw:
            return "", None
        pcm = bytes(raw)
        sec = len(pcm) / 2 / SR
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        wav = write_wav(pcm, OUT_DIR / ("voice_%s.wav" % time.strftime("%H%M%S")))
        note = ""
        if expected_sec and sec < expected_sec * 0.75:
            note = "（比消息里的 %.1fs 短，可能少了开头几帧）" % expected_sec
        LOG.info("语音抓取完成 %.2fs%s -> %s", sec, note, wav.name)

        text = asr_wav(wav)
        LOG.info("ASR: %r", text[:60])
        return text, wav


_listener: VoiceListener | None = None
_listener_lock = threading.Lock()


def get_listener() -> VoiceListener:
    global _listener
    with _listener_lock:
        if _listener is None:
            _listener = VoiceListener()
        return _listener


def transcribe(expected_sec: float = 0.0) -> tuple[str, Path | None]:
    return get_listener().transcribe(expected_sec=expected_sec)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    t, p = transcribe()
    print("文字:", t)
    print("音频:", p)
