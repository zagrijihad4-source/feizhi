"""Feizhi control panel: local web console over the existing feizhi_pc modules.

Talks to the same SQLite store / state files the running service uses, so the
panel shows live data instead of a copy. Sending goes through HookBridge, which
is the same path the autoreply loop uses.

usage: python panel/server.py [port]
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FEIZHI = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(FEIZHI))

HERE = Path(__file__).resolve().parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
PEER = "wx99"  # replaced below with the real wxid
NOTES = HERE / "requirements.md"
RVC = Path(r"<PROJECT_ROOT>\sing\RVC")
SING = Path(r"<PROJECT_ROOT>\sing")

PEER_WXID = "wxid99r5idk4n8or22"

_state_cache = {"at": 0.0, "data": {}}
_jobs = {}
_jobs_lock = threading.Lock()


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return default if default is not None else {"error": "%s: %s" % (type(exc).__name__, exc)}


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _run(cmd, timeout=8):
    """Never let a child console program flash a window: the panel polls
    tasklist every few seconds, and without CREATE_NO_WINDOW each poll spawned
    a black console box on the user's desktop."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="ignore",
                           creationflags=CREATE_NO_WINDOW)
        return p.stdout or ""
    except Exception:  # noqa: BLE001
        return ""


def _pid_alive(pid):
    if not pid:
        return False
    out = _run(["tasklist", "/FI", "PID eq %d" % pid, "/NH"])
    return str(pid) in out


def _bridge_root():
    return Path(r"<PROJECT_ROOT>\wx-basic-bridge")


