"""解析 msg_dump2.json：完整打印消息对象与子对象的字符串，并拆解 ASN.1 filekey。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SRC = Path(r"<PROJECT_ROOT>\reports\msg_dump2.json")


def der_walk(b: bytes, depth: int = 0, limit: int = 40):
    """极简 DER 遍历，用于看 filekey 的组成。"""
    out = []
    i = 0
    n = 0
    while i < len(b) and n < limit:
        tag = b[i]
        i += 1
        if i >= len(b):
            break
        ln = b[i]
        i += 1
        if ln & 0x80:
            k = ln & 0x7F
            if i + k > len(b):
                break
            ln = int.from_bytes(b[i:i + k], "big")
            i += k
        body = b[i:i + ln]
        if i + ln > len(b):
            body = b[i:]
        name = {0x30: "SEQUENCE", 0x02: "INTEGER", 0x04: "OCTETSTR",
                0x03: "BITSTR", 0x0C: "UTF8STR"}.get(tag, f"tag{tag:#x}")
        if name == "SEQUENCE":
            out.append("  " * depth + f"{name} len={ln}")
            out.extend(der_walk(body, depth + 1, limit - len(out)))
        elif name == "INTEGER":
            v = int.from_bytes(body, "big") if body else 0
            out.append("  " * depth + f"INTEGER {v} (hex {body.hex()})")
        elif name in ("OCTETSTR", "UTF8STR"):
            try:
                txt = body.decode("utf-8")
                inner = None
            except UnicodeDecodeError:
                txt, inner = None, "bin"
            if txt and txt.isprintable():
                out.append("  " * depth + f"{name} len={ln} {txt!r}")
            else:
                out.append("  " * depth + f"{name} len={ln} (bin) {body[:32].hex(' ')}")
                if ln > 0:
                    out.extend(der_walk(body, depth + 1, limit - len(out)))
        else:
            out.append("  " * depth + f"{name} len={ln} {body[:32].hex(' ')}")
        i += ln
        n += 1
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    if not SRC.exists():
        print(f"找不到 {SRC}")
        return 1
    recs = json.loads(SRC.read_text(encoding="utf-8"))
    print(f"提交记录数 {len(recs)}\n")

    seen_urls = set()
    seen_filekeys = set()

    for r in recs:
        print(f"=== 提交 #{r.get('n')} 消息数={r.get('count')} ===")
        if r.get("err"):
            print(f"  遍历失败: {r['err']}")
        for o in r.get("objs") or []:
            print(f"\n  信封 {o['ptr']} vt={o['vt']}")
            for s in o.get("strs") or []:
                print(f"    +{s['off']:#05x} len={s['len']:<5} cap={s['cap']:<7} {s['s']!r}")
            for sub in o.get("subs") or []:
                print(f"\n  子对象 via+{sub['via']:#x} {sub['ptr']} vt={sub['vt']}")
                for s in sub.get("strs") or []:
                    print(f"    +{s['off']:#05x} len={s['len']:<5} cap={s['cap']:<7} {s['s'][:400]!r}")
                    val = s["s"]
                    if "stodownload" in val:
                        seen_urls.add(val)
                        if "filekey=" in val:
                            fk = val.split("filekey=", 1)[1]
                            seen_filekeys.add(fk)
        print()

    print("\n########## filekey 拆解 ##########")
    for fk in sorted(seen_filekeys):
        print(f"\nfilekey = {fk}")
        try:
            b = bytes.fromhex(fk)
            for line in der_walk(b):
                print("   " + line)
        except Exception as e:
            print(f"   解析失败: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
