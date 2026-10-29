"""把 sticker_templates.json 转成 C 头文件，供 hook 模块直接嵌入。

输出: <PROJECT_ROOT>\\wx-basic-bridge\\native\\wx_hook_bridge\\src\\include\\wx_sticker_templates.h

生成的结构：
    typedef struct { const char* lib_md5; const char* spec_md5; const char* aux_md5;
                     const char* url_20401; const char* url_20403; const char* url_20402; } wxb_stk_tpl;
    static const wxb_stk_tpl g_wxb_stk_tpls[] = { ... };
    #define WXB_STK_TPL_COUNT 7
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPORTS = Path(r"<PROJECT_ROOT>\reports")
SRC = REPORTS / "sticker_templates.json"
DST = Path(r"<PROJECT_ROOT>\wx-basic-bridge\native\wx_hook_bridge\src\include\wx_sticker_templates.h")


def cstr(s: str | None) -> str:
    if not s:
        return "NULL"
    # C 字符串里 URL 只含安全 ASCII，直接转义反斜杠与引号
    esc = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{esc}"'


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    if not SRC.exists():
        print(f"缺少 {SRC}")
        return 1
    tpls = json.loads(SRC.read_text(encoding="utf-8"))
    if not tpls:
        print("模板库为空")
        return 1

    lines = [
        "/* 自动生成，请勿手改。源: reports/sticker_templates.json",
        " * 生成脚本: <PROJECT_ROOT>\\gen_templates_h.py",
        " *",
        " * 每个模板对应一个用户收藏表情，字段取自真实发送时捕获的内容对象。",
        " * 布局参考 TASK_LOG 第九节：内容对象 0x1B0 字节，控制块 vtable 0x83DCC28，",
        " * 对象体 vtable 0x8755528，12 个 std::string 从 block+0x20 起 stride 0x20。",
        " */",
        "#ifndef WX_STICKER_TEMPLATES_H",
        "#define WX_STICKER_TEMPLATES_H",
        "",
        "typedef struct {",
        "    const char *lib_md5;    /* block+0x20，与表情库文件名一致 */",
        "    const char *spec_md5;   /* block+0x60 */",
        "    const char *aux_md5;    /* block+0x120 */",
        "    const char *url_20401;  /* block+0xe0 */",
        "    const char *url_20403;  /* block+0x100 */",
        "    const char *url_20402;  /* block+0x140 */",
        "} wxb_stk_tpl;",
        "",
        "static const wxb_stk_tpl g_wxb_stk_tpls[] = {",
    ]
    for md5, r in sorted(tpls.items()):
        lines.append(f"    /* {md5} */")
        lines.append(f"    {{ {cstr(r.get('lib_md5'))},")
        lines.append(f"      {cstr(r.get('spec_md5'))},")
        lines.append(f"      {cstr(r.get('aux_md5'))},")
        lines.append(f"      {cstr(r.get('url_20401'))},")
        lines.append(f"      {cstr(r.get('url_20403'))},")
        lines.append(f"      {cstr(r.get('url_20402'))} }},")
    lines += [
        "};",
        "",
        f"#define WXB_STK_TPL_COUNT {len(tpls)}",
        "",
        "#endif /* WX_STICKER_TEMPLATES_H */",
        "",
    ]
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text("\n".join(lines), encoding="utf-8")
    print(f"写入 {DST}")
    print(f"模板数 {len(tpls)}，文件 {DST.stat().st_size} 字节")
    for md5, r in sorted(tpls.items()):
        miss = [k for k, _ in (("lib_md5", 0), ("spec_md5", 0), ("aux_md5", 0),
                              ("url_20401", 0), ("url_20403", 0), ("url_20402", 0))
                if not r.get(k)]
        print(f"  {md5}  缺失字段={miss if miss else '无'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
