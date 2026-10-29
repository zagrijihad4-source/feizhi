"""Send a favourited sticker by replaying a real emoji message XML.

Why this works: WeChat's sticker message is just XML carried in a normal
message record (the receive hook shows `type: 47` with content
`<msg><emoji .../></msg>`). Our text channel (message model + 0xDB40 + pack,
0x160EBE0) is already proven to deliver, and type=1 messages are rendered from
their XML by WeChat. So we replay the captured XML with our own
fromusername/tousername and the sticker type code.

Usage:
    python send_sticker_xml.py [target_wxid]

Source XML is taken from the newest inbox record whose type is 47; a backup of
the raw XML is written next to the report files.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

INBOX = Path(r"<PROJECT_ROOT>\wx-basic-bridge\bridge\inbox")
OUTBOX = Path(r"<PROJECT_ROOT>\wx-basic-bridge\bridge\outbox\next.txt")
CONTROL = Path(r"<PROJECT_ROOT>\wx-basic-bridge\bridge\control")
BACKUP = Path(r"<PROJECT_ROOT>\reports\sticker_xml_sample.xml")
SELF_WXID = "<WXID_SELF>"


def newest_type47() -> tuple[Path, dict]:
    best: tuple[float, Path, dict] | None = None
    for f in INBOX.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if str(d.get("type")) != "47":
            continue
        try:
            mtime = f.stat().st_mtime
        except OSError:
            continue
        if best is None or mtime > best[0]:
            best = (mtime, f, d)
    if not best:
        raise SystemExit("no type=47 record found in inbox")
    return best[1], best[2]


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "filehelper"
    type_code = int(sys.argv[2]) if len(sys.argv) > 2 else 47
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    src, rec = newest_type47()
    xml = rec["content"]
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(xml, encoding="utf-8")
    print(f"source: {src.name}  xml {len(xml)} bytes")
    print(f"  md5={re.search(r'md5=.([0-9a-f]{32})', xml).group(1) if 'md5=' in xml else '?'}")

    # Rewrite the routing attributes for our own send.
    before = xml
    xml = re.sub(r'fromusername="[^"]*"', f'fromusername="{SELF_WXID}"', xml, count=1)
    xml = re.sub(r'tousername="[^"]*"', f'tousername="{target}"', xml, count=1)
    if len(xml) != len(before):
        print("  warning: routing rewrite changed length")

    seq = str(int(time.time() * 1000))
    OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    OUTBOX.write_text(f"{seq}\t9\t{target}\t{type_code}\t{xml}", encoding="utf-8")
    print(f"sent seq={seq} type={type_code} target={target}")

    deadline = time.time() + 12
    while time.time() < deadline:
        time.sleep(1.0)
        res = CONTROL / f"result_{seq}.json"
        if res.exists():
            print("result:", res.read_text(encoding="utf-8", errors="replace").strip())
            return 0
    print("no result yet; check control dir")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