def collect_status():
    now = time.time()
    if now - _state_cache["at"] < 2.0 and _state_cache["data"]:
        return _state_cache["data"]

    st = {}

    # WeChat
    wx = _run(["tasklist", "/FI", "IMAGENAME eq Weixin.exe", "/NH"])
    pids = re.findall(r"Weixin\.exe\s+(\d+)", wx)
    st["wechat"] = {"running": bool(pids), "pids": pids}

    # worker / hook channel
    chan = _bridge_root() / "bridge" / "control" / "channel.txt"
    if chan.exists():
        kv = {}
        for line in chan.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip()
        age = now - chan.stat().st_mtime
        st["worker"] = {
            "phase": kv.get("phase", "?"),
            "hooked": kv.get("hooked") == "1",
            "stale_sec": round(age, 1),
            "healthy": kv.get("phase") == "running" and kv.get("hooked") == "1" and age < 30,
            "hwnd": kv.get("hwnd", ""),
            "callbacks": int(kv.get("callbacks", 0) or 0),
        }
    else:
        st["worker"] = {"healthy": False, "phase": "missing"}

    # feizhi service
    pid_file = FEIZHI / "state" / "run_both.pid"
    pid = None
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except Exception:  # noqa: BLE001
            pid = None
    st["service"] = {"pid": pid, "running": _pid_alive(pid)}

    # GPU
    gpu = _run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,power.draw",
                "--format=csv,noheader,nounits"])
    if gpu.strip():
        parts = [p.strip() for p in gpu.strip().splitlines()[0].split(",")]
        st["gpu"] = {"used": parts[0], "total": parts[1], "util": parts[2], "power": parts[3]}

    # store counters
    def _counts():
        from store import ContextStore
        s = ContextStore()
        try:
            return {"counts": s.counts(), "outbound": s.outbound_stats()}
        finally:
            s.close()

    st["store"] = _safe(_counts, {})

    # sing artifacts
    outs = sorted((SING / "outputs" / "rvc").glob("*_mix.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
    st["songs"] = [{"name": p.name, "mb": round(p.stat().st_size / 1048576, 1),
                    "mtime": time.strftime("%m-%d %H:%M", time.localtime(p.stat().st_mtime))}
                   for p in outs[:12]]

    st["now"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _state_cache["at"] = now
    _state_cache["data"] = st
    return st


def get_messages(limit=40):
    from store import ContextStore
    s = ContextStore()
    try:
        return s.recent(limit)
    finally:
        s.close()


def get_memory():
    p = FEIZHI / "state" / "feizhi_memory.json"
    if not p.exists():
        return {"facts": [], "events": []}
    d = json.loads(p.read_text(encoding="utf-8"))
    return {
        "facts": d.get("facts", [])[-25:],
        "events": d.get("events", [])[-25:],
        "stats": {"facts": len(d.get("facts", [])), "events": len(d.get("events", []))},
    }


def get_life():
    p = FEIZHI / "state" / "feizhi_life.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    out = {"mood": d.get("mood"), "ongoing": d.get("ongoing", [])[-8:],
           "loops": d.get("open_loops", [])[-8:]}
    return out


def get_moments():
    p = FEIZHI / "state" / "moments_posted.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(d, list):
        return d[-10:]
    if isinstance(d, dict):
        items = d.get("posted") or d.get("items") or []
        return items[-10:] if isinstance(items, list) else []
    return []


def get_logs(n=60):
    cands = list((FEIZHI / "logs").glob("*.log")) if (FEIZHI / "logs").exists() else []
    cands += list((FEIZHI).glob("*.log"))
    if not cands:
        return {"lines": [], "file": None}
    f = max(cands, key=lambda p: p.stat().st_mtime)
    try:
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:]
    except Exception:  # noqa: BLE001
        lines = []
    return {"lines": lines, "file": str(f)}


def _record(role, text, source):
    """Panel-originated messages must land in the same store the autoreply loop
    reads, otherwise the conversation view silently diverges from reality."""
    try:
        from store import ContextStore
        s = ContextStore()
        try:
            key = "panel-%d-%s" % (int(time.time() * 1000), str(abs(hash((role, text))) % 100000))
            s.add(PEER_WXID, role, text, source, key)
        finally:
            s.close()
    except Exception:  # noqa: BLE001
        pass


def do_send_text(text):
    from bridge import HookBridge
    b = HookBridge()
    ok = b.send_text(PEER_WXID, text)
    if ok:
        _record("assistant", text, "panel")
    return {"ok": bool(ok)}


def _job_start(name):
    jid = "%s-%d" % (name, int(time.time() * 1000))
    with _jobs_lock:
        _jobs[jid] = {"id": jid, "state": "running", "started": time.time(), "log": []}
    return jid


def _job_log(jid, msg):
    with _jobs_lock:
        j = _jobs.get(jid)
        if j:
            j["log"].append("%s %s" % (time.strftime("%H:%M:%S"), msg))


def _job_done(jid, ok, detail=""):
    with _jobs_lock:
        j = _jobs.get(jid)
        if j:
            j["state"] = "done" if ok else "failed"
            j["detail"] = detail
            j["ended"] = time.time()


def do_send_voice(text):
    """TTS then push as a WeChat voice message, in the background."""
    jid = _job_start("voice")

    def work():
        try:
            import tts
            import voice
            _job_log(jid, "synthesize: %s" % text[:30])
            pcm = tts.synthesize_pcm(text)
            _job_log(jid, "pcm ready, sending")
            ok = voice.VoiceSender().say_pcm(Path(pcm), max_hold=60.0, retries=1)
            _job_log(jid, "sent=%s" % ok)
            if ok:
                _record("assistant", "[语音] " + text, "panel")
            _job_done(jid, bool(ok))
        except Exception as exc:  # noqa: BLE001
            _job_log(jid, "ERROR %s" % exc)
            _job_done(jid, False, str(exc))

    threading.Thread(target=work, daemon=True).start()
    return {"job": jid}


def do_send_song(name, start=83, dur=45):
    """Push an already-rendered cover clip to WeChat."""
    jid = _job_start("song")

    def work():
        try:
            import numpy as np
            import soundfile as sf
            import voice
            src = SING / "outputs" / "rvc" / name
            if not src.exists():
                raise FileNotFoundError(str(src))
            x, sr = sf.read(str(src), dtype="float32", always_2d=True)
            x = x.mean(axis=1)
            a, b = int(start * sr), min(int((start + dur) * sr), len(x))
            seg = x[a:b]
            n16 = int(round(len(seg) * 16000 / sr))
            y = np.interp(np.linspace(0, len(seg) - 1, n16), np.arange(len(seg)), seg).astype(np.float32)
            y = y / max(float(np.abs(y).max()), 1e-9) * 0.92
            pcm = SING / "outputs" / "rvc" / "_panel_send.pcm"
            pcm.write_bytes((y * 32767).astype("<i2").tobytes())
            _job_log(jid, "clip %.1fs, sending" % (len(y) / 16000))
            ok = voice.VoiceSender().say_pcm(pcm, max_hold=60.0, retries=1)
            _job_log(jid, "sent=%s" % ok)
            if ok:
                _record("assistant", "[翻唱] " + name, "panel")
            _job_done(jid, bool(ok))
        except Exception as exc:  # noqa: BLE001
            _job_log(jid, "ERROR %s" % exc)
            _job_done(jid, False, str(exc))

    threading.Thread(target=work, daemon=True).start()
    return {"job": jid}


def do_new_song(song, params=None):
    """Full pipeline: bilibili -> separate -> RVC -> mix. Long running."""
    jid = _job_start("newsong")
    p = params or {}
    index_rate = p.get("index_rate", 0)
    protect = p.get("protect", 0.5)
    eq = p.get("eq", 1.2)

    def work():
        py = str(SING / ".venv" / "Scripts" / "python.exe")
        env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")

        def run(cmd, **kw):
            kw.setdefault("creationflags", CREATE_NO_WINDOW)
            return subprocess.run(cmd, **kw)

        try:
            slug = re.sub(r"[^0-9a-zA-Z]+", "", song)[:12] or "song"
            _job_log(jid, "fetch from bilibili: %s" % song)
            cmd = [py, "-X", "utf8", str(SING / "bili_fetch.py"), song, slug]
            r = run(cmd, cwd=str(SING), env=env, capture_output=True, text=True,
                    encoding="utf-8", errors="ignore", timeout=300)
            _job_log(jid, (r.stdout or "").strip().splitlines()[-1] if r.stdout else "no output")
            m4a = SING / "source" / ("%s.m4a" % slug)
            if not m4a.exists():
                raise RuntimeError("download failed")
            wav = SING / "source" / ("%s.wav" % slug)
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(m4a),
                 "-ar", "44100", "-ac", "2", str(wav)], timeout=180)
            _job_log(jid, "separating")
            r = run([py, "-u", str(SING / "separate_any.py"), str(wav),
                     str(SING / "source" / slug)], cwd=str(SING), env=env,
                    capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=900)
            if not (SING / "source" / ("%s_vocal.wav" % slug)).exists():
                raise RuntimeError("separation failed: %s" % (r.stdout or "")[-300:])
            _job_log(jid, "converting (index-rate=%s protect=%s)" % (index_rate, protect))
            out = SING / "outputs" / "rvc" / ("%s_yinyin.wav" % slug)
            r = run([py, "-u", str(SING / "rvc_cover.py"),
                     str(SING / "source" / ("%s_vocal.wav" % slug)), str(out),
                     "--model", "yinyin.pth", "--index-rate", str(index_rate),
                     "--protect", str(protect)], cwd=str(SING), env=env,
                    capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=1800)
            if not out.exists():
                raise RuntimeError("conversion failed: %s" % (r.stdout or "")[-300:])
            _job_log(jid, "eq + mix")
            eqd = SING / "outputs" / "rvc" / ("%s_eq.wav" % slug)
            run([py, str(SING / "eq_boost.py"), str(out), str(eqd), str(eq)],
                cwd=str(SING), env=env, timeout=600)
            mix = SING / "outputs" / "rvc" / ("%s_mix.wav" % slug)
            run([py, str(SING / "mix_cover.py"), str(eqd),
                 str(SING / "source" / ("%s_inst.wav" % slug)), str(mix), "1.05", "0.72"],
                cwd=str(SING), env=env, timeout=600)
            _job_log(jid, "done -> %s" % mix.name)
            _job_done(jid, True, mix.name)
        except Exception as exc:  # noqa: BLE001
            _job_log(jid, "ERROR %s" % exc)
            _job_done(jid, False, str(exc))

    threading.Thread(target=work, daemon=True).start()
    return {"job": jid}


