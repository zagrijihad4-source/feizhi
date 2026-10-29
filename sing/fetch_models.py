"""从 hf-mirror 下 SoulX-Singer 的 SVC 权重和 RMVPE（F0 提取）。"""
import sys
import time
from pathlib import Path

import requests

BASE = "https://hf-mirror.com"
DEST = Path(r"<PROJECT_ROOT>\sing\pretrained_models")

FILES = [
    ("Soul-AILab/SoulX-Singer", "model-svc.pt",
     DEST / "SoulX-Singer" / "model-svc.pt"),
    ("Soul-AILab/SoulX-Singer-Preprocess", "rmvpe/rmvpe.pt",
     DEST / "SoulX-Singer-Preprocess" / "rmvpe" / "rmvpe.pt"),
]


def download(repo: str, fname: str, out: Path) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    url = "%s/%s/resolve/main/%s" % (BASE, repo, fname)
    if out.exists() and out.stat().st_size > 1024 * 1024:
        print("[skip] %s 已存在 %.1f MB" % (out.name, out.stat().st_size / 1048576))
        return True
    print("[get ] %s -> %s" % (url, out))
    t0 = time.time()
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            if r.status_code != 200:
                print("  HTTP", r.status_code)
                return False
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            tmp = out.with_suffix(out.suffix + ".part")
            with tmp.open("wb") as fh:
                for chunk in r.iter_content(1024 * 256):
                    fh.write(chunk)
                    done += len(chunk)
                    if total and done % (1024 * 1024 * 40) < 1024 * 256:
                        pct = done * 100.0 / total
                        print("  %.1f%%  %.0f/%.0f MB  %.1f MB/s"
                              % (pct, done / 1048576, total / 1048576,
                                 done / 1048576 / max(0.1, time.time() - t0)))
            tmp.replace(out)
        print("  done %.1f MB / %.1fs" % (out.stat().st_size / 1048576, time.time() - t0))
        return True
    except Exception as exc:  # noqa: BLE001
        print("  FAIL", type(exc).__name__, str(exc)[:150])
        return False


ok = 0
for repo, fname, out in FILES:
    if download(repo, fname, out):
        ok += 1

print("\n成功 %d / %d" % (ok, len(FILES)))
for _, _, out in FILES:
    if out.exists():
        print("  %-40s %.1f MB" % (out.name, out.stat().st_size / 1048576))
sys.exit(0 if ok == len(FILES) else 1)
