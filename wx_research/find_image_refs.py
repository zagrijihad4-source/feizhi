"""纯静态定位：找出引用图片/表情消息特征串的代码位置。

不依赖 Frida 运行时基址，不走 Ghidra 全量分析。

原理:
  x64 代码引用字符串用 RIP-relative: lea reg, [rip+disp32]
  指令形如  48 8D <modrm> <disp32>   或   4C 8D <modrm> <disp32>
  modrm 的 mod=00, rm=101 时表示 RIP-relative，
  取值集合 {05,0D,15,1D,25,2D,35,3D}
  目标地址 = 指令地址 + 7 + disp32

  反过来：扫 .text 里所有这类 lea，算出目标地址，
  若目标落在 .rdata 且该地址处正好是我们关心的特征串，
  那这条指令就是「引用该字符串的代码」。

输出写文件，避免刷屏。
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

DLL = Path(r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll")
OUT = Path(r"<PROJECT_ROOT>\reports\image_refs.txt")

# 想定位的特征串（图片 / 表情消息 XML 字段）
# 注意: filekey/aeskey/cdnurl 在 .rdata 里有几十处日志格式串同名前缀，
# 会污染「字符串起点」登记，故不纳入扫描目标，只做参考打印。
NEEDLES = [
    b"cdnthumburl",
    b"cdnbigimgurl",
    b"cdnthumbaeskey",
    b"cdnmidimgurl",
    b"emoticonmd5",
]

# 只对「唯一命中的图片专属串」登记扫描目标
SCAN_STRINGS = {"cdnthumburl", "cdnbigimgurl", "cdnthumbaeskey", "cdnmidimgurl", "emoticonmd5"}

RIP_MODRM = {0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D}


def parse_pe_sections(data: bytes):
    """[(name, va, vsize, rawptr, rawsize)]"""
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_off:pe_off + 4] != b"PE\0\0":
        raise SystemExit("不是有效 PE")
    num_sec = struct.unpack_from("<H", data, pe_off + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe_off + 20)[0]
    sec_off = pe_off + 24 + opt_size
    out = []
    for i in range(num_sec):
        o = sec_off + i * 40
        name = data[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, o + 8)
        out.append((name, va, vsize, rawptr, rawsize))
    return out


def find_section(sections, name):
    for s in sections:
        if s[0] == name:
            return s
    return None


def off_to_rva(sections, off):
    for _n, va, vsize, rawptr, rawsize in sections:
        if rawptr <= off < rawptr + rawsize:
            if off - rawptr < max(vsize, rawsize):
                return va + (off - rawptr)
    return None


def rva_to_off(sections, rva):
    for _n, va, vsize, rawptr, rawsize in sections:
        if va <= rva < va + max(vsize, rawsize):
            return rawptr + (rva - va)
    return None


def main():
    log = []

    def emit(s=""):
        # 控制台是 GBK，替换符会炸；统一降级输出
        try:
            print(s)
        except UnicodeEncodeError:
            print(s.encode("gbk", "replace").decode("gbk", "replace"))
        log.append(s)

    emit(f"目标: {DLL}")
    data = DLL.read_bytes()
    emit(f"文件大小 {len(data):,} 字节")
    sections = parse_pe_sections(data)

    emit("")
    emit("段表:")
    for n, va, vsz, rp, rs in sections:
        emit(f"  {n:<8} VA={va:#010x} VSize={vsz/1048576:7.2f}MB RawPtr={rp:#010x} RawSize={rs/1048576:7.2f}MB")

    # ---- 1) 定位特征串本体（在文件里全量搜，再映射回 RVA）----
    emit("")
    emit("=== 1) 特征串位置 ===")
    str_rvas = {}   # rva -> needle
    for nd in NEEDLES:
        found = []
        start = 0
        while True:
            pos = data.find(nd, start)
            if pos < 0:
                break
            rva = off_to_rva(sections, pos)
            if rva is not None:
                found.append((pos, rva))
            start = pos + 1
            if len(found) > 40:
                break
        if not found:
            emit(f"  {nd.decode():<16} 未找到")
            continue
        for pos, rva in found:
            sec = next((s[0] for s in sections if s[1] <= rva < s[1] + max(s[2], s[4])), "?")
            tail = data[pos:pos + 40].split(b"\0")[0].decode("ascii", "replace")
            emit(f"  {nd.decode():<16} rva={rva:#010x} [{sec}] {tail!r}")
            # 只登记字符串起点（入参引用通常指向串首），且只登记可扫描的串
            if rva not in str_rvas and nd.decode() in SCAN_STRINGS:
                str_rvas[rva] = nd.decode()

    if not str_rvas:
        emit("没有任何特征串可定位，终止")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text("\n".join(log), encoding="utf-8")
        return 1

    # ---- 2) 扫 .text，找 RIP-relative lea 命中这些 RVA ----
    text = find_section(sections, ".text")
    if not text:
        raise SystemExit("找不到 .text")
    _n, tva, tvsz, trp, trs = text
    tsz = min(tvsz, trs if trs else tvsz)
    emit("")
    emit(f"=== 2) 扫描 .text ({tsz/1048576:.1f}MB) ===")

    body = data[trp:trp + tsz]
    n = len(body)
    hits = []
    i = 0
    while i < n - 7:
        b0 = body[i]
        if b0 in (0x48, 0x4C) and body[i + 1] == 0x8D and body[i + 2] in RIP_MODRM:
            disp = struct.unpack_from("<i", body, i + 3)[0]
            instr_rva = tva + i
            tgt_rva = instr_rva + 7 + disp
            if tgt_rva in str_rvas:
                hits.append((instr_rva, str_rvas[tgt_rva], tgt_rva))
            i += 7
            continue
        i += 1

    emit(f"命中 {len(hits)} 处")
    by_str = {}
    for instr_rva, name, tgt in hits:
        by_str.setdefault(name, []).append(instr_rva)

    emit("")
    emit("=== 3) 按特征串汇总 ===")
    for name, addrs in sorted(by_str.items(), key=lambda kv: -len(kv[1])):
        emit(f"  {name:<16} {len(addrs):>3} 处  " + ", ".join(f"{a:#x}" for a in addrs[:12]))

    # ---- 4) 输出每处命中点前后字节，便于反汇编 ----
    emit("")
    emit("=== 4) 命中点上下文（前 32 字节 / 后 32 字节）===")
    for instr_rva, name, _tgt in hits[:60]:
        off = rva_to_off(sections, instr_rva)
        if off is None:
            continue
        chunk = data[max(0, off - 32):off + 32]
        rel = off - max(0, off - 32)
        emit(f"  [{name}] instr_rva={instr_rva:#x}")
        emit("    " + " ".join(f"{b:02X}" for b in chunk[:rel]) + " | " + " ".join(f"{b:02X}" for b in chunk[rel:]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(log), encoding="utf-8")
    print(f"\n报告已写入 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
