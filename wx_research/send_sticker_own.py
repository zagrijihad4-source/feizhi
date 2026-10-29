"""Send one of OUR OWN favourited stickers by building the emoji XML ourselves.

Earlier attempt failed because it replayed another account's sticker (its md5 is
not in our library, so the server rejects it). Here we build the XML from the
locally captured templates, which come from our own library:

    md5        <- lib_md5            (also the Persist/<hash2>/<md5> filename)
    len        <- size of the local Persist file
    android*/s60* md5+len <- same md5/len
    cdnurl     <- url_20401
    encrypturl <- url_20403
    externurl  <- url_20402
    externmd5  <- spec_md5 (fallback: aux_md5)   [mapping inferred, not proven]
    width/height = 240 (as in the captured sample)

Usage:
    python send_sticker_own.py [target_wxid] [lib_md5_index]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

TPL = Path(r"<PROJECT_ROOT>\reports\sticker_templates.json")
PERSIST = Path(r"D:\xwechat_files\<WXID_SELF>_dfb4\business\emoticon\Persist")
OUTBOX = Path(r"<PROJECT_ROOT>\wx-basic-bridge\bridge\outbox\next.txt")
CONTROL = Path(r"<PROJECT_ROOT>\wx-basic-bridge\bridge\control")
SELF = "<WXID_SELF>"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def local_size(lib_md5: str) -> int:
    """Persist/<first two chars>/<md5>"""
    p = PERSIST / lib_md5[:2] / lib_md5
    if p.exists():
        return p.stat().st_size
    for cand in PERSIST.glob(f"*/{lib_md5}"):
        return cand.stat().st_size
    return 0


def build_xml(t: dict, target: str, aeskey: str = "", extern_md5: str | None = None) -> str:
    m = t["lib_md5"]
    ln = local_size(m) or 0
    ext = extern_md5 or t.get("spec_md5") or ""
    parts = [
        f'fromusername="{SELF}"',
        f'tousername="{target}"',
        'type="2"',
        'idbuffer="media:0_0"',
        f'md5="{m}"',
        f'len="{ln}"',
        'productid=""',
        f'androidmd5="{m}"',
        f'androidlen="{ln}"',
        f's60v3md5="{m}"',
        f's60v3len="{ln}"',
        f's60v5md5="{m}"',
        f's60v5len="{ln}"',
        f'cdnurl="{esc(t["url_20401"])}"',
        'designerid=""',
        'thumburl=""',
        f'encrypturl="{esc(t["url_20403"])}"',
        f'aeskey="{esc(aeskey)}"',
        f'externurl="{esc(t["url_20402"])}"',
        f'externmd5="{esc(ext)}"',
        'width="240"',
        'height="240"',
        'tpurl=""',
        'tpauthkey=""',
        'attachedtext=""',
        'attachedtextcolor=""',
        'lensid=""',
        'emojiattr=""',
        'linkid=""',
        'desc=""',
    ]
    return "<msg><emoji " + " ".join(parts) + "></emoji></msg>"


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "filehelper"
    pick = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    all_t = json.loads(TPL.read_text(encoding="utf-8"))
    keys = [k for k in all_t.keys() if k.startswith(("lib_",))] if False else list(all_t.keys())
    # the JSON is keyed by model names per md5 group; pick the first flat dict with lib_md5
    items = [v for v in all_t.values() if isinstance(v, dict) and "lib_md5" in v]
    if not items:
        print("no templates found; keys:", list(all_t)[:5])
        return 1
    t = items[pick % len(items)]
    xml = build_xml(t, target)
    print(f"template lib_md5={t['lib_md5']} local_size={local_size(t['lib_md5'])}")
    print(f"xml {len(xml)} bytes")

    seq = str(int(time.time() * 1000))
    OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    OUTBOX.write_text(f"{seq}\t9\t{target}\t47\t{xml}", encoding="utf-8")
    print(f"sent seq={seq} type=47 target={target}")

    deadline = time.time() + 12
    while time.time() < deadline:
        time.sleep(1.0)
        res = CONTROL / f"result_{seq}.json"
        if res.exists():
            print("result:", res.read_text(encoding="utf-8", errors="replace").strip())
            return 0
    print("no result yet")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
