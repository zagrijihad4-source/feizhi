"""用 Frida 验证 RVA 定位：把运行时 WeChat 进程里 Weixin.dll + RVA 的字节，
与磁盘文件里同一 RVA 的字节逐一对比。

这一步不需要任何人工操作，纯粹确认「模块基址 + 文件 RVA」这套定位在运行时成立，
为后续 hook 采样（图片 XML 构造器）打地基。
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import frida
import pefile

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
IMAGE_BASE = 0x180000000

TARGETS = {
    "image_xml_builder": 0x21806A0,
    "doaddmsg(hooked)": 0x166A6BF,
    "send_call1_text": 0x6A35B0,
    "send_call2": 0xDB40,
    "send_call3": 0x160EBE0,
    "emoticon_parser": 0xA19440,
    "img_xml_vtbl+0": 0x21806A0,
}

SCRIPT = r"""
var results = [];
var MOD = Process.findModuleByName('Weixin.dll');
function grab(name, rva) {
    if (MOD === null) { results.push({name: name, err: 'Weixin.dll not found'}); return; }
    var p = MOD.base.add(rva);
    var bytes = [];
    try {
        var buf = p.readByteArray(16);
        var u8 = new Uint8Array(buf);
        for (var i = 0; i < u8.length; i++) bytes.push(u8[i]);
    } catch (e) {
        results.push({name: name, err: '' + e});
        return;
    }
    results.push({name: name, rva: rva, bytes: bytes});
}
send({kind: 'base', base: MOD === null ? null : MOD.base.toString(),
      size: MOD === null ? 0 : MOD.size});
__TARGETS__
send({kind: 'result', results: results});
"""


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    # 磁盘侧字节
    data = DLL.read_bytes()
    pe = pefile.PE(str(DLL), fast_load=True)
    off_map = {}
    for sec in pe.sections:
        name = sec.Name.rstrip(b"\0").decode("ascii", "replace")
        off_map[name] = (sec.VirtualAddress, sec.Misc_VirtualSize,
                         sec.PointerToRawData, sec.SizeOfRawData)

    def rva_to_off(rva):
        for name, (va, vsz, rp, rs) in off_map.items():
            if va <= rva < va + max(vsz, rs):
                o = rp + (rva - va)
                if o < rp + rs:
                    return o
        return None

    disk = {}
    for label, rva in TARGETS.items():
        o = rva_to_off(rva)
        disk[label] = (rva, data[o:o + 16] if o is not None else None)

    # 找进程
    try:
        device = frida.get_local_device()
        procs = [p for p in device.enumerate_processes() if "weixin" in p.name.lower()]
    except Exception as e:
        print(f"枚举进程失败: {e}")
        return 1
    if not procs:
        print("没找到 Weixin 进程")
        return 1
    print("Weixin 进程:")
    for p in procs:
        print(f"  pid={p.pid}")
    # 选有 hook DLL 的那个（通常 pid 最小/主进程），逐个尝试直到 Weixin.dll 可读
    script_src = SCRIPT.replace("__TARGETS__", "\n".join(
        f"grab({label!r}, {rva});" for label, rva in TARGETS.items()))

    for p in sorted(procs, key=lambda x: -x.pid):
        print(f"\n--- 尝试 attach pid={p.pid} ---")
        try:
            session = frida.attach(p.pid)
        except Exception as e:
            print(f"  attach 失败: {e}")
            continue
        info = {}
        try:
            script = session.create_script(script_src)

            def on_message(msg, payload):
                if msg.get("type") == "send":
                    d = msg["payload"]
                    if d.get("kind") == "base":
                        info["base"] = d
                    elif d.get("kind") == "result":
                        info["results"] = d["results"]

            script.on("message", on_message)
            script.load()
            import time
            time.sleep(1.0)
        except Exception as e:
            print(f"  script 失败: {e}")
            session.detach()
            continue

        if not info.get("results"):
            print("  没拿到结果")
            session.detach()
            continue

        b = info.get("base", {})
        if not b.get("base"):
            print("  该进程未加载 Weixin.dll，跳过")
            session.detach()
            continue
        print(f"  Weixin.dll base = {b.get('base')} size = {b.get('size')}")
        ok_all = True
        for r in info["results"]:
            label = r["name"]
            if "err" in r:
                print(f"  {label:<22} 运行时读取失败: {r['err']}")
                ok_all = False
                continue
            _, dbytes = disk[label]
            rbytes = bytes(r["bytes"])
            same = dbytes is not None and dbytes[:16] == rbytes
            mark = "OK " if same else "差异"
            print(f"  {label:<22} rva={r['rva']:#x}")
            print(f"    磁盘 {dbytes.hex(' ') if dbytes else 'N/A'}")
            print(f"    运行 {rbytes.hex(' ')}  [{mark}]")
            if not same:
                ok_all = False
        session.detach()
        print(f"  => {'全部一致，RVA 定位成立' if ok_all else '存在差异，换下一个进程再试'}")
        if ok_all:
            return 0
        continue
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