def add_note(text):
    NOTES.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    with open(NOTES, "a", encoding="utf-8") as f:
        f.write("\n## %s\n\n%s\n" % (stamp, text.strip()))
    return {"ok": True, "file": str(NOTES)}


def get_notes():
    if not NOTES.exists():
        return {"text": ""}
    return {"text": NOTES.read_text(encoding="utf-8")}


class Handler(BaseHTTPRequestHandler):
    server_version = "FeizhiPanel/1.0"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype="text/html; charset=utf-8"):
        if not path.exists():
            self._json({"error": "not found"}, 404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                self._file(HERE / "index.html")
            elif u.path == "/api/status":
                self._json(collect_status())
            elif u.path == "/api/messages":
                self._json(_safe(lambda: get_messages(int(q.get("limit", ["40"])[0])), []))
            elif u.path == "/api/memory":
                self._json(_safe(get_memory, {}))
            elif u.path == "/api/life":
                self._json(_safe(get_life, {}))
            elif u.path == "/api/moments":
                self._json(_safe(get_moments, []))
            elif u.path == "/api/logs":
                self._json(_safe(lambda: get_logs(int(q.get("n", ["60"])[0])), {"lines": []}))
            elif u.path == "/api/notes":
                self._json(_safe(get_notes, {"text": ""}))
            elif u.path == "/api/job":
                jid = q.get("id", [""])[0]
                with _jobs_lock:
                    self._json(_jobs.get(jid) or {"error": "unknown job"}, 200 if jid in _jobs else 404)
            else:
                self._json({"error": "no route"}, 404)
        except Exception:  # noqa: BLE001
            self._json({"error": traceback.format_exc()[-500:]}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:  # noqa: BLE001
            body = {}
        try:
            if u.path == "/api/send":
                self._json(_safe(lambda: do_send_text(body.get("text", "")), {"ok": False}))
            elif u.path == "/api/voice":
                self._json(_safe(lambda: do_send_voice(body.get("text", "")), {"error": "failed"}))
            elif u.path == "/api/song":
                self._json(_safe(lambda: do_send_song(body.get("name", ""), float(body.get("start", 83)),
                                                      float(body.get("dur", 45))), {"error": "failed"}))
            elif u.path == "/api/newsong":
                self._json(_safe(lambda: do_new_song(body.get("song", ""), body.get("params")),
                                 {"error": "failed"}))
            elif u.path == "/api/note":
                self._json(_safe(lambda: add_note(body.get("text", "")), {"ok": False}))
            else:
                self._json({"error": "no route"}, 404)
        except Exception:  # noqa: BLE001
            self._json({"error": traceback.format_exc()[-500:]}, 500)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("feizhi panel: http://127.0.0.1:%d" % PORT, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
