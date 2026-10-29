"""把采样到的 7 次发送固化成「收藏表情模板库」。

输入: <PROJECT_ROOT>\\reports\\string_dump.json   （frida_string_dump.py 的输出）
输出: <PROJECT_ROOT>\\reports\\sticker_templates.json  （每表情的 6 个关键字符串）
      <PROJECT_ROOT>\\reports\\sticker_templates.txt   （人读版，便于核对）

内容对象字段（相对 block，均为 MSVC std::string）：
  0x20  md5        —— 与表情库文件名逐字节相同（主键）
  0x60  spec md5   —— 不在表情库中，服务端相关
  0xe0  CDN 20401  —— URL 的 m= 参数 == block+0x20
  0x100 CDN 20403  —— URL 的 m= 参数是独立 md5
  0x120 md5        —— 独立 md5
  0x140 CDN 20402  —— URL 的 m= 参数是独立 md5
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPORTS = Path(r"<PROJECT_ROOT>\reports")
SRC = REPORTS / "string_dump.json"
OUT_JSON = REPORTS / "sticker_templates.json"
OUT_TXT = REPORTS / "sticker_templates.txt"

FIELDS = [
    ("0x20", "lib_md5"),
    ("0x60", "spec_md5"),
    ("0xe0", "url_20401"),
    ("0x100", "url_20403"),
    ("0x120", "aux_md5"),
    ("0x140", "url_20402"),
]


def m_of(url: str) -> str | None:
    """从 URL 里取 m= 参数。"""
    try:
        q = url.split("?", 1)[1]
        for kv in q.split("&"):
            if kv.startswith("m="):
                return kv[2:]
    except Exception:
        pass
    return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    if not SRC.exists():
        print(f"缺少 {SRC}")
        return 1
    data = json.loads(SRC.read_text(encoding="utf-8"))
    sends = data.get("sends") or []
    print(f"读入 {len(sends)} 条发送记录\n")

    templates: dict[str, dict] = {}
    for s in sends:
        fields: dict[str, str] = {}
        for st in s.get("strings") or []:
            if not isinstance(st, dict):
                continue
            off = st.get("off")
            txt = st.get("text")
            if off is None or not txt:
                continue
            for key, name in FIELDS:
                if off == key:
                    fields[name] = txt
        md5 = fields.get("lib_md5")
        if not md5:
            continue
        env_uuid = ((s.get("env_strings") or {}).get("uuid") or {}).get("text")
        env_recv = ((s.get("env_strings") or {}).get("receiver") or {}).get("text")
        rec = {
            "lib_md5": md5,
            "spec_md5": fields.get("spec_md5"),
            "url_20401": fields.get("url_20401"),
            "url_20403": fields.get("url_20403"),
            "url_20402": fields.get("url_20402"),
            "aux_md5": fields.get("aux_md5"),
            "url_20401_m": m_of(fields.get("url_20401", "")),
            "url_20403_m": m_of(fields.get("url_20403", "")),
            "url_20402_m": m_of(fields.get("url_20402", "")),
            "sample_env_uuid": env_uuid,
            "sample_receiver": env_recv,
            "url_20401_len": len(fields.get("url_20401") or ""),
            "url_20403_len": len(fields.get("url_20403") or ""),
            "url_20402_len": len(fields.get("url_20402") or ""),
            "complete": all(fields.get(k) for _, k in FIELDS),
        }
        templates[md5] = rec

    OUT_JSON.write_text(json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"收藏表情模板库  （共 {len(templates)} 个）", "=" * 70, ""]
    for md5, r in sorted(templates.items()):
        lines.append(f"[{md5}]  完整={r['complete']}")
        lines.append(f"  spec_md5   : {r['spec_md5']}")
        lines.append(f"  aux_md5    : {r['aux_md5']}")
        lines.append(f"  url_20401  : len={r['url_20401_len']}  m={r['url_20401_m']}  (== lib_md5: {r['url_20401_m'] == md5})")
        lines.append(f"  url_20403  : len={r['url_20403_len']}  m={r['url_20403_m']}")
        lines.append(f"  url_20402  : len={r['url_20402_len']}  m={r['url_20402_m']}")
        lines.append(f"  示例 receiver: {r['sample_receiver']}")
        lines.append("")
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")

    print(f"写入 {OUT_JSON}")
    print(f"写入 {OUT_TXT}\n")

    # 关键校验：每个表情的 20401 URL 是否都以自身 md5 为 m=
    ok = sum(1 for md5, r in templates.items() if r["url_20401_m"] == md5)
    print(f"校验：20401 URL 的 m= 与自身 md5 一致的数量 = {ok}/{len(templates)}")

    # 跨表情比对：三个 URL 的 md5 是否互不相同（说明不可推导）
    all_sets = []
    for md5, r in templates.items():
        all_sets.append({
            md5,
            r.get("url_20401_m") or "",
            r.get("url_20403_m") or "",
            r.get("url_20402_m") or "",
            r.get("spec_md5") or "",
            r.get("aux_md5") or "",
        })
    inter = set.intersection(*all_sets) if all_sets else set()
    print(f"校验：全部 {len(templates)} 个表情共有的 md5 值（应为空）= {inter}")
    print("\n结论：若交集为空，说明每个表情的 URL 都含独有 md5，")
    print("      无法用「一套模板只换 block+0x20」覆盖任意表情，必须逐表情持有模板。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
