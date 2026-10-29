"""只读诊断：比对目标 RVA 的文件原始字节与运行时字节。

用途：判断 0x160EBE0 上的 frida hook 是否真的安装/是否残留。
  · 运行时 == 文件原始  → 没有任何 hook 生效（脚本 attach 静默失败）
  · 运行时 != 文件原始  → 存在 hook（是我们的，还是上一轮强杀留下的残留，再进一步判断）

本脚本不 hook 任何函数、不写任何内存，只读。
用法: python frida_peek.py [rva_hex] [len]
"""
from __future__ import annotations

import sys
from pathlib import Path

import frida

WEIXIN_DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
FALLBACK = Path(r"C:\Program Files\Tencent\Weixin\Weixin.dll")

JS = r"""
const m = Process.getModuleByName("Weixin.dll");
const base = m.base;
const p = base.add(__RVA__);
const bytes = Array.from(new Uint8Array(p.readByteArray(__N__)))
    .map(function (b) { return b.toString(16).padStart(2, "0"); }).join(" ");
send({ hex: bytes, base: base.toString(), size: m.size });
"""


def file_bytes(rva: int, n: int) -> tuple[str, str]:
    dll = WEIXIN_DLL if WEIXIN_DLL.exists() else FALLBACK
    if not dll.exists():
        return ("<dll not found>", str(dll))
    try:
        import pefile  # noqa: PLC0415
    except ImportError:
        return ("<pefile missing>", str(dll))
    pe = pefile.PE(str(dll), fast_load=True)
    off = pe.get_offset_from_rva(rva)
    with open(dll, "rb") as f:
        f.seek(off)
        data = f.read(n)
    hexs = " ".join(f"{b:02x}" for b in data)
    return (hexs, f"{dll}  fileoff=0x{off:x}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    rva = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x160EBE0
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 16

    fhex, where = file_bytes(rva, n)
    print(f"RVA 0x{rva:x}  n={n}")
    print(f"FILE : {fhex}")
    print(f"       ({where})")

    device = frida.get_local_device()
    procs = [p for p in device.enumerate_processes() if p.name.lower() == "weixin.exe"]
    if not procs:
        print("Weixin.exe 未运行")
        return 1

    js = JS.replace("__RVA__", hex(rva)).replace("__N__", str(n))
    got = False
    for p in procs:
        try:
            session = frida.attach(p.pid)
            script = session.create_script(js)
            box = {}

            def on_msg(message, data):  # noqa: ANN001, ARG001
                if message.get("type") == "send":
                    box.update(message.get("payload") or {})
                elif message.get("type") == "error":
                    box["err"] = message.get("description")

            script.on("message", on_msg)
            script.load()
            import time  # noqa: PLC0415
            time.sleep(0.6)
            if "hex" in box:
                mark = "SAME" if box["hex"] == fhex else "DIFFERS"
                print(f"LIVE : {box['hex']}   [pid={p.pid}] <<< {mark}")
                print(f"       base={box.get('base')} size=0x{box.get('size', 0):x}")
                got = True
            elif "err" in box:
                print(f"pid={p.pid}: script error {box['err']}")
            try:
                script.unload()
            except Exception:
                pass
            session.detach()
        except Exception as e:  # noqa: BLE001
            print(f"pid={p.pid} attach 失败: {e}")
    if not got:
        print("(未取到运行时字节)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
