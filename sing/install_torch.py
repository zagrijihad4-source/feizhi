"""装 torch：多个源依次尝试，哪个快用哪个。"""
import subprocess
import sys
import time
from pathlib import Path

PY = Path(r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe")
PKGS = ["torch==2.2.0", "torchaudio==2.2.0"]

INDEXES = [
    ("pytorch-official", "https://download.pytorch.org/whl/cu121"),
    ("sjtu", "https://mirror.sjtu.edu.cn/pytorch-wheels/cu121"),
    ("aliyun", "https://mirrors.aliyun.com/pypi/simple"),
]

for name, idx in INDEXES:
    print("=" * 60)
    print("尝试源:", name, idx, flush=True)
    cmd = [str(PY), "-m", "pip", "install", "--no-input",
           "--timeout", "60", "--retries", "2",
           "--progress-bar", "on",
           "--index-url", idx] + PKGS
    t0 = time.time()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", bufsize=1)
    last = 0.0
    try:
        for line in p.stdout:
            line = line.rstrip()
            if line:
                now = time.time()
                # 别把进度条刷屏，每 5 秒打一条
                if now - last > 5 or "Successfully" in line or "ERROR" in line:
                    print("[%5.0fs] %s" % (now - t0, line[-200:]), flush=True)
                    last = now
        p.wait(timeout=3600)
    except Exception as exc:  # noqa: BLE001
        print("中断:", exc, flush=True)
        p.kill()
        continue
    print("退出码", p.returncode, "耗时 %.0fs" % (time.time() - t0), flush=True)
    if p.returncode == 0:
        print("INSTALL OK via", name, flush=True)
        break
print("done")
