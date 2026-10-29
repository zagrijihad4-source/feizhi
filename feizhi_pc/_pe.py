import struct
p = r"C:\Program Files\Tencent\Weixin\4.1.9.23\Weixin.dll"
with open(p, "rb") as f:
    d = f.read(0x400)
e_lfanew = struct.unpack_from("<I", d, 0x3C)[0]
assert d[e_lfanew:e_lfanew+4] == b"PE\0\0", "not PE"
machine = struct.unpack_from("<H", d, e_lfanew + 4)[0]
opt = e_lfanew + 24
magic = struct.unpack_from("<H", d, opt)[0]
image_base = struct.unpack_from("<Q", d, opt + 24)[0]
print("magic=0x%x machine=0x%x" % (magic, machine))
print("ImageBase = 0x%x" % image_base)
for rva in (0x160EBE0, 0x1677A30, 0x166A6BF, 0x15F35C0, 0x17040A0, 0xDB40):
    print("  RVA 0x%-9x -> VA 0x%x" % (rva, image_base + rva))
