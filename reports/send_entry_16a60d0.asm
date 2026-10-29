0x016a60d0  push     rbp
0x016a60d1  push     r15
0x016a60d3  push     r14
0x016a60d5  push     rsi
0x016a60d6  push     rdi
0x016a60d7  push     rbx
0x016a60d8  sub      rsp, 0x368
0x016a60df  lea      rbp, [rsp + 0x80]
0x016a60e7  movaps   xmmword ptr [rbp + 0x2d0], xmm6
0x016a60ee  mov      qword ptr [rbp + 0x2c8], 0xfffffffffffffffe
0x016a60f9  mov      qword ptr [rbp + 0x2c0], r8
0x016a6100  mov      rsi, rdx
0x016a6103  mov      rdi, rcx
0x016a6106  movaps   xmm6, xmmword ptr [rip + 0x68b8173]   ; ->rva 0x7f5e280
0x016a610d  movaps   xmmword ptr [rbp + 0xa0], xmm6
0x016a6114  lea      rdx, [rip + 0x6c2d97c]   ; ->rva 0x82d3a97
0x016a611b  lea      r8, [rip + 0x6c25c2a]   ; ->rva 0x82cbd4c
0x016a6122  lea      rcx, [rbp + 0x130]
0x016a6129  mov      r9d, 0xcd0
0x016a612f  call     0x1801845d0   ; ->rva 0x1845d0
0x016a6134  nop      
0x016a6135  mov      dword ptr [rbp + 0xa0], 2
0x016a613f  mov      qword ptr [rbp + 0xb0], 0
0x016a614a  movaps   xmm0, xmmword ptr [rbp + 0x130]
0x016a6151  movups   xmmword ptr [rbp + 0xb8], xmm0
0x016a6158  xorps    xmm0, xmm0
0x016a615b  movups   xmmword ptr [rbp + 0xc8], xmm0
0x016a6162  mov      qword ptr [rbp + 0xd8], 0
0x016a616d  mov      qword ptr [rbp + 0xe0], 0xf
0x016a6178  call     0x1808fde20   ; ->rva 0x8fde20
0x016a617d  nop      
0x016a617e  mov      qword ptr [rbp + 0xa8], rax
0x016a6185  cmp      qword ptr [rbp + 0xe0], 0x1f
0x016a618d  jae      0x1816a61aa
0x016a618f  lea      r9, [rip + 0x6c21682]   ; "Begin StartSendMessageSyncStage"
0x016a6196  mov      edx, 0x1f
0x016a619b  lea      rcx, [rbp + 0xc8]
0x016a61a2  call     0x180032800   ; ->rva 0x32800
0x016a61a7  nop      
0x016a61a8  jmp      0x1816a61d5   ; ->rva 0x16a61d5
0x016a61aa  mov      rax, qword ptr [rbp + 0xc8]
0x016a61b1  mov      qword ptr [rbp + 0xd8], 0x1f
0x016a61bc  movups   xmm0, xmmword ptr [rip + 0x6c21664]   ; "MessageSyncStage"
0x016a61c3  movups   xmmword ptr [rax + 0xf], xmm0
0x016a61c7  movups   xmm0, xmmword ptr [rip + 0x6c2164a]   ; "Begin StartSendMessageSyncStage"
0x016a61ce  movups   xmmword ptr [rax], xmm0
0x016a61d1  mov      byte ptr [rax + 0x1f], 0
0x016a61d5  mov      rbx, qword ptr [rbp + 0x2c0]
0x016a61dc  mov      rcx, qword ptr [rbx]
0x016a61df  mov      edx, 1
0x016a61e4  call     0x1834f0a50   ; ->rva 0x34f0a50
0x016a61e9  nop      
0x016a61ea  movabs   rax, 0xaaaaaaaaaaaaaaaa
0x016a61f4  mov      qword ptr [rbp + 0x2b0], rax
0x016a61fb  movaps   xmmword ptr [rbp + 0x2a0], xmm6
0x016a6202  movaps   xmmword ptr [rbp + 0x290], xmm6
0x016a6209  movaps   xmmword ptr [rbp + 0x280], xmm6
0x016a6210  xorps    xmm0, xmm0
0x016a6213  movaps   xmmword ptr [rbp + 0xf0], xmm0
0x016a621a  mov      rax, qword ptr [rbx + 8]
0x016a621e  test     rax, rax
0x016a6221  je       0x1816a622d
0x016a6223  lock inc dword ptr [rax + 8]
0x016a6227  mov      rax, qword ptr [rbx + 8]
0x016a622b  jmp      0x1816a622f   ; ->rva 0x16a622f
0x016a622d  xor      eax, eax
0x016a622f  mov      rcx, qword ptr [rbx]
0x016a6232  mov      qword ptr [rbp + 0xf0], rcx
0x016a6239  mov      qword ptr [rbp + 0xf8], rax
0x016a6240  lea      rdx, [rbp + 0x130]
0x016a6247  lea      r8, [rbp + 0xf0]
0x016a624e  mov      rcx, rdi
0x016a6251  call     0x1816a77e0   ; ->rva 0x16a77e0
0x016a6256  nop      
0x016a6257  lea      rbx, [rbp + 0x200]
0x016a625e  lea      rdx, [rbp + 0x280]
0x016a6265  lea      r8, [rbp + 0x130]
0x016a626c  mov      rcx, rbx
0x016a626f  call     0x18165a4c0   ; ->rva 0x165a4c0
0x016a6274  nop      
0x016a6275  mov      r14, qword ptr [rbp + 0x138]
0x016a627c  test     r14, r14
0x016a627f  je       0x1816a62a0
0x016a6281  lock dec dword ptr [r14 + 8]
0x016a6286  jne      0x1816a62a0
0x016a6288  mov      rax, qword ptr [r14]
0x016a628b  mov      rcx, r14
0x016a628e  call     qword ptr [rax]
0x016a6290  lock dec dword ptr [r14 + 0xc]
0x016a6295  jne      0x1816a62a0
0x016a6297  mov      rax, qword ptr [r14]
0x016a629a  mov      rcx, r14
0x016a629d  call     qword ptr [rax + 8]
0x016a62a0  mov      rcx, qword ptr [rbp + 0x2a8]
0x016a62a7  mov      rax, qword ptr [rbp + 0x2c0]
0x016a62ae  mov      rax, qword ptr [rax]
0x016a62b1  xorps    xmm0, xmm0
0x016a62b4  movaps   xmmword ptr [rbp + 0x100], xmm0
0x016a62bb  mov      rdx, qword ptr [rax + 0x20]
0x016a62bf  test     rdx, rdx
0x016a62c2  je       0x1816a62ce
0x016a62c4  lock inc dword ptr [rdx + 8]
0x016a62c8  mov      rdx, qword ptr [rax + 0x20]
0x016a62cc  jmp      0x1816a62d0   ; ->rva 0x16a62d0
0x016a62ce  xor      edx, edx
0x016a62d0  mov      rax, qword ptr [rax + 0x18]
0x016a62d4  mov      qword ptr [rbp + 0x100], rax
0x016a62db  mov      qword ptr [rbp + 0x108], rdx
0x016a62e2  lea      rdx, [rbp + 0x100]
0x016a62e9  call     0x1816a96f0   ; ->rva 0x16a96f0
0x016a62ee  nop      
0x016a62ef  mov      rax, qword ptr [rbp + 0x2c0]
0x016a62f6  mov      rcx, qword ptr [rax]
0x016a62f9  add      rcx, 0x78
0x016a62fd  lea      rdx, [rbp + 0x280]
0x016a6304  call     0x1816a98f0   ; ->rva 0x16a98f0
0x016a6309  nop      
0x016a630a  mov      rax, qword ptr [rbp + 0x2c0]
0x016a6311  mov      rcx, qword ptr [rax]
0x016a6314  lea      r14, [rbp + 0x130]
0x016a631b  mov      rdx, r14
0x016a631e  call     0x1834ef5e0   ; ->rva 0x34ef5e0
0x016a6323  nop      
0x016a6324  xorps    xmm0, xmm0
0x016a6327  movaps   xmmword ptr [rbp + 0x210], xmm0
0x016a632e  movaps   xmmword ptr [rbp + 0x200], xmm0
0x016a6335  mov      ecx, 0x20
0x016a633a  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x016a633f  nop      
0x016a6340  mov      qword ptr [rbp + 0x200], rax
0x016a6347  mov      qword ptr [rbp + 0x210], 0x15
0x016a6352  mov      qword ptr [rbp + 0x218], 0x1f
0x016a635d  movups   xmm0, xmmword ptr [rip + 0x6c214d4]   ; "GetAddSendMessageToDb"
0x016a6364  movups   xmmword ptr [rax], xmm0
0x016a6367  movabs   rcx, 0x62446f5465676173
0x016a6371  mov      qword ptr [rax + 0xd], rcx
0x016a6375  mov      byte ptr [rax + 0x15], 0
0x016a6379  mov      r15, qword ptr [rbp + 0x140]
0x016a6380  cmp      qword ptr [rbp + 0x148], 0x10
0x016a6388  jb       0x1816a6391
0x016a638a  mov      r14, qword ptr [rbp + 0x130]
0x016a6391  cmp      r15, 0xa
0x016a6395  jbe      0x1816a63b4
0x016a6397  mov      qword ptr [rsp + 0x20], r15
0x016a639c  lea      rcx, [rbp + 0x200]
0x016a63a3  mov      rdx, r15
0x016a63a6  mov      r9, r14
0x016a63a9  call     0x180008df0   ; ->rva 0x8df0
0x016a63ae  nop      
0x016a63af  mov      rbx, rax
0x016a63b2  jmp      0x1816a63da   ; ->rva 0x16a63da
0x016a63b4  mov      rcx, rax
0x016a63b7  add      rcx, 0x15
0x016a63bb  lea      rdx, [r15 + 0x15]
0x016a63bf  mov      qword ptr [rbp + 0x210], rdx
0x016a63c6  mov      rdx, r14
0x016a63c9  mov      r8, r15
0x016a63cc  mov      r14, rax
0x016a63cf  call     0x18669dd20   ; ->rva 0x669dd20
0x016a63d4  mov      byte ptr [r14 + r15 + 0x15], 0
0x016a63da  movups   xmm0, xmmword ptr [rbx]
0x016a63dd  movups   xmm1, xmmword ptr [rbx + 0x10]
0x016a63e1  movaps   xmmword ptr [rbp - 0x30], xmm1
0x016a63e5  movaps   xmmword ptr [rbp - 0x40], xmm0
0x016a63e9  mov      qword ptr [rbx + 0x10], 0
0x016a63f1  mov      qword ptr [rbx + 0x18], 0xf
0x016a63f9  mov      byte ptr [rbx], 0
0x016a63fc  lea      rcx, [rbp + 0xa0]
0x016a6403  lea      rdx, [rbp - 0x40]
0x016a6407  mov      r8d, 0x32
0x016a640d  call     0x180e6da50   ; ->rva 0xe6da50
0x016a6412  nop      
0x016a6413  mov      rax, qword ptr [rbp + 0x218]
0x016a641a  cmp      rax, 0x10
0x016a641e  mov      rbx, qword ptr [rbp + 0x2c0]
0x016a6425  jb       0x1816a645f
0x016a6427  mov      rcx, qword ptr [rbp + 0x200]
0x016a642e  lea      rdx, [rax + 1]
0x016a6432  cmp      rdx, 0x1000
0x016a6439  jb       0x1816a645a
0x016a643b  mov      r8, qword ptr [rcx - 8]
0x016a643f  add      rcx, -8
0x016a6443  sub      rcx, r8
0x016a6446  cmp      rcx, 0x20
0x016a644a  jae      0x1816a7227
0x016a6450  add      rax, 0x28
0x016a6454  mov      rdx, rax
0x016a6457  mov      rcx, r8
0x016a645a  call     0x1864a7d68   ; ->rva 0x64a7d68
0x016a645f  mov      rax, qword ptr [rbp + 0x148]
0x016a6466  cmp      rax, 0x10
0x016a646a  jb       0x1816a64a4
0x016a646c  mov      rcx, qword ptr [rbp + 0x130]
0x016a6473  lea      rdx, [rax + 1]
0x016a6477  cmp      rdx, 0x1000
0x016a647e  jb       0x1816a649f
0x016a6480  mov      r8, qword ptr [rcx - 8]
0x016a6484  add      rcx, -8
0x016a6488  sub      rcx, r8
0x016a648b  cmp      rcx, 0x20
0x016a648f  jae      0x1816a7227
0x016a6495  add      rax, 0x28
0x016a6499  mov      rdx, rax
0x016a649c  mov      rcx, r8
0x016a649f  call     0x1864a7d68   ; ->rva 0x64a7d68
0x016a64a4  mov      eax, dword ptr [rbp + 0x284]
0x016a64aa  or       eax, dword ptr [rbp + 0x280]
0x016a64b0  je       0x1816a6725
0x016a64b6  mov      ecx, 4
0x016a64bb  call     0x180046ac0   ; ->rva 0x46ac0
0x016a64c0  test     eax, eax
0x016a64c2  je       0x1816a66f6
0x016a64c8  lea      rdi, [rbp + 0x1c0]
0x016a64cf  mov      rcx, rdi
0x016a64d2  call     0x180046bf0   ; ->rva 0x46bf0
0x016a64d7  nop      
0x016a64d8  cmp      qword ptr [rbp + 0x1d8], 0x10
0x016a64e0  jb       0x1816a64e9
0x016a64e2  mov      rdi, qword ptr [rbp + 0x1c0]
0x016a64e9  lea      rax, [rip + 0x6c263a0]   ; ->rva 0x82cc890
0x016a64f0  mov      qword ptr [rsp + 0x20], rax
0x016a64f5  mov      qword ptr [rsp + 0x38], 0
0x016a64fe  mov      byte ptr [rsp + 0x30], 0
0x016a6503  mov      dword ptr [rsp + 0x28], 0xcd9
0x016a650b  lea      r9, [rip + 0x6c2583a]   ; ->rva 0x82cbd4c
0x016a6512  lea      rcx, [rbp + 0x130]
0x016a6519  mov      edx, 4
0x016a651e  mov      r8, rdi
0x016a6521  call     0x180046f40   ; ->rva 0x46f40
0x016a6526  nop      
0x016a6527  mov      rax, qword ptr [rbp + 0x2c0]
0x016a652e  mov      rcx, qword ptr [rax]
0x016a6531  call     0x1834f0a40   ; ->rva 0x34f0a40
0x016a6536  nop      
0x016a6537  mov      qword ptr [rbp + 0x50], 0
0x016a653f  mov      ecx, 7
0x016a6544  lea      rdx, [rbp + 0x57]
0x016a6548  mov      r8d, 0xcccccccd
0x016a654e  lea      r9, [rip + 0x68b81b5]   ; "ZYXWVUTSRQPONMLKJIHGFEDCBA9876543210123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
0x016a6555  nop      word ptr cs:[rax + rax]
0x016a6560  mov      r10d, eax
0x016a6563  imul     r10, r8
0x016a6567  shr      r10, 0x23
0x016a656b  lea      r11d, [r10 + r10]
0x016a656f  lea      r11d, [r11 + r11*4]
0x016a6573  neg      r11d
0x016a6576  add      r11d, eax
0x016a6579  add      r11d, 0x23
0x016a657d  movzx    r11d, byte ptr [r11 + r9]
0x016a6582  mov      byte ptr [rdx + 1], r11b
0x016a6586  inc      rdx
0x016a6589  inc      rcx
0x016a658c  cmp      eax, 9
0x016a658f  mov      eax, r10d
0x016a6592  ja       0x1816a6560
0x016a6594  lea      rax, [rbp + 0x58]
0x016a6598  mov      byte ptr [rdx + 1], 0
0x016a659c  cmp      rcx, 9
0x016a65a0  mov      r10, qword ptr [rbp + 0x2c0]
0x016a65a7  jb       0x1816a65cc
0x016a65a9  lea      rcx, [rbp + 0x59]
0x016a65ad  nop      dword ptr [rax]
0x016a65b0  movzx    r8d, byte ptr [rdx]
0x016a65b4  movzx    r9d, byte ptr [rcx - 1]
0x016a65b9  mov      byte ptr [rdx], r9b
0x016a65bc  dec      rdx
0x016a65bf  mov      byte ptr [rcx - 1], r8b
0x016a65c3  cmp      rcx, rdx
0x016a65c6  lea      rcx, [rcx + 1]
0x016a65ca  jb       0x1816a65b0
0x016a65cc  mov      qword ptr [rbp + 0x50], rax
0x016a65d0  mov      rcx, qword ptr [r10]
0x016a65d3  lea      rdi, [rbp + 0x1e0]
0x016a65da  mov      rdx, rdi
0x016a65dd  call     0x1834ef5e0   ; ->rva 0x34ef5e0
0x016a65e2  nop      
0x016a65e3  cmp      qword ptr [rbp + 0x1f8], 0x10
0x016a65eb  jb       0x1816a65f4
0x016a65ed  mov      rdi, qword ptr [rbp + 0x1e0]
0x016a65f4  mov      qword ptr [rbp], rdi
0x016a65f8  mov      byte ptr [rbp + 8], 0
0x016a65fc  xorps    xmm0, xmm0
0x016a65ff  movaps   xmmword ptr [rbp + 0x270], xmm0
0x016a6606  movaps   xmmword ptr [rbp + 0x260], xmm0
0x016a660d  movaps   xmmword ptr [rbp + 0x250], xmm0
0x016a6614  movaps   xmmword ptr [rbp + 0x240], xmm0
0x016a661b  movaps   xmmword ptr [rbp + 0x230], xmm0
0x016a6622  movaps   xmmword ptr [rbp + 0x220], xmm0
0x016a6629  movaps   xmmword ptr [rbp + 0x210], xmm0
0x016a6630  mov      rax, rbp
0x016a6633  mov      qword ptr [rbp + 0x200], rax
0x016a663a  lea      rax, [rbp + 0x50]
0x016a663e  mov      qword ptr [rbp + 0x208], rax
0x016a6645  lea      rdx, [rip + 0x6c2d489]   ; ->rva 0x82d3ad5
0x016a664c  lea      rcx, [rbp + 0x130]
0x016a6653  lea      r8, [rbp + 0x200]
0x016a665a  call     0x1800474e0   ; ->rva 0x474e0
0x016a665f  nop      
0x016a6660  mov      rax, qword ptr [rbp + 0x1f8]
0x016a6667  cmp      rax, 0x10
0x016a666b  jb       0x1816a66a5
0x016a666d  mov      rcx, qword ptr [rbp + 0x1e0]
0x016a6674  lea      rdx, [rax + 1]
0x016a6678  cmp      rdx, 0x1000
0x016a667f  jb       0x1816a66a0
0x016a6681  mov      r8, qword ptr [rcx - 8]
0x016a6685  add      rcx, -8
0x016a6689  sub      rcx, r8
0x016a668c  cmp      rcx, 0x20
0x016a6690  jae      0x1816a7227
0x016a6696  add      rax, 0x28
0x016a669a  mov      rdx, rax
0x016a669d  mov      rcx, r8
0x016a66a0  call     0x1864a7d68   ; ->rva 0x64a7d68
0x016a66a5  lea      rcx, [rbp + 0x130]
0x016a66ac  call     0x180047040   ; ->rva 0x47040
0x016a66b1  mov      rax, qword ptr [rbp + 0x1d8]
0x016a66b8  cmp      rax, 0x10
0x016a66bc  jb       0x1816a66f6
0x016a66be  mov      rcx, qword ptr [rbp + 0x1c0]
0x016a66c5  lea      rdx, [rax + 1]
0x016a66c9  cmp      rdx, 0x1000
0x016a66d0  jb       0x1816a66f1
0x016a66d2  mov      r8, qword ptr [rcx - 8]
0x016a66d6  add      rcx, -8
0x016a66da  sub      rcx, r8
0x016a66dd  cmp      rcx, 0x20
0x016a66e1  jae      0x1816a7227
0x016a66e7  add      rax, 0x28
0x016a66eb  mov      rdx, rax
0x016a66ee  mov      rcx, r8
0x016a66f1  call     0x1864a7d68   ; ->rva 0x64a7d68
0x016a66f6  mov      rax, qword ptr [rbp + 0x280]
0x016a66fd  mov      qword ptr [rsi], rax
0x016a6700  xorps    xmm0, xmm0
0x016a6703  movups   xmmword ptr [rsi + 8], xmm0
0x016a6707  movups   xmmword ptr [rsi + 0x18], xmm0
0x016a670b  mov      rdi, qword ptr [rbp + 0x298]
0x016a6712  cmp      qword ptr [rbp + 0x2a0], 0x10
0x016a671a  jb       0x1816a6792
0x016a671c  mov      rbx, qword ptr [rbp + 0x288]
0x016a6723  jmp      0x1816a6799   ; ->rva 0x16a6799
0x016a6725  mov      rcx, qword ptr [rbx]
0x016a6728  call     0x1834f0a60   ; ->rva 0x34f0a60
0x016a672d  nop      
0x016a672e  test     al, al
0x016a6730  je       0x1816a6764
0x016a6732  movaps   xmmword ptr [rbp + 0x1e0], xmm6
0x016a6739  xorps    xmm0, xmm0
0x016a673c  movaps   xmmword ptr [rbp + 0x110], xmm0
0x016a6743  mov      rcx, qword ptr [rbp + 0x2c0]
0x016a674a  mov      rax, qword ptr [rcx + 8]
0x016a674e  test     rax, rax
0x016a6751  je       0x1816a67f0
0x016a6757  lock inc dword ptr [rax + 8]
0x016a675b  mov      rax, qword ptr [rcx + 8]
0x016a675f  jmp      0x1816a67f2   ; ->rva 0x16a67f2
0x016a6764  mov      rax, qword ptr [rbp + 0x2c0]
0x016a676b  mov      rax, qword ptr [rax]
0x016a676e  xorps    xmm0, xmm0
0x016a6771  movaps   xmmword ptr [rbp + 0x130], xmm0
0x016a6778  mov      rcx, qword ptr [rax + 0x20]
0x016a677c  test     rcx, rcx
0x016a677f  je       0x1816a686f
0x016a6785  lock inc dword ptr [rcx + 8]
0x016a6789  mov      rbx, qword ptr [rax + 0x20]
0x016a678d  jmp      0x1816a6871   ; ->rva 0x16a6871
0x016a6792  lea      rbx, [rbp + 0x288]
0x016a6799  test     rdi, rdi
0x016a679c  js       0x1816a722d
0x016a67a2  cmp      rdi, 0xf
0x016a67a6  jbe      0x1816a68f3
0x016a67ac  mov      rax, rdi
0x016a67af  or       rax, 0xf
0x016a67b3  cmp      rax, 0x17
0x016a67b7  mov      r14d, 0x16
0x016a67bd  cmovae   r14, rax
0x016a67c1  cmp      rax, 0xfff
0x016a67c7  jb       0x1816a67e1
0x016a67c9  lea      rcx, [r14 + 0x28]
0x016a67cd  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x016a67d2  nop      
0x016a67d3  test     rax, rax
0x016a67d6  jne      0x1816a6942
0x016a67dc  jmp      0x1816a7227   ; ->rva 0x16a7227
0x016a67e1  lea      rcx, [r14 + 1]
0x016a67e5  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x016a67ea  nop      
0x016a67eb  jmp      0x1816a6aa1   ; ->rva 0x16a6aa1
0x016a67f0  xor      eax, eax
0x016a67f2  mov      rcx, qword ptr [rcx]
0x016a67f5  mov      qword ptr [rbp + 0x110], rcx
0x016a67fc  mov      qword ptr [rbp + 0x118], rax
0x016a6803  lea      rdx, [rbp + 0x1e0]
0x016a680a  lea      r8, [rbp + 0x110]
0x016a6811  mov      rcx, rdi
0x016a6814  call     0x1816a9a80   ; ->rva 0x16a9a80
0x016a6819  nop      
0x016a681a  cmp      qword ptr [rbp + 0x1e0], 0
0x016a6822  je       0x1816a6956
0x016a6828  mov      rax, qword ptr [rbp + 0x2c0]
0x016a682f  mov      rcx, qword ptr [rax]
0x016a6832  mov      edx, 3
0x016a6837  call     0x1834f0a50   ; ->rva 0x34f0a50
0x016a683c  nop      
0x016a683d  mov      rcx, qword ptr [rbp + 0x1e0]
0x016a6844  xorps    xmm0, xmm0
0x016a6847  movaps   xmmword ptr [rbp + 0x120], xmm0
0x016a684e  mov      rdx, qword ptr [rbp + 0x2c0]
0x016a6855  mov      rax, qword ptr [rdx + 8]
0x016a6859  test     rax, rax
0x016a685c  je       0x1816a6afd
0x016a6862  lock inc dword ptr [rax + 8]
0x016a6866  mov      rax, qword ptr [rdx + 8]
0x016a686a  jmp      0x1816a6aff   ; ->rva 0x16a6aff
0x016a686f  xor      ebx, ebx
0x016a6871  mov      rdx, qword ptr [rax + 0x18]
0x016a6875  mov      qword ptr [rbp + 0x130], rdx
0x016a687c  mov      qword ptr [rbp + 0x138], rbx
0x016a6883  mov      rcx, rdi
0x016a6886  call     0x181655da0   ; ->rva 0x1655da0
0x016a688b  nop      
0x016a688c  test     rbx, rbx
0x016a688f  je       0x1816a68ae
0x016a6891  lock dec dword ptr [rbx + 8]
0x016a6895  jne      0x1816a68ae
0x016a6897  mov      rax, qword ptr [rbx]
0x016a689a  mov      rcx, rbx
0x016a689d  call     qword ptr [rax]
0x016a689f  lock dec dword ptr [rbx + 0xc]
0x016a68a3  jne      0x1816a68ae
0x016a68a5  mov      rax, qword ptr [rbx]
0x016a68a8  mov      rcx, rbx
0x016a68ab  call     qword ptr [rax + 8]
0x016a68ae  mov      rax, qword ptr [rbp + 0x280]
0x016a68b5  mov      qword ptr [rsi], rax
0x016a68b8  xorps    xmm0, xmm0
0x016a68bb  movups   xmmword ptr [rsi + 8], xmm0
0x016a68bf  movups   xmmword ptr [rsi + 0x18], xmm0
0x016a68c3  mov      rdi, qword ptr [rbp + 0x298]
0x016a68ca  cmp      qword ptr [rbp + 0x2a0], 0x10
0x016a68d2  jb       0x1816a68dd
0x016a68d4  mov      rbx, qword ptr [rbp + 0x288]
0x016a68db  jmp      0x1816a68e4   ; ->rva 0x16a68e4
0x016a68dd  lea      rbx, [rbp + 0x288]
0x016a68e4  test     rdi, rdi
0x016a68e7  js       0x1816a7233
0x016a68ed  cmp      rdi, 0xf
0x016a68f1  ja       0x1816a690e
0x016a68f3  lea      rax, [rsi + 8]
0x016a68f7  mov      qword ptr [rsi + 0x18], rdi
0x016a68fb  mov      qword ptr [rsi + 0x20], 0xf
0x016a6903  movups   xmm0, xmmword ptr [rbx]
0x016a6906  movups   xmmword ptr [rax], xmm0
0x016a6909  jmp      0x1816a6abe   ; ->rva 0x16a6abe
0x016a690e  mov      rax, rdi
0x016a6911  or       rax, 0xf
0x016a6915  cmp      rax, 0x17
0x016a6919  mov      r14d, 0x16
0x016a691f  cmovae   r14, rax
0x016a6923  cmp      rax, 0xfff
0x016a6929  jb       0x1816a6a97
0x016a692f  lea      rcx, [r14 + 0x28]
0x016a6933  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x016a6938  nop      
0x016a6939  test     rax, rax
0x016a693c  je       0x1816a7227
0x016a6942  mov      rcx, rax
0x016a6945  add      rax, 0x27
0x016a6949  and      rax, 0xffffffffffffffe0
0x016a694d  mov      qword ptr [rax - 8], rcx
0x016a6951  jmp      0x1816a6aa1   ; ->rva 0x16a6aa1
0x016a6956  mov      ecx, 4
0x016a695b  call     0x180046ac0   ; ->rva 0x46ac0
0x016a6960  test     eax, eax
0x016a6962  je       0x1816a6a60
0x016a6968  lea      rdi, [rbp + 0x50]
0x016a696c  mov      rcx, rdi
0x016a696f  call     0x180046bf0   ; ->rva 0x46bf0
0x016a6974  nop      
0x016a6975  cmp      qword ptr [rbp + 0x68], 0x10
0x016a697a  jb       0x1816a6980
0x016a697c  mov      rdi, qword ptr [rbp + 0x50]
0x016a6980  lea      rax, [rip + 0x6c25f09]   ; ->rva 0x82cc890
0x016a6987  mov      qword ptr [rsp + 0x20], rax
0x016a698c  mov      qword ptr [rsp + 0x38], 0
0x016a6995  mov      byte ptr [rsp + 0x30], 0
0x016a699a  mov      dword ptr [rsp + 0x28], 0xce5
0x016a69a2  lea      r9, [rip + 0x6c253a3]   ; ->rva 0x82cbd4c
0x016a69a9  lea      rcx, [rbp + 0x130]
0x016a69b0  mov      edx, 4
0x016a69b5  mov      r8, rdi
0x016a69b8  call     0x180046f40   ; ->rva 0x46f40
0x016a69bd  nop      
0x016a69be  xorps    xmm0, xmm0
0x016a69c1  movaps   xmmword ptr [rbp + 0x270], xmm0
0x016a69c8  movaps   xmmword ptr [rbp + 0x260], xmm0
0x016a69cf  movaps   xmmword ptr [rbp + 0x250], xmm0
0x016a69d6  movaps   xmmword ptr [rbp + 0x240], xmm0
0x016a69dd  movaps   xmmword ptr [rbp + 0x230], xmm0
0x016a69e4  movaps   xmmword ptr [rbp + 0x220], xmm0
0x016a69eb  movaps   xmmword ptr [rbp + 0x210], xmm0
0x016a69f2  movaps   xmmword ptr [rbp + 0x200], xmm0
0x016a69f9  lea      rdx, [rip + 0x6c2d1d6]   ; ->rva 0x82d3bd6
0x016a6a00  lea      rcx, [rbp + 0x130]
0x016a6a07  lea      r8, [rbp + 0x200]
0x016a6a0e  call     0x1800474e0   ; ->rva 0x474e0
0x016a6a13  nop      
0x016a6a14  lea      rcx, [rbp + 0x130]
0x016a6a1b  call     0x180047040   ; ->rva 0x47040
0x016a6a20  mov      rax, qword ptr [rbp + 0x68]
0x016a6a24  cmp      rax, 0x10
0x016a6a28  jb       0x1816a6a60
0x016a6a2a  mov      rcx, qword ptr [rbp + 0x50]
0x016a6a2e  lea      rdx, [rax + 1]
0x016a6a32  cmp      rdx, 0x1000
0x016a6a39  jb       0x1816a6a5a
0x016a6a3b  mov      r8, qword ptr [rcx - 8]
0x016a6a3f  add      rcx, -8
0x016a6a43  sub      rcx, r8
0x016a6a46  cmp      rcx, 0x20
0x016a6a4a  jae      0x1816a7227
0x016a6a50  add      rax, 0x28
0x016a6a54  mov      rdx, rax
0x016a6a57  mov      rcx, r8
0x016a6a5a  call     0x1864a7d68   ; ->rva 0x64a7d68
0x016a6a5f  nop      
0x016a6a60  mov      dword ptr [rsp + 0x20], 4
0x016a6a68  mov      rcx, rsi
0x016a6a6b  mov      edx, 1
0x016a6a70  mov      r8d, 1
0x016a6a76  mov      r9d, 4
0x016a6a7c  call     0x1834ec1c0   ; ->rva 0x34ec1c0
0x016a6a81  nop      
0x016a6a82  mov      rdi, qword ptr [rbp + 0x1e8]
0x016a6a89  test     rdi, rdi
0x016a6a8c  jne      0x1816a7114
0x016a6a92  jmp      0x1816a7131   ; ->rva 0x16a7131
0x016a6a97  lea      rcx, [r14 + 1]
0x016a6a9b  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x016a6aa0  nop      
0x016a6aa1  mov      qword ptr [rsi + 8], rax
0x016a6aa5  mov      qword ptr [rsi + 0x18], rdi
0x016a6aa9  mov      qword ptr [rsi + 0x20], r14
0x016a6aad  inc      rdi
0x016a6ab0  mov      rcx, rax
0x016a6ab3  mov      rdx, rbx
0x016a6ab6  mov      r8, rdi
0x016a6ab9  call     0x18669dd20   ; ->rva 0x669dd20
0x016a6abe  xorps    xmm0, xmm0
0x016a6ac1  movups   xmmword ptr [rsi + 0x28], xmm0
0x016a6ac5  mov      rax, qword ptr [rbp + 0x2b0]
0x016a6acc  test     rax, rax
0x016a6acf  je       0x1816a6ade
0x016a6ad1  lock inc dword ptr [rax + 8]
0x016a6ad5  mov      rdi, qword ptr [rbp + 0x2b0]
0x016a6adc  jmp      0x1816a6ae0   ; ->rva 0x16a6ae0
0x016a6ade  xor      edi, edi
0x016a6ae0  mov      rax, qword ptr [rbp + 0x2a8]
0x016a6ae7  mov      qword ptr [rsi + 0x28], rax
0x016a6aeb  mov      qword ptr [rsi + 0x30], rdi
0x016a6aef  test     rdi, rdi
0x016a6af2  jne      0x1816a713d
0x016a6af8  jmp      0x1816a715a   ; ->rva 0x16a715a
0x016a6afd  xor      eax, eax
0x016a6aff  mov      rdx, qword ptr [rdx]
0x016a6b02  mov      qword ptr [rbp + 0x120], rdx
0x016a6b09  mov      qword ptr [rbp + 0x128], rax
0x016a6b10  lea      rdx, [rbp + 0x130]
0x016a6b17  lea      r8, [rbp + 0x120]
0x016a6b1e  call     0x1834e0030   ; ->rva 0x34e0030
0x016a6b23  nop      
0x016a6b24  mov      rax, qword ptr [rbp + 0x130]
0x016a6b2b  mov      rbx, qword ptr [rbp + 0x148]
0x016a6b32  mov      qword ptr [rbp + 0x280], rax
0x016a6b39  cmp      qword ptr [rbp + 0x150], 0x10
0x016a6b41  jb       0x1816a6b89
0x016a6b43  mov      r9, qword ptr [rbp + 0x138]
0x016a6b4a  lea      rdi, [rbp + 0x288]
0x016a6b51  mov      rax, qword ptr [rbp + 0x2a0]
0x016a6b58  cmp      rbx, rax
0x016a6b5b  ja       0x1816a6ba3
0x016a6b5d  mov      r14, rdi
0x016a6b60  cmp      rax, 0x10
0x016a6b64  jb       0x1816a6b6d
0x016a6b66  mov      r14, qword ptr [rbp + 0x288]
0x016a6b6d  mov      qword ptr [rbp + 0x298], rbx
0x016a6b74  mov      rcx, r14
0x016a6b77  mov      rdx, r9
0x016a6b7a  mov      r8, rbx
0x016a6b7d  call     0x18669dd20   ; ->rva 0x669dd20
0x016a6b82  mov      byte ptr [r14 + rbx], 0
0x016a6b87  jmp      0x1816a6baf   ; ->rva 0x16a6baf
0x016a6b89  lea      r9, [rbp + 0x138]
0x016a6b90  lea      rdi, [rbp + 0x288]
0x016a6b97  mov      rax, qword ptr [rbp + 0x2a0]
0x016a6b9e  cmp      rbx, rax
0x016a6ba1  jbe      0x1816a6b5d
0x016a6ba3  mov      rcx, rdi
0x016a6ba6  mov      rdx, rbx
0x016a6ba9  call     0x180032800   ; ->rva 0x32800
0x016a6bae  nop      
0x016a6baf  mov      rax, qword ptr [rbp + 0x160]
0x016a6bb6  test     rax, rax
0x016a6bb9  je       0x1816a6bc8
0x016a6bbb  lock inc dword ptr [rax + 8]
0x016a6bbf  mov      rax, qword ptr [rbp + 0x160]
0x016a6bc6  jmp      0x1816a6bca   ; ->rva 0x16a6bca
0x016a6bc8  xor      eax, eax
0x016a6bca  mov      r14, qword ptr [rbp + 0x2c0]
0x016a6bd1  mov      rcx, qword ptr [rbp + 0x158]
0x016a6bd8  mov      qword ptr [rbp + 0x2a8], rcx
0x016a6bdf  mov      rbx, qword ptr [rbp + 0x2b0]
0x016a6be6  mov      qword ptr [rbp + 0x2b0], rax
0x016a6bed  test     rbx, rbx
0x016a6bf0  je       0x1816a6c0f
0x016a6bf2  lock dec dword ptr [rbx + 8]
0x016a6bf6  jne      0x1816a6c0f
0x016a6bf8  mov      rax, qword ptr [rbx]
0x016a6bfb  mov      rcx, rbx
0x016a6bfe  call     qword ptr [rax]
0x016a6c00  lock dec dword ptr [rbx + 0xc]
0x016a6c04  jne      0x1816a6c0f
0x016a6c06  mov      rax, qword ptr [rbx]
0x016a6c09  mov      rcx, rbx
0x016a6c0c  call     qword ptr [rax + 8]
0x016a6c0f  mov      rbx, qword ptr [rbp + 0x160]
0x016a6c16  test     rbx, rbx
0x016a6c19  je       0x1816a6c38
0x016a6c1b  lock dec dword ptr [rbx + 8]
0x016a6c1f  jne      0x1816a6c38
0x016a6c21  mov      rax, qword ptr [rbx]
0x016a6c24  mov      rcx, rbx
0x016a6c27  call     qword ptr [rax]
0x016a6c29  lock dec dword ptr [rbx + 0xc]
0x016a6c2d  jne      0x1816a6c38
0x016a6c2f  mov      rax, qword ptr [rbx]
0x016a6c32  mov      rcx, rbx
0x016a6c35  call     qword ptr [rax + 8]
0x016a6c38  mov      rax, qword ptr [rbp + 0x150]
0x016a6c3f  cmp      rax, 0x10
0x016a6c43  jb       0x1816a6c7d
0x016a6c45  mov      rcx, qword ptr [rbp + 0x138]
0x016a6c4c  lea      rdx, [rax + 1]
0x016a6c50  cmp      rdx, 0x1000
0x016a6c57  jb       0x1816a6c78
0x016a6c59  mov      r8, qword ptr [rcx - 8]
0x016a6c5d  add      rcx, -8
0x016a6c61  sub      rcx, r8
0x016a6c64  cmp      rcx, 0x20
0x016a6c68  jae      0x1816a7227
0x016a6c6e  add      rax, 0x28
0x016a6c72  mov      rdx, rax
0x016a6c75  mov      rcx, r8
0x016a6c78  call     0x1864a7d68   ; ->rva 0x64a7d68
0x016a6c7d  mov      rcx, qword ptr [r14]
0x016a6c80  lea      rbx, [rbp + 0x130]
0x016a6c87  mov      rdx, rbx
0x016a6c8a  call     0x1834ef5e0   ; ->rva 0x34ef5e0
0x016a6c8f  nop      
0x016a6c90  xorps    xmm0, xmm0
0x016a6c93  movaps   xmmword ptr [rbp + 0x210], xmm0
0x016a6c9a  movaps   xmmword ptr [rbp + 0x200], xmm0
0x016a6ca1  mov      ecx, 0x20
0x016a6ca6  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x016a6cab  nop      
0x016a6cac  mov      qword ptr [rbp + 0x200], rax
0x016a6cb3  mov      qword ptr [rbp + 0x210], 0x14
0x016a6cbe  mov      qword ptr [rbp + 0x218], 0x1f
0x016a6cc9  movups   xmm0, xmmword ptr [rip + 0x6c20b7e]   ; "CoPrepareShowMessage"
0x016a6cd0  movups   xmmword ptr [rax], xmm0
0x016a6cd3  mov      dword ptr [rax + 0x10], 0x65676173
0x016a6cda  mov      byte ptr [rax + 0x14], 0
0x016a6cde  mov      r14, qword ptr [rbp + 0x140]
0x016a6ce5  cmp      qword ptr [rbp + 0x148], 0x10
0x016a6ced  jb       0x1816a6cf6
0x016a6cef  mov      rbx, qword ptr [rbp + 0x130]
0x016a6cf6  cmp      r14, 0xb
0x016a6cfa  jbe      0x1816a6d16
0x016a6cfc  mov      qword ptr [rsp + 0x20], r14
0x016a6d01  lea      rcx, [rbp + 0x200]
0x016a6d08  mov      rdx, r14
0x016a6d0b  mov      r9, rbx
0x016a6d0e  call     0x180008df0   ; ->rva 0x8df0
0x016a6d13  nop      
0x016a6d14  jmp      0x1816a6d43   ; ->rva 0x16a6d43
0x016a6d16  mov      rcx, rax
0x016a6d19  add      rcx, 0x14
0x016a6d1d  lea      rdx, [r14 + 0x14]
0x016a6d21  mov      qword ptr [rbp + 0x210], rdx
0x016a6d28  mov      rdx, rbx
0x016a6d2b  mov      r8, r14
0x016a6d2e  mov      rbx, rax
0x016a6d31  call     0x18669dd20   ; ->rva 0x669dd20
0x016a6d36  mov      byte ptr [rbx + r14 + 0x14], 0
0x016a6d3c  lea      rax, [rbp + 0x200]
0x016a6d43  movups   xmm0, xmmword ptr [rax]
0x016a6d46  movups   xmm1, xmmword ptr [rax + 0x10]
0x016a6d4a  movaps   xmmword ptr [rbp - 0x10], xmm1
0x016a6d4e  movaps   xmmword ptr [rbp - 0x20], xmm0
0x016a6d52  mov      qword ptr [rax + 0x10], 0
0x016a6d5a  mov      qword ptr [rax + 0x18], 0xf
0x016a6d62  mov      byte ptr [rax], 0
0x016a6d65  lea      rcx, [rbp + 0xa0]
0x016a6d6c  lea      rdx, [rbp - 0x20]
0x016a6d70  mov      r8d, 0x32
0x016a6d76  call     0x180e6da50   ; ->rva 0xe6da50
0x016a6d7b  nop      
0x016a6d7c  mov      rax, qword ptr [rbp + 0x218]
0x016a6d83  cmp      rax, 0x10
0x016a6d87  jb       0x1816a6dc1
0x016a6d89  mov      rcx, qword ptr [rbp + 0x200]
0x016a6d90  lea      rdx, [rax + 1]
0x016a6d94  cmp      rdx, 0x1000
0x016a6d9b  jb       0x1816a6dbc
0x016a6d9d  mov      r8, qword ptr [rcx - 8]
0x016a6da1  add      rcx, -8
0x016a6da5  sub      rcx, r8
0x016a6da8  cmp      rcx, 0x20
0x016a6dac  jae      0x1816a7227
0x016a6db2  add      rax, 0x28
0x016a6db6  mov      rdx, rax
0x016a6db9  mov      rcx, r8
0x016a6dbc  call     0x1864a7d68   ; ->rva 0x64a7d68
0x016a6dc1  mov      rax, qword ptr [rbp + 0x148]
0x016a6dc8  cmp      rax, 0x10
0x016a6dcc  jb       0x1816a6e06
0x016a6dce  mov      rcx, qword ptr [rbp + 0x130]
0x016a6dd5  lea      rdx, [rax + 1]
0x016a6dd9  cmp      rdx, 0x1000
0x016a6de0  jb       0x1816a6e01
0x016a6de2  mov      r8, qword ptr [rcx - 8]
0x016a6de6  add      rcx, -8
0x016a6dea  sub      rcx, r8
0x016a6ded  cmp      rcx, 0x20
0x016a6df1  jae      0x1816a7227
0x016a6df7  add      rax, 0x28
0x016a6dfb  mov      rdx, rax
0x016a6dfe  mov      rcx, r8
0x016a6e01  call     0x1864a7d68   ; ->rva 0x64a7d68
0x016a6e06  mov      eax, dword ptr [rbp + 0x284]
0x016a6e0c  or       eax, dword ptr [rbp + 0x280]
0x016a6e12  je       0x1816a700c
0x016a6e18  mov      ecx, 4
0x016a6e1d  call     0x180046ac0   ; ->rva 0x46ac0
0x016a6e22  test     eax, eax
0x016a6e24  je       0x1816a6fa3
0x016a6e2a  mov      rbx, rbp
0x016a6e2d  mov      rcx, rbx
0x016a6e30  call     0x180046bf0   ; ->rva 0x46bf0
0x016a6e35  nop      
0x016a6e36  cmp      qword ptr [rbp + 0x18], 0x10
0x016a6e3b  jb       0x1816a6e41
0x016a6e3d  mov      rbx, qword ptr [rbp]
0x016a6e41  lea      rax, [rip + 0x6c25a48]   ; ->rva 0x82cc890
0x016a6e48  mov      qword ptr [rsp + 0x20], rax
0x016a6e4d  mov      qword ptr [rsp + 0x38], 0
0x016a6e56  mov      byte ptr [rsp + 0x30], 0
0x016a6e5b  mov      dword ptr [rsp + 0x28], 0xced
0x016a6e63  lea      r9, [rip + 0x6c24ee2]   ; ->rva 0x82cbd4c
0x016a6e6a  lea      rcx, [rbp + 0x130]
0x016a6e71  mov      edx, 4
0x016a6e76  mov      r8, rbx
0x016a6e79  call     0x180046f40   ; ->rva 0x46f40
0x016a6e7e  nop      
0x016a6e7f  mov      rax, qword ptr [rbp + 0x2c0]
0x016a6e86  mov      rcx, qword ptr [rax]
0x016a6e89  lea      rbx, [rbp + 0x1c0]
0x016a6e90  mov      rdx, rbx
0x016a6e93  call     0x1834ef5e0   ; ->rva 0x34ef5e0
0x016a6e98  nop      
0x016a6e99  cmp      qword ptr [rbp + 0x1d8], 0x10
0x016a6ea1  jb       0x1816a6eaa
0x016a6ea3  mov      rbx, qword ptr [rbp + 0x1c0]
0x016a6eaa  mov      qword ptr [rbp + 0x50], rbx
0x016a6eae  mov      byte ptr [rbp + 0x58], 0
0x016a6eb2  xorps    xmm0, xmm0
0x016a6eb5  movaps   xmmword ptr [rbp + 0x200], xmm0
0x016a6ebc  movaps   xmmword ptr [rbp + 0x270], xmm0
0x016a6ec3  movaps   xmmword ptr [rbp + 0x260], xmm0
0x016a6eca  movaps   xmmword ptr [rbp + 0x250], xmm0
0x016a6ed1  movaps   xmmword ptr [rbp + 0x240], xmm0
0x016a6ed8  movaps   xmmword ptr [rbp + 0x230], xmm0
0x016a6edf  movaps   xmmword ptr [rbp + 0x220], xmm0
0x016a6ee6  movaps   xmmword ptr [rbp + 0x210], xmm0
0x016a6eed  lea      rax, [rbp + 0x50]
0x016a6ef1  mov      qword ptr [rbp + 0x200], rax
0x016a6ef8  lea      rdx, [rip + 0x6c2cd03]   ; ->rva 0x82d3c02
0x016a6eff  lea      rcx, [rbp + 0x130]
0x016a6f06  lea      r8, [rbp + 0x200]
0x016a6f0d  call     0x1800474e0   ; ->rva 0x474e0
0x016a6f12  nop      
0x016a6f13  mov      rax, qword ptr [rbp + 0x1d8]
0x016a6f1a  cmp      rax, 0x10
0x016a6f1e  jb       0x1816a6f58
0x016a6f20  mov      rcx, qword ptr [rbp + 0x1c0]
0x016a6f27  lea      rdx, [rax + 1]
0x016a6f2b  cmp      rdx, 0x1000
0x016a6f32  jb       0x1816a6f53
0x016a6f34  mov      r8, qword ptr [rcx - 8]
0x016a6f38  add      rcx, -8
0x016a6f3c  sub      rcx, r8
0x016a6f3f  cmp      rcx, 0x20
0x016a6f43  jae      0x1816a7227
0x016a6f49  add      rax, 0x28
0x016a6f4d  mov      rdx, rax
0x016a6f50  mov      rcx, r8
0x016a6f53  call     0x1864a7d68   ; ->rva 0x64a7d68
0x016a6f58  lea      rcx, [rbp + 0x130]
0x016a6f5f  call     0x180047040   ; ->rva 0x47040
0x016a6f64  mov      rax, qword ptr [rbp + 0x18]
0x016a6f68  cmp      rax, 0x10
0x016a6f6c  jb       0x1816a6fa3
0x016a6f6e  mov      rcx, qword ptr [rbp]
0x016a6f72  lea      rdx, [rax + 1]
0x016a6f76  cmp      rdx, 0x1000
0x016a6f7d  jb       0x1816a6f9e
0x016a6f7f  mov      r8, qword ptr [rcx - 8]
0x016a6f83  add      rcx, -8
0x016a6f87  sub      rcx, r8
0x016a6f8a  cmp      rcx, 0x20
0x016a6f8e  jae      0x1816a7227
0x016a6f94  add      rax, 0x28
0x016a6f98  mov      rdx, rax
0x016a6f9b  mov      rcx, r8
0x016a6f9e  call     0x1864a7d68   ; ->rva 0x64a7d68
0x016a6fa3  mov      rax, qword ptr [rbp + 0x280]
0x016a6faa  mov      qword ptr [rsi], rax
0x016a6fad  xorps    xmm0, xmm0
0x016a6fb0  movups   xmmword ptr [rsi + 8], xmm0
0x016a6fb4  movups   xmmword ptr [rsi + 0x18], xmm0
0x016a6fb8  mov      rbx, qword ptr [rbp + 0x298]
0x016a6fbf  cmp      qword ptr [rbp + 0x2a0], 0x10
0x016a6fc7  jb       0x1816a6fd0
0x016a6fc9  mov      rdi, qword ptr [rbp + 0x288]
0x016a6fd0  test     rbx, rbx
0x016a6fd3  js       0x1816a723f
0x016a6fd9  cmp      rbx, 0xf
0x016a6fdd  jbe      0x1816a7048
0x016a6fdf  mov      rax, rbx
0x016a6fe2  or       rax, 0xf
0x016a6fe6  cmp      rax, 0x17
0x016a6fea  mov      r14d, 0x16
0x016a6ff0  cmovae   r14, rax
0x016a6ff4  cmp      rax, 0xfff
0x016a6ffa  jb       0x1816a70ad
0x016a7000  lea      rcx, [r14 + 0x28]
0x016a7004  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x016a7009  nop      
0x016a700a  jmp      0x1816a7087   ; ->rva 0x16a7087
0x016a700c  mov      rax, qword ptr [rbp + 0x280]
0x016a7013  mov      qword ptr [rsi], rax
0x016a7016  xorps    xmm0, xmm0
0x016a7019  movups   xmmword ptr [rsi + 8], xmm0
0x016a701d  movups   xmmword ptr [rsi + 0x18], xmm0
0x016a7021  mov      rbx, qword ptr [rbp + 0x298]
0x016a7028  cmp      qword ptr [rbp + 0x2a0], 0x10
0x016a7030  jb       0x1816a7039
0x016a7032  mov      rdi, qword ptr [rbp + 0x288]
0x016a7039  test     rbx, rbx
0x016a703c  js       0x1816a7239
0x016a7042  cmp      rbx, 0xf
0x016a7046  ja       0x1816a7060
0x016a7048  lea      rax, [rsi + 8]
0x016a704c  mov      qword ptr [rsi + 0x18], rbx
0x016a7050  mov      qword ptr [rsi + 0x20], 0xf
0x016a7058  movups   xmm0, xmmword ptr [rdi]
0x016a705b  movups   xmmword ptr [rax], xmm0
0x016a705e  jmp      0x1816a70d4   ; ->rva 0x16a70d4
0x016a7060  mov      rax, rbx
0x016a7063  or       rax, 0xf
0x016a7067  cmp      rax, 0x17
0x016a706b  mov      r14d, 0x16
0x016a7071  cmovae   r14, rax
0x016a7075  cmp      rax, 0xfff
0x016a707b  jb       0x1816a70a1
0x016a707d  lea      rcx, [r14 + 0x28]
0x016a7081  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x016a7086  nop      
0x016a7087  test     rax, rax
0x016a708a  je       0x1816a7227
0x016a7090  mov      rcx, rax
0x016a7093  add      rax, 0x27
0x016a7097  and      rax, 0xffffffffffffffe0
0x016a709b  mov      qword ptr [rax - 8], rcx
0x016a709f  jmp      0x1816a70b7   ; ->rva 0x16a70b7
0x016a70a1  lea      rcx, [r14 + 1]
0x016a70a5  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x016a70aa  nop      
0x016a70ab  jmp      0x1816a70b7   ; ->rva 0x16a70b7
0x016a70ad  lea      rcx, [r14 + 1]
0x016a70b1  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x016a70b6  nop      
0x016a70b7  mov      qword ptr [rsi + 8], rax
0x016a70bb  mov      qword ptr [rsi + 0x18], rbx
0x016a70bf  mov      qword ptr [rsi + 0x20], r14
0x016a70c3  inc      rbx
0x016a70c6  mov      rcx, rax
0x016a70c9  mov      rdx, rdi
0x016a70cc  mov      r8, rbx
0x016a70cf  call     0x18669dd20   ; ->rva 0x669dd20
0x016a70d4  lea      rcx, [rsi + 0x28]
0x016a70d8  xorps    xmm0, xmm0
0x016a70db  movups   xmmword ptr [rsi + 0x28], xmm0
0x016a70df  mov      rax, qword ptr [rbp + 0x2b0]
0x016a70e6  test     rax, rax
0x016a70e9  je       0x1816a70f8
0x016a70eb  lock inc dword ptr [rax + 8]
0x016a70ef  mov      rax, qword ptr [rbp + 0x2b0]
0x016a70f6  jmp      0x1816a70fa   ; ->rva 0x16a70fa
0x016a70f8  xor      eax, eax
0x016a70fa  mov      rdx, qword ptr [rbp + 0x2a8]
0x016a7101  mov      qword ptr [rcx], rdx
0x016a7104  mov      qword ptr [rsi + 0x30], rax
0x016a7108  mov      rdi, qword ptr [rbp + 0x1e8]
0x016a710f  test     rdi, rdi
0x016a7112  je       0x1816a7131
0x016a7114  lock dec dword ptr [rdi + 8]
0x016a7118  jne      0x1816a7131
0x016a711a  mov      rax, qword ptr [rdi]
0x016a711d  mov      rcx, rdi
0x016a7120  call     qword ptr [rax]
0x016a7122  lock dec dword ptr [rdi + 0xc]
0x016a7126  jne      0x1816a7131
0x016a7128  mov      rax, qword ptr [rdi]
0x016a712b  mov      rcx, rdi
0x016a712e  call     qword ptr [rax + 8]
0x016a7131  mov      rdi, qword ptr [rbp + 0x2b0]
0x016a7138  test     rdi, rdi
0x016a713b  je       0x1816a715a
0x016a713d  lock dec dword ptr [rdi + 8]
0x016a7141  jne      0x1816a715a
0x016a7143  mov      rax, qword ptr [rdi]
0x016a7146  mov      rcx, rdi
0x016a7149  call     qword ptr [rax]
0x016a714b  lock dec dword ptr [rdi + 0xc]
0x016a714f  jne      0x1816a715a
0x016a7151  mov      rax, qword ptr [rdi]
0x016a7154  mov      rcx, rdi
0x016a7157  call     qword ptr [rax + 8]
0x016a715a  mov      rax, qword ptr [rbp + 0x2a0]
0x016a7161  cmp      rax, 0x10
0x016a7165  mov      rdi, qword ptr [rbp + 0x2c0]
0x016a716c  jb       0x1816a71a6
0x016a716e  mov      rcx, qword ptr [rbp + 0x288]
0x016a7175  lea      rdx, [rax + 1]
0x016a7179  cmp      rdx, 0x1000
0x016a7180  jb       0x1816a71a1
0x016a7182  mov      r8, qword ptr [rcx - 8]
0x016a7186  add      rcx, -8
0x016a718a  sub      rcx, r8
0x016a718d  cmp      rcx, 0x20
0x016a7191  jae      0x1816a7227
0x016a7197  add      rax, 0x28
0x016a719b  mov      rdx, rax
0x016a719e  mov      rcx, r8
0x016a71a1  call     0x1864a7d68   ; ->rva 0x64a7d68
0x016a71a6  mov      rax, qword ptr [rbp + 0xe0]
0x016a71ad  cmp      rax, 0x10
0x016a71b1  jb       0x1816a71e7
0x016a71b3  mov      rcx, qword ptr [rbp + 0xc8]
0x016a71ba  lea      rdx, [rax + 1]
0x016a71be  cmp      rdx, 0x1000
0x016a71c5  jb       0x1816a71e2
0x016a71c7  mov      r8, qword ptr [rcx - 8]
0x016a71cb  add      rcx, -8
0x016a71cf  sub      rcx, r8
0x016a71d2  cmp      rcx, 0x20
0x016a71d6  jae      0x1816a7227
0x016a71d8  add      rax, 0x28
0x016a71dc  mov      rdx, rax
0x016a71df  mov      rcx, r8
0x016a71e2  call     0x1864a7d68   ; ->rva 0x64a7d68
0x016a71e7  mov      rdi, qword ptr [rdi + 8]
0x016a71eb  test     rdi, rdi
0x016a71ee  je       0x1816a720d
0x016a71f0  lock dec dword ptr [rdi + 8]
0x016a71f4  jne      0x1816a720d
0x016a71f6  mov      rax, qword ptr [rdi]
0x016a71f9  mov      rcx, rdi
0x016a71fc  call     qword ptr [rax]
0x016a71fe  lock dec dword ptr [rdi + 0xc]
0x016a7202  jne      0x1816a720d
0x016a7204  mov      rax, qword ptr [rdi]
0x016a7207  mov      rcx, rdi
0x016a720a  call     qword ptr [rax + 8]
0x016a720d  mov      rax, rsi
0x016a7210  movaps   xmm6, xmmword ptr [rbp + 0x2d0]
0x016a7217  add      rsp, 0x368
0x016a721e  pop      rbx
0x016a721f  pop      rdi
0x016a7220  pop      rsi
0x016a7221  pop      r14
0x016a7223  pop      r15
0x016a7225  pop      rbp
0x016a7226  ret      
0x016a7227  call     0x186667ee8   ; ->rva 0x6667ee8
0x016a722c  nop      
0x016a722d  call     0x180008560   ; ->rva 0x8560
0x016a7232  nop      
0x016a7233  call     0x180008560   ; ->rva 0x8560
0x016a7238  nop      
0x016a7239  call     0x180008560   ; ->rva 0x8560
0x016a723e  nop      
0x016a723f  call     0x180008560   ; ->rva 0x8560
0x016a7244  nop      
0x016a7245  int3     
0x016a7246  nop      word ptr cs:[rax + rax]
0x016a7250  mov      qword ptr [rsp + 0x10], rdx
0x016a7255  push     rbp
0x016a7256  push     r15
0x016a7258  push     r14
0x016a725a  push     rsi
0x016a725b  push     rdi
0x016a725c  push     rbx
0x016a725d  sub      rsp, 0x58
0x016a7261  lea      rbp, [rdx + 0x80]
0x016a7268  movaps   xmmword ptr [rsp + 0x40], xmm6
0x016a726d  lea      rcx, [rbp + 0x1c0]
0x016a7274  call     0x180001ef0   ; ->rva 0x1ef0
0x016a7279  movaps   xmm6, xmmword ptr [rsp + 0x40]
0x016a727e  add      rsp, 0x58
0x016a7282  pop      rbx
0x016a7283  pop      rdi
0x016a7284  pop      rsi
0x016a7285  pop      r14
0x016a7287  pop      r15
0x016a7289  pop      rbp
0x016a728a  ret      
0x016a728b  nop      dword ptr [rax + rax]
0x016a7290  mov      qword ptr [rsp + 0x10], rdx
0x016a7295  push     rbp
0x016a7296  push     r15
0x016a7298  push     r14
0x016a729a  push     rsi
0x016a729b  push     rdi
0x016a729c  push     rbx
0x016a729d  sub      rsp, 0x58
0x016a72a1  lea      rbp, [rdx + 0x80]
0x016a72a8  movaps   xmmword ptr [rsp + 0x40], xmm6
0x016a72ad  lea      rcx, [rbp + 0x130]
0x016a72b4  call     0x180047040   ; ->rva 0x47040
0x016a72b9  movaps   xmm6, xmmword ptr [rsp + 0x40]
0x016a72be  add      rsp, 0x58
0x016a72c2  pop      rbx
0x016a72c3  pop      rdi
0x016a72c4  pop      rsi
0x016a72c5  pop      r14
0x016a72c7  pop      r15
0x016a72c9  pop      rbp
0x016a72ca  ret      
0x016a72cb  nop      dword ptr [rax + rax]
0x016a72d0  mov      qword ptr [rsp + 0x10], rdx
0x016a72d5  push     rbp
0x016a72d6  push     r15
0x016a72d8  push     r14
0x016a72da  push     rsi
0x016a72db  push     rdi
0x016a72dc  push     rbx
0x016a72dd  sub      rsp, 0x58
0x016a72e1  lea      rbp, [rdx + 0x80]
0x016a72e8  movaps   xmmword ptr [rsp + 0x40], xmm6
0x016a72ed  lea      rcx, [rbp + 0x130]
0x016a72f4  call     0x180033c90   ; ->rva 0x33c90
0x016a72f9  movaps   xmm6, xmmword ptr [rsp + 0x40]
0x016a72fe  add      rsp, 0x58
0x016a7302  pop      rbx
0x016a7303  pop      rdi
0x016a7304  pop      rsi
0x016a7305  pop      r14
0x016a7307  pop      r15
0x016a7309  pop      rbp
0x016a730a  ret      
0x016a730b  nop      dword ptr [rax + rax]
0x016a7310  mov      qword ptr [rsp + 0x10], rdx
0x016a7315  push     rbp
0x016a7316  push     r15
0x016a7318  push     r14
0x016a731a  push     rsi
0x016a731b  push     rdi
0x016a731c  push     rbx
0x016a731d  sub      rsp, 0x58
0x016a7321  lea      rbp, [rdx + 0x80]
0x016a7328  movaps   xmmword ptr [rsp + 0x40], xmm6
0x016a732d  lea      rcx, [rbp + 0x130]
0x016a7334  call     0x180047040   ; ->rva 0x47040
0x016a7339  movaps   xmm6, xmmword ptr [rsp + 0x40]
0x016a733e  add      rsp, 0x58
0x016a7342  pop      rbx
0x016a7343  pop      rdi
0x016a7344  pop      rsi
0x016a7345  pop      r14
0x016a7347  pop      r15
0x016a7349  pop      rbp
0x016a734a  ret      
0x016a734b  nop      dword ptr [rax + rax]
0x016a7350  mov      qword ptr [rsp + 0x10], rdx
0x016a7355  push     rbp
0x016a7356  push     r15
0x016a7358  push     r14
