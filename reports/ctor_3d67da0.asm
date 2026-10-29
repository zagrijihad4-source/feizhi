0x03d67da0  push     rbp
0x03d67da1  push     r15
0x03d67da3  push     r14
0x03d67da5  push     r13
0x03d67da7  push     r12
0x03d67da9  push     rsi
0x03d67daa  push     rdi
0x03d67dab  push     rbx
0x03d67dac  sub      rsp, 0x1c8
0x03d67db3  lea      rbp, [rsp + 0x80]
0x03d67dbb  movaps   xmmword ptr [rbp + 0x130], xmm7
0x03d67dc2  movaps   xmmword ptr [rbp + 0x120], xmm6
0x03d67dc9  mov      qword ptr [rbp + 0x118], 0xfffffffffffffffe
0x03d67dd4  mov      rdi, rcx
0x03d67dd7  xorps    xmm0, xmm0
0x03d67dda  movups   xmmword ptr [rcx], xmm0
0x03d67ddd  mov      qword ptr [rcx + 0x10], 0
0x03d67de5  mov      qword ptr [rbp + 0xf0], rdx
0x03d67dec  mov      rax, qword ptr [rdx]
0x03d67def  test     rax, rax
0x03d67df2  je       0x183d685b6
0x03d67df8  mov      ecx, dword ptr [rax + 0x6c]
0x03d67dfb  mov      qword ptr [rbp + 0x40], rcx
0x03d67dff  test     rcx, rcx
0x03d67e02  mov      qword ptr [rbp + 0xf8], rdi
0x03d67e09  je       0x183d67e29
0x03d67e0b  lea      rdx, [rbp + 0x40]
0x03d67e0f  mov      rcx, rdi
0x03d67e12  call     0x18057df00   ; ->rva 0x57df00
0x03d67e17  nop      
0x03d67e18  mov      rax, qword ptr [rbp + 0xf0]
0x03d67e1f  mov      rax, qword ptr [rax]
0x03d67e22  mov      rdi, qword ptr [rbp + 0xf8]
0x03d67e29  mov      r14, qword ptr [rax + 0x70]
0x03d67e2d  movsxd   rax, dword ptr [rax + 0x78]
0x03d67e31  lea      r15, [r14 + rax*8]
0x03d67e35  movaps   xmm6, xmmword ptr [rip + 0x41f6444]   ; ->rva 0x7f5e280
0x03d67e3c  xorps    xmm7, xmm7
0x03d67e3f  lea      rbx, [rbp + 0x40]
0x03d67e43  jmp      0x183d67e5b   ; ->rva 0x3d67e5b
0x03d67e45  nop      word ptr cs:[rax + rax]
0x03d67e50  add      r14, 8
0x03d67e54  mov      rdi, qword ptr [rbp + 0xf8]
0x03d67e5b  cmp      r14, r15
0x03d67e5e  je       0x183d685b6
0x03d67e64  mov      rsi, qword ptr [r14]
0x03d67e67  movaps   xmmword ptr [rbp + 0x100], xmm6
0x03d67e6e  mov      ecx, 0x1b0
0x03d67e73  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x03d67e78  nop      
0x03d67e79  mov      r12, rax
0x03d67e7c  mov      r13, rax
0x03d67e7f  movabs   rax, 0x100000001
0x03d67e89  mov      qword ptr [r12 + 8], rax
0x03d67e8e  lea      rax, [rip + 0x4674d93]   ; ->rva 0x83dcc28
0x03d67e95  mov      qword ptr [r12], rax
0x03d67e99  lea      rdi, [r12 + 0x10]
0x03d67e9e  lea      rcx, [r12 + 0x18]
0x03d67ea3  mov      r8d, 0x158
0x03d67ea9  xor      edx, edx
0x03d67eab  call     0x18669e3c0   ; ->rva 0x669e3c0
0x03d67eb0  mov      qword ptr [r12 + 0x38], 0xf
0x03d67eb9  movups   xmmword ptr [r12 + 0x40], xmm7
0x03d67ebf  mov      qword ptr [r12 + 0x50], 0
0x03d67ec8  mov      qword ptr [r12 + 0x58], 0xf
0x03d67ed1  movups   xmmword ptr [r12 + 0x60], xmm7
0x03d67ed7  mov      qword ptr [r12 + 0x70], 0
0x03d67ee0  mov      qword ptr [r12 + 0x78], 0xf
0x03d67ee9  movups   xmmword ptr [r12 + 0x80], xmm7
0x03d67ef2  mov      qword ptr [r12 + 0x90], 0
0x03d67efe  mov      qword ptr [r12 + 0x98], 0xf
0x03d67f0a  movups   xmmword ptr [r12 + 0xa0], xmm7
0x03d67f13  mov      qword ptr [r12 + 0xb0], 0
0x03d67f1f  mov      qword ptr [r12 + 0xb8], 0xf
0x03d67f2b  movups   xmmword ptr [r12 + 0xc0], xmm7
0x03d67f34  mov      qword ptr [r12 + 0xd0], 0
0x03d67f40  mov      qword ptr [r12 + 0xd8], 0xf
0x03d67f4c  movups   xmmword ptr [r12 + 0xe0], xmm7
0x03d67f55  mov      qword ptr [r12 + 0xf0], 0
0x03d67f61  mov      qword ptr [r12 + 0xf8], 0xf
0x03d67f6d  movups   xmmword ptr [r12 + 0x100], xmm7
0x03d67f76  mov      qword ptr [r12 + 0x110], 0
0x03d67f82  mov      qword ptr [r12 + 0x118], 0xf
0x03d67f8e  movups   xmmword ptr [r12 + 0x120], xmm7
0x03d67f97  mov      qword ptr [r12 + 0x130], 0
0x03d67fa3  mov      qword ptr [r12 + 0x138], 0xf
0x03d67faf  movups   xmmword ptr [r12 + 0x140], xmm7
0x03d67fb8  mov      qword ptr [r12 + 0x150], 0
0x03d67fc4  mov      qword ptr [r12 + 0x158], 0xf
0x03d67fd0  mov      dword ptr [r12 + 0x168], 0xffffffff
0x03d67fdc  lea      rax, [rip + 0x49ed545]   ; ->rva 0x8755528
0x03d67fe3  mov      qword ptr [r12 + 0x10], rax
0x03d67fe8  movups   xmmword ptr [r12 + 0x170], xmm7
0x03d67ff1  mov      qword ptr [r12 + 0x180], 0
0x03d67ffd  mov      qword ptr [r12 + 0x188], 0xf
0x03d68009  movups   xmmword ptr [r12 + 0x1a0], xmm7
0x03d68012  movups   xmmword ptr [r12 + 0x190], xmm7
0x03d6801b  mov      qword ptr [rbp + 0x100], rdi
0x03d68022  mov      qword ptr [rbp + 0x108], r12
0x03d68029  mov      rax, qword ptr [rsi + 8]
0x03d6802d  add      r12, 0x20
0x03d68031  cmp      r12, rax
0x03d68034  je       0x183d6805d
0x03d68036  cmp      qword ptr [rax + 0x18], 0x10
0x03d6803b  mov      r9, rax
0x03d6803e  jb       0x183d68043
0x03d68040  mov      r9, qword ptr [rax]
0x03d68043  mov      rdi, qword ptr [rax + 0x10]
0x03d68047  cmp      rdi, 0xf
0x03d6804b  jbe      0x183d68110
0x03d68051  mov      rcx, r12
0x03d68054  mov      rdx, rdi
0x03d68057  call     0x180032800   ; ->rva 0x32800
0x03d6805c  nop      
0x03d6805d  mov      rsi, qword ptr [rsi + 0x10]
0x03d68061  test     rsi, rsi
0x03d68064  je       0x183d68135
0x03d6806a  cmp      dword ptr [rsi + 0x10], 0
0x03d6806e  je       0x183d6814a
0x03d68074  movabs   rax, 0xaaaaaaaaaaaaaaaa
0x03d6807e  mov      qword ptr [rbp + 0x90], rax
0x03d68085  movaps   xmmword ptr [rbp + 0x80], xmm6
0x03d6808c  movaps   xmmword ptr [rbp + 0x70], xmm6
0x03d68090  movaps   xmmword ptr [rbp + 0x60], xmm6
0x03d68094  movaps   xmmword ptr [rbp + 0x50], xmm6
0x03d68098  movaps   xmmword ptr [rbp + 0x40], xmm6
0x03d6809c  mov      rcx, rbx
0x03d6809f  call     0x1854bf410   ; ->rva 0x54bf410
0x03d680a4  nop      
0x03d680a5  mov      rax, qword ptr [rsi + 8]
0x03d680a9  cmp      qword ptr [rax + 0x18], 0x10
0x03d680ae  mov      rdx, rax
0x03d680b1  jb       0x183d680b6
0x03d680b3  mov      rdx, qword ptr [rax]
0x03d680b6  mov      r8d, dword ptr [rax + 0x10]
0x03d680ba  mov      rcx, rbx
0x03d680bd  call     0x1805ce2c0   ; ->rva 0x5ce2c0
0x03d680c2  nop      
0x03d680c3  mov      rax, qword ptr [rbp + 0x100]
0x03d680ca  mov      rcx, qword ptr [rbp + 0x50]
0x03d680ce  lea      r13, [rax + 0xd0]
0x03d680d5  cmp      r13, rcx
0x03d680d8  je       0x183d682c5
0x03d680de  cmp      qword ptr [rcx + 0x18], 0x10
0x03d680e3  mov      r9, rcx
0x03d680e6  jb       0x183d680eb
0x03d680e8  mov      r9, qword ptr [rcx]
0x03d680eb  mov      rdi, qword ptr [rcx + 0x10]
0x03d680ef  mov      rcx, qword ptr [rax + 0xe8]
0x03d680f6  cmp      rdi, rcx
0x03d680f9  jbe      0x183d682a0
0x03d680ff  mov      rcx, r13
0x03d68102  mov      rdx, rdi
0x03d68105  call     0x180032800   ; ->rva 0x32800
0x03d6810a  nop      
0x03d6810b  jmp      0x183d682c5   ; ->rva 0x3d682c5
0x03d68110  mov      qword ptr [r13 + 0x30], rdi
0x03d68114  mov      rcx, r12
0x03d68117  mov      rdx, r9
0x03d6811a  mov      r8, rdi
0x03d6811d  call     0x18669dd20   ; ->rva 0x669dd20
0x03d68122  mov      byte ptr [r13 + rdi + 0x20], 0
0x03d68128  mov      rsi, qword ptr [rsi + 0x10]
0x03d6812c  test     rsi, rsi
0x03d6812f  jne      0x183d6806a
0x03d68135  mov      rax, qword ptr [rip + 0x681d6fc]   ; ->rva 0xa585838
0x03d6813c  mov      rsi, qword ptr [rax + 0x10]
0x03d68140  cmp      dword ptr [rsi + 0x10], 0
0x03d68144  jne      0x183d68074
0x03d6814a  mov      ecx, 4
0x03d6814f  call     0x180046ac0   ; ->rva 0x46ac0
0x03d68154  test     eax, eax
0x03d68156  mov      rcx, qword ptr [rbp + 0xf8]
0x03d6815d  je       0x183d68250
0x03d68163  lea      rcx, [rbp + 0xd0]
0x03d6816a  call     0x180046bf0   ; ->rva 0x46bf0
0x03d6816f  nop      
0x03d68170  cmp      qword ptr [rbp + 0xe8], 0x10
0x03d68178  lea      r8, [rbp + 0xd0]
0x03d6817f  jb       0x183d68188
0x03d68181  mov      r8, qword ptr [rbp + 0xd0]
0x03d68188  lea      rax, [rip + 0x49ed67f]   ; ->rva 0x875580e
0x03d6818f  mov      qword ptr [rsp + 0x20], rax
0x03d68194  mov      qword ptr [rsp + 0x38], 0
0x03d6819d  mov      byte ptr [rsp + 0x30], 0
0x03d681a2  mov      dword ptr [rsp + 0x28], 0xff
0x03d681aa  mov      rcx, rbx
0x03d681ad  mov      edx, 4
0x03d681b2  lea      r9, [rip + 0x49ed5cb]   ; ->rva 0x8755784
0x03d681b9  call     0x180046f40   ; ->rva 0x46f40
0x03d681be  nop      
0x03d681bf  movaps   xmmword ptr [rbp + 0x30], xmm7
0x03d681c3  movaps   xmmword ptr [rbp + 0x20], xmm7
0x03d681c7  movaps   xmmword ptr [rbp + 0x10], xmm7
0x03d681cb  movaps   xmmword ptr [rbp], xmm7
0x03d681cf  movaps   xmmword ptr [rbp - 0x10], xmm7
0x03d681d3  movaps   xmmword ptr [rbp - 0x20], xmm7
0x03d681d7  movaps   xmmword ptr [rbp - 0x30], xmm7
0x03d681db  movaps   xmmword ptr [rbp - 0x40], xmm7
0x03d681df  mov      rcx, rbx
0x03d681e2  lea      rdx, [rip + 0x49ed67d]   ; ->rva 0x8755866
0x03d681e9  lea      r8, [rbp - 0x40]
0x03d681ed  call     0x1800474e0   ; ->rva 0x474e0
0x03d681f2  nop      
0x03d681f3  mov      rcx, rbx
0x03d681f6  call     0x180047040   ; ->rva 0x47040
0x03d681fb  mov      rax, qword ptr [rbp + 0xe8]
0x03d68202  cmp      rax, 0x10
0x03d68206  mov      rcx, qword ptr [rbp + 0xf8]
0x03d6820d  jb       0x183d68250
0x03d6820f  mov      rsi, rcx
0x03d68212  mov      rcx, qword ptr [rbp + 0xd0]
0x03d68219  lea      rdx, [rax + 1]
0x03d6821d  cmp      rdx, 0x1000
0x03d68224  jb       0x183d68245
0x03d68226  mov      r8, qword ptr [rcx - 8]
0x03d6822a  add      rcx, -8
0x03d6822e  sub      rcx, r8
0x03d68231  cmp      rcx, 0x20
0x03d68235  jae      0x183d68608
0x03d6823b  add      rax, 0x28
0x03d6823f  mov      rdx, rax
0x03d68242  mov      rcx, r8
0x03d68245  call     0x1864a7d68   ; ->rva 0x64a7d68
0x03d6824a  mov      rcx, rsi
0x03d6824d  nop      dword ptr [rax]
0x03d68250  mov      rdx, qword ptr [rcx + 8]
0x03d68254  cmp      rdx, qword ptr [rcx + 0x10]
0x03d68258  je       0x183d6852f
0x03d6825e  movups   xmmword ptr [rdx], xmm7
0x03d68261  mov      rax, qword ptr [rbp + 0x108]
0x03d68268  test     rax, rax
0x03d6826b  je       0x183d68271
0x03d6826d  lock inc dword ptr [rax + 8]
0x03d68271  mov      rax, qword ptr [rbp + 0x100]
0x03d68278  mov      qword ptr [rdx], rax
0x03d6827b  mov      r13, qword ptr [rbp + 0x108]
0x03d68282  mov      qword ptr [rdx + 8], r13
0x03d68286  mov      rax, qword ptr [rbp + 0xf8]
0x03d6828d  add      qword ptr [rax + 8], 0x10
0x03d68292  test     r13, r13
0x03d68295  jne      0x183d6854c
0x03d6829b  jmp      0x183d67e50   ; ->rva 0x3d67e50
0x03d682a0  cmp      rcx, 0x10
0x03d682a4  jb       0x183d682aa
0x03d682a6  mov      r13, qword ptr [r13]
0x03d682aa  mov      qword ptr [rax + 0xe0], rdi
0x03d682b1  mov      rcx, r13
0x03d682b4  mov      rdx, r9
0x03d682b7  mov      r8, rdi
0x03d682ba  call     0x18669dd20   ; ->rva 0x669dd20
0x03d682bf  mov      byte ptr [r13 + rdi], 0
0x03d682c5  mov      rax, qword ptr [rbp + 0x100]
0x03d682cc  mov      rcx, qword ptr [rbp + 0x58]
0x03d682d0  lea      r13, [rax + 0x70]
0x03d682d4  cmp      r13, rcx
0x03d682d7  je       0x183d68329
0x03d682d9  cmp      qword ptr [rcx + 0x18], 0x10
0x03d682de  mov      r9, rcx
0x03d682e1  jb       0x183d682e6
0x03d682e3  mov      r9, qword ptr [rcx]
0x03d682e6  mov      rdi, qword ptr [rcx + 0x10]
0x03d682ea  mov      rcx, qword ptr [rax + 0x88]
0x03d682f1  cmp      rdi, rcx
0x03d682f4  jbe      0x183d68304
0x03d682f6  mov      rcx, r13
0x03d682f9  mov      rdx, rdi
0x03d682fc  call     0x180032800   ; ->rva 0x32800
0x03d68301  nop      
0x03d68302  jmp      0x183d68329   ; ->rva 0x3d68329
0x03d68304  cmp      rcx, 0x10
0x03d68308  jb       0x183d6830e
0x03d6830a  mov      r13, qword ptr [r13]
0x03d6830e  mov      qword ptr [rax + 0x80], rdi
0x03d68315  mov      rcx, r13
0x03d68318  mov      rdx, r9
0x03d6831b  mov      r8, rdi
0x03d6831e  call     0x18669dd20   ; ->rva 0x669dd20
0x03d68323  mov      byte ptr [r13 + rdi], 0
0x03d68329  mov      rax, qword ptr [rbp + 0x100]
0x03d68330  mov      rcx, qword ptr [rbp + 0x68]
0x03d68334  lea      r13, [rax + 0x130]
0x03d6833b  cmp      r13, rcx
0x03d6833e  je       0x183d68390
0x03d68340  cmp      qword ptr [rcx + 0x18], 0x10
0x03d68345  mov      r9, rcx
0x03d68348  jb       0x183d6834d
0x03d6834a  mov      r9, qword ptr [rcx]
0x03d6834d  mov      rdi, qword ptr [rcx + 0x10]
0x03d68351  mov      rcx, qword ptr [rax + 0x148]
0x03d68358  cmp      rdi, rcx
0x03d6835b  jbe      0x183d6836b
0x03d6835d  mov      rcx, r13
0x03d68360  mov      rdx, rdi
0x03d68363  call     0x180032800   ; ->rva 0x32800
0x03d68368  nop      
0x03d68369  jmp      0x183d68390   ; ->rva 0x3d68390
0x03d6836b  cmp      rcx, 0x10
0x03d6836f  jb       0x183d68375
0x03d68371  mov      r13, qword ptr [r13]
0x03d68375  mov      qword ptr [rax + 0x140], rdi
0x03d6837c  mov      rcx, r13
0x03d6837f  mov      rdx, r9
0x03d68382  mov      r8, rdi
0x03d68385  call     0x18669dd20   ; ->rva 0x669dd20
0x03d6838a  mov      byte ptr [r13 + rdi], 0
0x03d68390  mov      rax, qword ptr [rbp + 0x100]
0x03d68397  mov      rcx, qword ptr [rbp + 0x70]
0x03d6839b  lea      r13, [rax + 0x50]
0x03d6839f  cmp      r13, rcx
0x03d683a2  je       0x183d683ee
0x03d683a4  cmp      qword ptr [rcx + 0x18], 0x10
0x03d683a9  mov      r9, rcx
0x03d683ac  jb       0x183d683b1
0x03d683ae  mov      r9, qword ptr [rcx]
0x03d683b1  mov      rdi, qword ptr [rcx + 0x10]
0x03d683b5  mov      rcx, qword ptr [rax + 0x68]
0x03d683b9  cmp      rdi, rcx
0x03d683bc  jbe      0x183d683cc
0x03d683be  mov      rcx, r13
0x03d683c1  mov      rdx, rdi
0x03d683c4  call     0x180032800   ; ->rva 0x32800
0x03d683c9  nop      
0x03d683ca  jmp      0x183d683ee   ; ->rva 0x3d683ee
0x03d683cc  cmp      rcx, 0x10
0x03d683d0  jb       0x183d683d6
0x03d683d2  mov      r13, qword ptr [r13]
0x03d683d6  mov      qword ptr [rax + 0x60], rdi
0x03d683da  mov      rcx, r13
0x03d683dd  mov      rdx, r9
0x03d683e0  mov      r8, rdi
0x03d683e3  call     0x18669dd20   ; ->rva 0x669dd20
0x03d683e8  mov      byte ptr [r13 + rdi], 0
0x03d683ee  mov      rax, qword ptr [rbp + 0x100]
0x03d683f5  mov      rcx, qword ptr [rbp + 0x78]
0x03d683f9  lea      r13, [rax + 0x30]
0x03d683fd  cmp      r13, rcx
0x03d68400  je       0x183d6844c
0x03d68402  cmp      qword ptr [rcx + 0x18], 0x10
0x03d68407  mov      r9, rcx
0x03d6840a  jb       0x183d6840f
0x03d6840c  mov      r9, qword ptr [rcx]
0x03d6840f  mov      rdi, qword ptr [rcx + 0x10]
0x03d68413  mov      rcx, qword ptr [rax + 0x48]
0x03d68417  cmp      rdi, rcx
0x03d6841a  jbe      0x183d6842a
0x03d6841c  mov      rcx, r13
0x03d6841f  mov      rdx, rdi
0x03d68422  call     0x180032800   ; ->rva 0x32800
0x03d68427  nop      
0x03d68428  jmp      0x183d6844c   ; ->rva 0x3d6844c
0x03d6842a  cmp      rcx, 0x10
0x03d6842e  jb       0x183d68434
0x03d68430  mov      r13, qword ptr [r13]
0x03d68434  mov      qword ptr [rax + 0x40], rdi
0x03d68438  mov      rcx, r13
0x03d6843b  mov      rdx, r9
0x03d6843e  mov      r8, rdi
0x03d68441  call     0x18669dd20   ; ->rva 0x669dd20
0x03d68446  mov      byte ptr [r13 + rdi], 0
0x03d6844c  mov      rax, qword ptr [rbp + 0x100]
0x03d68453  mov      rcx, qword ptr [rbp + 0x80]
0x03d6845a  lea      r13, [rax + 0xf0]
0x03d68461  cmp      r13, rcx
0x03d68464  je       0x183d684b6
0x03d68466  cmp      qword ptr [rcx + 0x18], 0x10
0x03d6846b  mov      r9, rcx
0x03d6846e  jb       0x183d68473
0x03d68470  mov      r9, qword ptr [rcx]
0x03d68473  mov      rdi, qword ptr [rcx + 0x10]
0x03d68477  mov      rcx, qword ptr [rax + 0x108]
0x03d6847e  cmp      rdi, rcx
0x03d68481  jbe      0x183d68491
0x03d68483  mov      rcx, r13
0x03d68486  mov      rdx, rdi
0x03d68489  call     0x180032800   ; ->rva 0x32800
0x03d6848e  nop      
0x03d6848f  jmp      0x183d684b6   ; ->rva 0x3d684b6
0x03d68491  cmp      rcx, 0x10
0x03d68495  jb       0x183d6849b
0x03d68497  mov      r13, qword ptr [r13]
0x03d6849b  mov      qword ptr [rax + 0x100], rdi
0x03d684a2  mov      rcx, r13
0x03d684a5  mov      rdx, r9
0x03d684a8  mov      r8, rdi
0x03d684ab  call     0x18669dd20   ; ->rva 0x669dd20
0x03d684b0  mov      byte ptr [r13 + rdi], 0
0x03d684b6  mov      rax, qword ptr [rbp + 0x100]
0x03d684bd  mov      rcx, qword ptr [rbp + 0x88]
0x03d684c4  lea      r13, [rax + 0x110]
0x03d684cb  cmp      r13, rcx
0x03d684ce  je       0x183d684fd
0x03d684d0  cmp      qword ptr [rcx + 0x18], 0x10
0x03d684d5  mov      r9, rcx
0x03d684d8  jb       0x183d684dd
0x03d684da  mov      r9, qword ptr [rcx]
0x03d684dd  mov      rdi, qword ptr [rcx + 0x10]
0x03d684e1  mov      rcx, qword ptr [rax + 0x128]
0x03d684e8  cmp      rdi, rcx
0x03d684eb  jbe      0x183d6857a
0x03d684f1  mov      rcx, r13
0x03d684f4  mov      rdx, rdi
0x03d684f7  call     0x180032800   ; ->rva 0x32800
0x03d684fc  nop      
0x03d684fd  mov      rax, qword ptr [rbp + 0x100]
0x03d68504  cmp      qword ptr [rax + 0x40], 0
0x03d68509  je       0x183d68512
0x03d6850b  mov      dword ptr [rax + 8], 5
0x03d68512  mov      rcx, rbx
0x03d68515  call     0x1854c09d0   ; ->rva 0x54c09d0
0x03d6851a  mov      rcx, qword ptr [rbp + 0xf8]
0x03d68521  mov      rdx, qword ptr [rcx + 8]
0x03d68525  cmp      rdx, qword ptr [rcx + 0x10]
0x03d68529  jne      0x183d6825e
0x03d6852f  lea      r8, [rbp + 0x100]
0x03d68536  call     0x1801d3b80   ; ->rva 0x1d3b80
0x03d6853b  nop      
0x03d6853c  mov      r13, qword ptr [rbp + 0x108]
0x03d68543  test     r13, r13
0x03d68546  je       0x183d67e50
0x03d6854c  lock dec dword ptr [r13 + 8]
0x03d68551  jne      0x183d67e50
0x03d68557  mov      rax, qword ptr [r13]
0x03d6855b  mov      rcx, r13
0x03d6855e  call     qword ptr [rax]
0x03d68560  lock dec dword ptr [r13 + 0xc]
0x03d68565  jne      0x183d67e50
0x03d6856b  mov      rax, qword ptr [r13]
0x03d6856f  mov      rcx, r13
0x03d68572  call     qword ptr [rax + 8]
0x03d68575  jmp      0x183d67e50   ; ->rva 0x3d67e50
0x03d6857a  cmp      rcx, 0x10
0x03d6857e  jb       0x183d68584
0x03d68580  mov      r13, qword ptr [r13]
0x03d68584  mov      qword ptr [rax + 0x120], rdi
0x03d6858b  mov      rcx, r13
0x03d6858e  mov      rdx, r9
0x03d68591  mov      r8, rdi
0x03d68594  call     0x18669dd20   ; ->rva 0x669dd20
0x03d68599  mov      byte ptr [r13 + rdi], 0
0x03d6859f  mov      rax, qword ptr [rbp + 0x100]
0x03d685a6  cmp      qword ptr [rax + 0x40], 0
0x03d685ab  jne      0x183d6850b
0x03d685b1  jmp      0x183d68512   ; ->rva 0x3d68512
0x03d685b6  mov      rax, qword ptr [rbp + 0xf0]
0x03d685bd  mov      rsi, qword ptr [rax + 8]
0x03d685c1  test     rsi, rsi
0x03d685c4  je       0x183d685e3
0x03d685c6  lock dec dword ptr [rsi + 8]
0x03d685ca  jne      0x183d685e3
0x03d685cc  mov      rax, qword ptr [rsi]
0x03d685cf  mov      rcx, rsi
0x03d685d2  call     qword ptr [rax]
0x03d685d4  lock dec dword ptr [rsi + 0xc]
0x03d685d8  jne      0x183d685e3
0x03d685da  mov      rax, qword ptr [rsi]
0x03d685dd  mov      rcx, rsi
0x03d685e0  call     qword ptr [rax + 8]
0x03d685e3  mov      rax, rdi
0x03d685e6  movaps   xmm6, xmmword ptr [rbp + 0x120]
0x03d685ed  movaps   xmm7, xmmword ptr [rbp + 0x130]
0x03d685f4  add      rsp, 0x1c8
0x03d685fb  pop      rbx
0x03d685fc  pop      rdi
0x03d685fd  pop      rsi
0x03d685fe  pop      r12
0x03d68600  pop      r13
0x03d68602  pop      r14
0x03d68604  pop      r15
0x03d68606  pop      rbp
0x03d68607  ret      
0x03d68608  call     0x186667ee8   ; ->rva 0x6667ee8
0x03d6860d  int3     
0x03d6860e  nop      
0x03d68610  mov      qword ptr [rsp + 0x10], rdx
0x03d68615  push     rbp
0x03d68616  push     r15
0x03d68618  push     r14
0x03d6861a  push     r13
0x03d6861c  push     r12
0x03d6861e  push     rsi
0x03d6861f  push     rdi
0x03d68620  push     rbx
0x03d68621  sub      rsp, 0x68
0x03d68625  lea      rbp, [rdx + 0x80]
0x03d6862c  movaps   xmmword ptr [rsp + 0x40], xmm7
0x03d68631  movaps   xmmword ptr [rsp + 0x50], xmm6
0x03d68636  lea      rcx, [rbp + 0x40]
0x03d6863a  call     0x1854c09d0   ; ->rva 0x54c09d0
0x03d6863f  movaps   xmm6, xmmword ptr [rsp + 0x50]
0x03d68644  movaps   xmm7, xmmword ptr [rsp + 0x40]
0x03d68649  add      rsp, 0x68
0x03d6864d  pop      rbx
0x03d6864e  pop      rdi
0x03d6864f  pop      rsi
0x03d68650  pop      r12
0x03d68652  pop      r13
0x03d68654  pop      r14
0x03d68656  pop      r15
0x03d68658  pop      rbp
0x03d68659  ret      
0x03d6865a  nop      word ptr [rax + rax]
0x03d68660  mov      qword ptr [rsp + 0x10], rdx
0x03d68665  push     rbp
0x03d68666  push     r15
0x03d68668  push     r14
0x03d6866a  push     r13
0x03d6866c  push     r12
0x03d6866e  push     rsi
0x03d6866f  push     rdi
0x03d68670  push     rbx
0x03d68671  sub      rsp, 0x68
0x03d68675  lea      rbp, [rdx + 0x80]
0x03d6867c  movaps   xmmword ptr [rsp + 0x40], xmm7
0x03d68681  movaps   xmmword ptr [rsp + 0x50], xmm6
0x03d68686  lea      rcx, [rbp + 0x40]
0x03d6868a  call     0x180047040   ; ->rva 0x47040
0x03d6868f  movaps   xmm6, xmmword ptr [rsp + 0x50]
0x03d68694  movaps   xmm7, xmmword ptr [rsp + 0x40]
0x03d68699  add      rsp, 0x68
0x03d6869d  pop      rbx
0x03d6869e  pop      rdi
0x03d6869f  pop      rsi
0x03d686a0  pop      r12
0x03d686a2  pop      r13
0x03d686a4  pop      r14
0x03d686a6  pop      r15
0x03d686a8  pop      rbp
0x03d686a9  ret      
0x03d686aa  nop      word ptr [rax + rax]
0x03d686b0  mov      qword ptr [rsp + 0x10], rdx
0x03d686b5  push     rbp
0x03d686b6  push     r15
0x03d686b8  push     r14
0x03d686ba  push     r13
0x03d686bc  push     r12
0x03d686be  push     rsi
0x03d686bf  push     rdi
0x03d686c0  push     rbx
0x03d686c1  sub      rsp, 0x68
0x03d686c5  lea      rbp, [rdx + 0x80]
0x03d686cc  movaps   xmmword ptr [rsp + 0x40], xmm7
0x03d686d1  movaps   xmmword ptr [rsp + 0x50], xmm6
0x03d686d6  lea      rcx, [rbp + 0xd0]
0x03d686dd  call     0x180001ef0   ; ->rva 0x1ef0
0x03d686e2  movaps   xmm6, xmmword ptr [rsp + 0x50]
0x03d686e7  movaps   xmm7, xmmword ptr [rsp + 0x40]
0x03d686ec  add      rsp, 0x68
0x03d686f0  pop      rbx
0x03d686f1  pop      rdi
0x03d686f2  pop      rsi
0x03d686f3  pop      r12
0x03d686f5  pop      r13
0x03d686f7  pop      r14
0x03d686f9  pop      r15
0x03d686fb  pop      rbp
0x03d686fc  ret      
0x03d686fd  nop      dword ptr [rax]
0x03d68700  mov      qword ptr [rsp + 0x10], rdx
0x03d68705  push     rbp
0x03d68706  push     r15
0x03d68708  push     r14
0x03d6870a  push     r13
0x03d6870c  push     r12
0x03d6870e  push     rsi
0x03d6870f  push     rdi
0x03d68710  push     rbx
0x03d68711  sub      rsp, 0x68
0x03d68715  lea      rbp, [rdx + 0x80]
0x03d6871c  movaps   xmmword ptr [rsp + 0x40], xmm7
0x03d68721  movaps   xmmword ptr [rsp + 0x50], xmm6
0x03d68726  lea      rcx, [rbp + 0x100]
0x03d6872d  call     0x180001f60   ; ->rva 0x1f60
0x03d68732  movaps   xmm6, xmmword ptr [rsp + 0x50]
0x03d68737  movaps   xmm7, xmmword ptr [rsp + 0x40]
0x03d6873c  add      rsp, 0x68
0x03d68740  pop      rbx
0x03d68741  pop      rdi
0x03d68742  pop      rsi
0x03d68743  pop      r12
0x03d68745  pop      r13
0x03d68747  pop      r14
0x03d68749  pop      r15
0x03d6874b  pop      rbp
0x03d6874c  ret      
0x03d6874d  nop      dword ptr [rax]
0x03d68750  mov      qword ptr [rsp + 0x10], rdx
0x03d68755  push     rbp
0x03d68756  push     r15
0x03d68758  push     r14
0x03d6875a  push     r13
0x03d6875c  push     r12
0x03d6875e  push     rsi
0x03d6875f  push     rdi
0x03d68760  push     rbx
0x03d68761  sub      rsp, 0x68
0x03d68765  lea      rbp, [rdx + 0x80]
0x03d6876c  movaps   xmmword ptr [rsp + 0x40], xmm7
0x03d68771  movaps   xmmword ptr [rsp + 0x50], xmm6
0x03d68776  mov      rcx, qword ptr [rbp + 0xf8]
0x03d6877d  call     0x1801d4350   ; ->rva 0x1d4350
0x03d68782  mov      rcx, qword ptr [rbp + 0xf0]
0x03d68789  call     0x180001f60   ; ->rva 0x1f60
0x03d6878e  movaps   xmm6, xmmword ptr [rsp + 0x50]
0x03d68793  movaps   xmm7, xmmword ptr [rsp + 0x40]
0x03d68798  add      rsp, 0x68
0x03d6879c  pop      rbx
0x03d6879d  pop      rdi
0x03d6879e  pop      rsi
0x03d6879f  pop      r12
0x03d687a1  pop      r13
0x03d687a3  pop      r14
0x03d687a5  pop      r15
0x03d687a7  pop      rbp
0x03d687a8  ret      
0x03d687a9  int3     
0x03d687aa  int3     
0x03d687ab  int3     
0x03d687ac  int3     
0x03d687ad  int3     
0x03d687ae  int3     
0x03d687af  int3     
0x03d687b0  push     rbp
0x03d687b1  push     r15
0x03d687b3  push     r14
0x03d687b5  push     r13
0x03d687b7  push     r12
0x03d687b9  push     rsi
0x03d687ba  push     rdi
0x03d687bb  push     rbx
0x03d687bc  sub      rsp, 0x98
0x03d687c3  lea      rbp, [rsp + 0x80]
0x03d687cb  movaps   xmmword ptr [rbp], xmm6
0x03d687cf  mov      qword ptr [rbp - 8], 0xfffffffffffffffe
0x03d687d7  mov      r13, rcx
0x03d687da  mov      qword ptr [rbp - 0x10], rdx
0x03d687de  mov      rbx, qword ptr [rdx]
0x03d687e1  test     rbx, rbx
0x03d687e4  je       0x183d68ba2
0x03d687ea  mov      esi, r8d
0x03d687ed  movaps   xmm6, xmmword ptr [rip + 0x41f5a8c]   ; ->rva 0x7f5e280
0x03d687f4  movups   xmmword ptr [r13], xmm6
0x03d687f9  mov      ecx, 0x308
0x03d687fe  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x03d68803  nop      
0x03d68804  mov      rdi, rax
0x03d68807  mov      r12, rax
0x03d6880a  movabs   r15, 0x100000001
0x03d68814  mov      qword ptr [rdi + 8], r15
0x03d68818  lea      rax, [rip + 0x47bddc9]   ; ->rva 0x85265e8
0x03d6881f  mov      qword ptr [rdi], rax
0x03d68822  lea      r14, [rdi + 0x10]
0x03d68826  mov      r8d, 0x2f8
0x03d6882c  mov      rcx, r14
0x03d6882f  xor      edx, edx
0x03d68831  call     0x18669e3c0   ; ->rva 0x669e3c0
0x03d68836  mov      qword ptr [rdi + 0x30], 0xf
0x03d6883e  xorps    xmm0, xmm0
0x03d68841  movups   xmmword ptr [rdi + 0x38], xmm0
0x03d68845  movups   xmmword ptr [rdi + 0x48], xmm0
0x03d68849  mov      qword ptr [rdi + 0x58], 0xf
0x03d68851  movups   xmmword ptr [rdi + 0x60], xmm0
0x03d68855  mov      qword ptr [rdi + 0x70], 0
0x03d6885d  mov      qword ptr [rdi + 0x78], 0xf
0x03d68865  movups   xmmword ptr [rdi + 0x80], xmm0
0x03d6886c  mov      qword ptr [rdi + 0x90], 0
0x03d68877  mov      qword ptr [rdi + 0x98], 0xf
0x03d68882  movups   xmmword ptr [rdi + 0xa0], xmm0
0x03d68889  movups   xmmword ptr [rdi + 0xb0], xmm0
0x03d68890  movups   xmmword ptr [rdi + 0xc0], xmm0
0x03d68897  movups   xmmword ptr [rdi + 0xd0], xmm0
0x03d6889e  movups   xmmword ptr [rdi + 0xe0], xmm0
0x03d688a5  movups   xmmword ptr [rdi + 0xf0], xmm0
0x03d688ac  movups   xmmword ptr [rdi + 0x100], xmm0
0x03d688b3  movups   xmmword ptr [rdi + 0x110], xmm0
0x03d688ba  movups   xmmword ptr [rdi + 0x120], xmm0
0x03d688c1  mov      qword ptr [rdi + 0x130], 0xf
0x03d688cc  movups   xmmword ptr [rdi + 0x148], xmm0
0x03d688d3  movups   xmmword ptr [rdi + 0x138], xmm0
0x03d688da  mov      qword ptr [rdi + 0x158], 0
0x03d688e5  mov      qword ptr [rdi + 0x160], 0xf
0x03d688f0  movups   xmmword ptr [rdi + 0x190], xmm0
0x03d688f7  mov      qword ptr [rdi + 0x1a0], 0
0x03d68902  mov      qword ptr [rdi + 0x16d], 0
0x03d6890d  mov      qword ptr [rdi + 0x168], 0
0x03d68918  mov      qword ptr [rdi + 0x1a8], 0xf
0x03d68923  movups   xmmword ptr [rdi + 0x1c0], xmm0
0x03d6892a  movups   xmmword ptr [rdi + 0x1b0], xmm0
0x03d68931  mov      qword ptr [rdi + 0x1d0], 0
0x03d6893c  mov      qword ptr [rdi + 0x1d8], 0xf
0x03d68947  movups   xmmword ptr [rdi + 0x1e0], xmm0
0x03d6894e  mov      qword ptr [rdi + 0x1f0], 0
0x03d68959  mov      qword ptr [rdi + 0x1f8], 0xf
0x03d68964  movups   xmmword ptr [rdi + 0x208], xmm0
0x03d6896b  mov      qword ptr [rdi + 0x218], 0
0x03d68976  mov      qword ptr [rdi + 0x220], 0xf
0x03d68981  movups   xmmword ptr [rdi + 0x228], xmm0
0x03d68988  mov      qword ptr [rdi + 0x238], 0
0x03d68993  mov      qword ptr [rdi + 0x240], 0xf
0x03d6899e  movups   xmmword ptr [rdi + 0x248], xmm0
