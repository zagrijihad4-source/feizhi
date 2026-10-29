"""反复跑 separate.py，缺哪个包就装哪个，直到跑通（最多 12 轮）。"""
import re
import subprocess
import sys

PY = r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe"
PIP_MAP = {
    "yaml": "pyyaml", "PIL": "pillow", "cv2": "opencv-python-headless",
    "sklearn": "scikit-learn", "skimage": "scikit-image",
    "ml_collections": "ml_collections", "wandb": "wandb",
    "pydub": "pydub", "soundfile": "soundfile", "librosa": "librosa",
    "matplotlib": "matplotlib", "tqdm": "tqdm", "einops": "einops",
    "omegaconf": "omegaconf", "torch": "torch", "torchaudio": "torchaudio",
    "numpy": "numpy", "scipy": "scipy", "pandas": "pandas",
    "bs_roformer": None, "beartype": "beartype",
}

for rnd in range(12):
    p = subprocess.run([PY, "-u", "separate.py"], cwd=r"<PROJECT_ROOT>\sing",
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    if p.returncode == 0:
        print("成功（第 %d 轮）" % (rnd + 1))
        print(p.stdout[-1500:])
        sys.exit(0)
    tail = (p.stdout or "") + (p.stderr or "")
    print("--- 第 %d 轮失败 ---" % (rnd + 1))
    print(tail[-600:])
    m = re.search(r"No module named '([^']+)'", tail)
    if not m:
        print("不是缺包问题，停")
        sys.exit(1)
    mod = m.group(1).split(".")[0]
    pkg = PIP_MAP.get(mod, mod)
    if not pkg:
        print("模块 %s 无对应 pip 包，停" % mod)
        sys.exit(1)
    print(">>> 补装:", pkg)
    subprocess.run([PY, "-m", "pip", "install", "--no-input", "--progress-bar", "off",
                    "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", pkg],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print("轮次用尽")
sys.exit(2)
