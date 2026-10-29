"""下载 RVC 训练所需底模：hubert、rmvpe、pretrained_v2 的 G/D。"""
import sys
import time
from pathlib import Path

import requests

RVC = Path(r"<PROJECT_ROOT>\sing\RVC")
H = {"User-Agent": "Mozilla/5.0"}
BASE = "https://hf-mirror.com/lj1995/VoiceConversionWebUI/resolve/main/"

FILES = [
    ("hubert_base.pt", RVC / "assets" / "hubert" / "hubert_base.pt"),
    ("rmvpe.pt", RVC / "assets" / "rmvpe" / "rmvpe.pt"),
    ("pretrained_v2/f0G40k.pth", RVC / "assets" / "pretrained_v2" / "f0G40k.pth"),
    ("pretrained_v2/f0D40k.pth", RVC / "assets" / "pretrained_v2" / "f0D40k.pth"),
]


def dl(remote: str, out: Path) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 1024 * 1024:
        print("[skip] %-22s %.1f MB" % (out.name, out.stat().st_size / 1048576))
        return True
    url = BASE + remote
    try:
        r = requests.head(url, timeout=30, allow_redirects=True, headers=H)
        total = int(r.headers.get("Content-Length") or 0)
    except Exception as exc:  # noqa: BLE001
        print("[fail] %s head: %s" % (remote, exc))
        return False
    print("[get ] %-22s %.1f MB" % (out.name, total / 1048576), flush=True)
    t0 = time.time()
    try:
        with requests.get(url, headers=H, stream=True, timeout=120) as r:
            if r.status_code != 200:
                print("   HTTP", r.status_code)
                return False
            tmp = out.with_suffix(out.suffix + ".part")
            done = 0
            with tmp.open("wb") as fh:
                for chunk in r.iter_content(1024 * 256):
                    fh.write(chunk)
                    done += len(chunk)
                    if total and done % (1024 * 1024 * 20) < 1024 * 256:
                        print("   %.1f%%  %.0f/%.0f MB  %.1f MB/s"
                              % (done * 100.0 / total, done / 1048576, total / 1048576,
                                 done / 1048576 / max(0.1, time.time() - t0)), flush=True)
            if total and tmp.stat().st_size != total:
                print("   大小不符 %d != %d" % (tmp.stat().st_size, total))
                return False
            tmp.replace(out)
        print("   done %.1f MB / %.0fs" % (out.stat().st_size / 1048576, time.time() - t0))
        return True
    except Exception as exc:  # noqa: BLE001
        print("   FAIL", type(exc).__name__, str(exc)[:120])
        return False


ok = 0
for remote, out in FILES:
    if dl(remote, out):
        ok += 1
print("\n成功 %d / %d" % (ok, len(FILES)))
for _, out in FILES:
    if out.exists():
        print("  %-40s %.1f MB" % (out.name, out.stat().st_size / 1048576))
sys.exit(0 if ok == len(FILES) else 1)
