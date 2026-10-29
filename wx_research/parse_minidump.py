"""解析 Windows minidump，提取异常记录与模块列表。

用途：定位微信崩溃的准确位置（异常码 + 崩溃地址 + 所属模块 + RVA），
     以确定我们的对象构造在哪一步出错。

minidump 结构：
  header:  'MDMP' + version + NumberOfStreams + StreamDirectoryRva
  stream:  { StreamType(4), DataSize(4), Rva(4) }
  关键流:
    6  ExceptionStream -> MINIDUMP_EXCEPTION_STREAM
    4  ModuleListStream
    3  ThreadListStream

用法: python parse_minidump.py "C:\\path\\to\\dump.dmp"
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

STREAM_EXCEPTION = 6
STREAM_MODULE_LIST = 4
STREAM_THREAD_LIST = 3
STREAM_SYSTEM_INFO = 7
STREAM_MEMORY_LIST = 5
STREAM_MEMORY64_LIST = 9

# 常见异常码
EXC_NAMES = {
    0xC0000005: "EXCEPTION_ACCESS_VIOLATION",
    0xC000001D: "EXCEPTION_ILLEGAL_INSTRUCTION",
    0xC0000094: "EXCEPTION_INT_DIVIDE_BY_ZERO",
    0xC0000096: "EXCEPTION_PRIV_INSTRUCTION",
    0xC00000FD: "EXCEPTION_STACK_OVERFLOW",
    0xC0000374: "STATUS_HEAP_CORRUPTION",
    0xC0000409: "STATUS_STACK_BUFFER_OVERRUN",
    0x80000003: "EXCEPTION_BREAKPOINT",
    0x80000004: "EXCEPTION_SINGLE_STEP",
    0xE06D7363: "CPP_EXCEPTION (MSVC throw)",
}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
    p = Path(sys.argv[1])
    d = p.read_bytes()
    if d[:4] != b"MDMP":
        print("不是 minidump")
        return 1
    (nstreams,) = struct.unpack_from("<I", d, 8)
    dir_rva, = struct.unpack_from("<I", d, 12)
    print(f"minidump: {p.name}  {len(d)} 字节  streams={nstreams}")

    streams = {}
    for i in range(nstreams):
        st, sz, rva = struct.unpack_from("<III", d, dir_rva + i * 12)
        streams[st] = (sz, rva)

    # ---- 模块列表 ----
    modules = []
    if STREAM_MODULE_LIST in streams:
        _, rva = streams[STREAM_MODULE_LIST]
        (nmod,) = struct.unpack_from("<I", d, rva)
        for i in range(nmod):
            base = rva + 4 + i * 108          # MINIDUMP_MODULE = 0x6C 字节
            mod_base, = struct.unpack_from("<Q", d, base)          # +0x00 BaseOfImage
            mod_size, = struct.unpack_from("<I", d, base + 0x08)   # +0x08 SizeOfImage (32 位)
            name_rva, = struct.unpack_from("<I", d, base + 0x14)   # +0x14 ModuleNameRva
            (nlen,) = struct.unpack_from("<I", d, name_rva)
            name = d[name_rva + 4:name_rva + 4 + nlen].decode("utf-16-le", "replace")
            modules.append((mod_base, mod_size, name))

    # ---- 异常 ----
    if STREAM_EXCEPTION in streams:
        _, rva = streams[STREAM_EXCEPTION]
        tid, _, _ = struct.unpack_from("<III", d, rva)
        rec = rva + 8
        # MINIDUMP_EXCEPTION 的真实布局（以异常记录起点为 0）：
        #   +0x00 ExceptionCode(4)  +0x04 ExceptionFlags(4)
        #   +0x08 ExceptionRecord(8)  +0x10 ExceptionAddress(8)
        #   +0x18 NumberParameters(4) +0x1C 对齐(4)
        #   +0x20 ExceptionInformation[0](8)  +0x28 ExceptionInformation[1](8) ...
        # 早期版本错用 "<IIQI"，把 ExceptionAddress 低 32 位当成 NumberParameters，
        # 参数数组起点也提前了 8 字节 —— 导致把 Information[0]（操作码）当成访问地址。
        code, flags, exc_rec, exc_addr = struct.unpack_from("<IIQQ", d, rec)
        num_params, = struct.unpack_from("<I", d, rec + 0x18)
        params = [struct.unpack_from("<Q", d, rec + 0x20 + i * 8)[0]
                  for i in range(min(num_params, 15))]

        print("\n" + "=" * 70)
        print(f"异常码   : {code:#010x}  {EXC_NAMES.get(code, '(unknown)')}")
        print(f"崩溃地址 : {exc_addr:#018x}   (ExceptionAddress)")
        print(f"参数个数 : {num_params}")
        if code == 0xC0000005 and len(params) >= 2:
            kind = {0: "读取", 1: "写入", 8: "执行(非法跳转/无执行权限)"}.get(params[0], str(params[0]))
            print(f"操作码   : {params[0]}  ({kind})")
            print(f"访问地址 : {params[1]:#018x}   (ExceptionInformation[1])")
            if params[1] == exc_addr:
                print("           ↑ 与崩溃地址相同 ⇒ 执行流本身跳到了该地址")
        print(f"线程 id  : {tid}")

        # 崩溃地址落在哪个模块
        hit = None
        for base, size, name in modules:
            if base <= exc_addr < base + size:
                hit = (base, size, name)
                break
        if hit:
            base, size, name = hit
            rva_hit = exc_addr - base
            print(f"所属模块 : {name}")
            print(f"模块基址 : {base:#018x}   RVA = {rva_hit:#x}   (模块大小 {size:#x})")
            print(f"  → 若为 Weixin.dll，则对应静态地址 RVA {rva_hit:#x}")
        else:
            print("所属模块 : (不在任何已列模块内 —— 可能是被调用后损坏的指针)")

        print("\n-- 异常附加参数 --")
        for i, v in enumerate(params):
            tag = ""
            for base, size, name in modules:
                if base <= v < base + size:
                    tag = f"  <= {name}+{v - base:#x}"
                    break
            print(f"  info[{i}] = {v:#018x}{tag}")
    else:
        print("没有异常流（可能是手动 dump 或非崩溃转储）")

    # ---- 线程上下文（含 RIP/RSP 与关键寄存器）----
    if STREAM_THREAD_LIST in streams:
        _, rva = streams[STREAM_THREAD_LIST]
        (nthread,) = struct.unpack_from("<I", d, rva)
        # MINIDUMP_THREAD = 0x30 字节：ThreadId(4) Suspend(4) PrioClass(4) Prio(4)
        #                    Teb(8) Stack(16) ThreadContext(8: size(4)+rva(4))
        for i in range(nthread):
            base = rva + 4 + i * 0x30
            th_id, = struct.unpack_from("<I", d, base)
            ctx_size, ctx_rva = struct.unpack_from("<II", d, base + 0x28)
            if th_id != tid or ctx_rva == 0 or ctx_size < 0x100:
                continue
            # x64 CONTEXT：Rip @ +0xF8, Rsp @ +0x98, Rbp @ +0xA0
            def reg(off):
                return struct.unpack_from("<Q", d, ctx_rva + off)[0]
            print("\n-- 崩溃线程寄存器（x64 CONTEXT）--")
            for name, off in (("Rip", 0xF8), ("Rsp", 0x98), ("Rbp", 0xA0),
                              ("Rax", 0x78), ("Rcx", 0x80), ("Rdx", 0x88),
                              ("Rbx", 0x90), ("Rsi", 0xA8), ("Rdi", 0xB0),
                              ("R8", 0xB8), ("R9", 0xC0), ("R10", 0xC8),
                              ("R11", 0xD0), ("R12", 0xD8), ("R13", 0xE0),
                              ("R14", 0xE8), ("R15", 0xF0)):
                v = reg(off)
                tag = ""
                for b, s, nm in modules:
                    if b <= v < b + s:
                        tag = f"   <= {nm.rsplit(chr(92), 1)[-1]}+{v - b:#x}"
                        break
                print(f"  {name:4s} = {v:#018x}{tag}")

            # ---- 读栈：用 Rsp 还原返回地址链 ----
            # 先建「虚拟地址 -> dump 文件偏移」映射
            ranges = []
            if STREAM_MEMORY_LIST in streams:
                _, mr = streams[STREAM_MEMORY_LIST]
                (nrange,) = struct.unpack_from("<I", d, mr)
                for k in range(nrange):
                    rb = mr + 4 + k * 16
                    start, = struct.unpack_from("<Q", d, rb)
                    dsz, drva = struct.unpack_from("<II", d, rb + 8)
                    ranges.append((start, dsz, drva))
            if STREAM_MEMORY64_LIST in streams:
                _, mr = streams[STREAM_MEMORY64_LIST]
                nrange, base_rva = struct.unpack_from("<QQ", d, mr)
                cur = base_rva
                for k in range(nrange):
                    rb = mr + 16 + k * 16
                    start, = struct.unpack_from("<Q", d, rb)
                    dsz, = struct.unpack_from("<I", d, rb + 8)
                    ranges.append((start, dsz, cur))
                    cur += (dsz + 15) & ~15

            def read_mem(vaddr, size):
                for start, dsz, drva in ranges:
                    if start <= vaddr and vaddr + size <= start + dsz:
                        off = drva + (vaddr - start)
                        if off + size <= len(d):
                            return d[off:off + size]
                return None

            rsp = reg(0x98)
            print(f"\n-- 栈回溯（Rsp = {rsp:#x}）--")
            blk = read_mem(rsp, 0x100)
            if blk is None:
                print("  （Rsp 所在内存不在 dump 的已捕获范围内）")
            else:
                print(f"  {'slot':>5} {'value':>20}  说明")
                for k in range(0, 0x100, 8):
                    v, = struct.unpack_from("<Q", blk, k)
                    if v == 0:
                        print(f"  {k:>5} {v:#020x}")
                        continue
                    tag = ""
                    for b, s, nm in modules:
                        if b <= v < b + s:
                            tag = f"  <= {nm.rsplit(chr(92), 1)[-1]}+{v - b:#x}"
                            break
                    else:
                        tag = "  (非模块地址)"
                    print(f"  {k:>5} {v:#020x}{tag}")
            break

    # ---- 模块列表（前 25 个最大的）----
    for base, size, name in sorted(modules, key=lambda m: -m[1])[:25]:
        print(f"  {base:#018x}  {size:#010x}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
