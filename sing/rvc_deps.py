"""反复跑 RVC 预处理，缺哪个包就补哪个（最多 15 轮）。"""
import re
import subprocess
import sys

PY = r"<PROJECT_ROOT>\sing\.venv\Scripts\python.exe"
RVC = r"<PROJECT_ROOT>\sing\RVC"
MAP = {
    "av": "av", "ffmpeg": "ffmpeg-python", "faiss": "faiss-cpu",
    "torchfcpe": "torchfcpe", "local_attention": "local-attention",
    "pymss": "pymss", "onnxruntime": "onnxruntime",
    "cv2": "opencv-python-headless", "split_lang": "split-lang",
    "fast_langdetect": "fast-langdetect", "i18n": None,   # i18n 是本仓库的包
    "einops": "einops", "librosa": "librosa", "soundfile": "soundfile",
    "yaml": "pyyaml", "tensorboard": "tensorboard", "matplotlib": "matplotlib",
    "sklearn": "scikit-learn", "parselmouth": "praat-parselmouth",
    "numpy": "numpy", "scipy": "scipy", "tqdm": "tqdm",
}

CMD = [PY, "-u", r"train\preprocess.py", "dataset\\yinyin", "40000", "4",
       r"logs\yinyin", "False", "0.3"]

for rnd in range(15):
    p = subprocess.run(CMD, cwd=RVC, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800,
                       env={"PYTHONPATH": RVC, **__import__("os").environ})
    if p.returncode == 0:
        print("预处理成功（第 %d 轮）" % (rnd + 1))
        print((p.stdout or "")[-1200:])
        sys.exit(0)
    tail = (p.stdout or "") + (p.stderr or "")
    print("--- 第 %d 轮失败 ---" % (rnd + 1))
    print(tail[-500:])
    m = re.search(r"No module named '([^']+)'", tail)
    if not m:
        print("不是缺包问题，停")
        sys.exit(1)
    mod = m.group(1).split(".")[0]
    pkg = MAP.get(mod, mod)
    if pkg is None:
        print("模块 %s 属于本仓库，检查 PYTHONPATH" % mod)
        sys.exit(1)
    print(">>> 补装:", pkg, flush=True)
    subprocess.run([PY, "-m", "pip", "install", "--no-input", "--progress-bar", "off",
                    "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", pkg],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print("轮次用尽")
sys.exit(2)
