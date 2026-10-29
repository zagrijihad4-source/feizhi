import io
p = "voice.py"
s = io.open(p, encoding="utf-8").read()

old = "import ctypes\nimport logging\nimport threading\nimport time"
assert s.count(old) == 1
s = s.replace(old, "import ctypes\nimport logging\nimport random\nimport threading\nimport time", 1)

old = """        pcm_path = Path(pcm_path)
        if not self._ensure():
            return False"""
assert s.count(old) == 1
new = """        pcm_path = Path(pcm_path)
        if not self._ensure():
            return False
        # ★ 多人同时要语音时的排队顺序（2026-10-28 用户定的：随机）。
        #   录音通道全进程只有一条，_lock 保证串行，但谁先抢到锁取决于线程调度，
        #   实际上会偏向"先到先发"。这里在抢锁前随机让一让，让顺序真的随机。
        #   代价是单人也多等 0~2 秒 —— 语音本来就有拟人延迟，看不出来。
        if _voice_contention():
            time.sleep(random.uniform(0.0, 2.0))"""
s = s.replace(old, new, 1)

# 争用判定：队列里有没有别人在等
old = "def _ralt_lp(down: bool) -> int:"
assert s.count(old) == 1
new = '''_inflight = 0
_inflight_lock = threading.Lock()


def _voice_contention() -> bool:
    """现在是不是有多条语音在抢录音通道。"""
    with _inflight_lock:
        return _inflight > 1


def _ralt_lp(down: bool) -> int:'''
s = s.replace(old, new, 1)

# say_pcm 进出各记一次
old = """        pcm_path = Path(pcm_path)
        if not self._ensure():
            return False"""
assert s.count(old) == 1
s = s.replace(old, """        pcm_path = Path(pcm_path)
        global _inflight
        with _inflight_lock:
            _inflight += 1
        try:
            return self._say_pcm_inner(pcm_path, max_hold, retries, peer)
        finally:
            with _inflight_lock:
                _inflight -= 1

    def _say_pcm_inner(self, pcm_path: Path, max_hold: float, retries: int,
                       peer: str | None) -> bool:
        if not self._ensure():
            return False""", 1)

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("语音随机排队已接入")
