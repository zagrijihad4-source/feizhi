; 命中点 0x160ebe0 属于函数 [0x160ebe0, 0x160eee9)，从入口反汇编
0x0160ebe0  push     rbp
0x0160ebe1  push     r14
0x0160ebe3  push     rsi
0x0160ebe4  push     rdi
0x0160ebe5  push     rbx
0x0160ebe6  sub      rsp, 0x1e0
0x0160ebed  lea      rbp, [rsp + 0x80]
0x0160ebf5  mov      qword ptr [rbp + 0x158], 0xfffffffffffffffe
0x0160ec00  mov      rbx, rdx
0x0160ec03  mov      rdi, rcx
0x0160ec06  call     0x18001f460   ; ->rva 0x1f460
0x0160ec0b  lea      rdx, [rbp + 0x128]
0x0160ec12  mov      rcx, rax
0x0160ec15  call     0x180020a50   ; ->rva 0x20a50
0x0160ec1a  mov      rsi, qword ptr [rbp + 0x128]
0x0160ec21  xorps    xmm0, xmm0
0x0160ec24  movaps   xmmword ptr [rbp - 0x50], xmm0
0x0160ec28  mov      qword ptr [rbp - 0x40], 0
0x0160ec30  mov      r14, qword ptr [rdi + 0x10]
0x0160ec34  mov      rcx, qword ptr [rdi + 8]
0x0160ec38  mov      rax, r14
0x0160ec3b  sub      rax, rcx
0x0160ec3e  sub      r14, rcx
0x0160ec41  je       0x18160ece2
0x0160ec47  sar      rax, 4
0x0160ec4b  mov      rcx, rax
0x0160ec4e  shr      rcx, 0x3c
0x0160ec52  jne      0x18160eed7
0x0160ec58  cmp      rax, 0x100
0x0160ec5e  jb       0x18160ec84
0x0160ec60  lea      rcx, [r14 + 0x27]
0x0160ec64  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x0160ec69  nop      
0x0160ec6a  test     rax, rax
0x0160ec6d  je       0x18160eee3
0x0160ec73  mov      rcx, rax
0x0160ec76  add      rax, 0x27
0x0160ec7a  and      rax, 0xffffffffffffffe0
0x0160ec7e  mov      qword ptr [rax - 8], rcx
0x0160ec82  jmp      0x18160ec8d   ; ->rva 0x160ec8d
0x0160ec84  mov      rcx, r14
0x0160ec87  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x0160ec8c  nop      
0x0160ec8d  mov      qword ptr [rbp - 0x50], rax
0x0160ec91  mov      qword ptr [rbp - 0x48], rax
0x0160ec95  add      r14, rax
0x0160ec98  mov      qword ptr [rbp - 0x40], r14
0x0160ec9c  mov      rcx, qword ptr [rdi + 8]
0x0160eca0  mov      rdx, qword ptr [rdi + 0x10]
0x0160eca4  cmp      rcx, rdx
0x0160eca7  je       0x18160ecde
0x0160eca9  xorps    xmm0, xmm0
0x0160ecac  jmp      0x18160eccb   ; ->rva 0x160eccb
0x0160ecae  nop      
0x0160ecb0  mov      r8, qword ptr [rcx]
0x0160ecb3  mov      qword ptr [rax], r8
0x0160ecb6  mov      r8, qword ptr [rcx + 8]
0x0160ecba  mov      qword ptr [rax + 8], r8
0x0160ecbe  add      rax, 0x10
0x0160ecc2  add      rcx, 0x10
0x0160ecc6  cmp      rcx, rdx
0x0160ecc9  je       0x18160ecde
0x0160eccb  movups   xmmword ptr [rax], xmm0
0x0160ecce  mov      r8, qword ptr [rcx + 8]
0x0160ecd2  test     r8, r8
0x0160ecd5  je       0x18160ecb0
0x0160ecd7  lock inc dword ptr [r8 + 8]
0x0160ecdc  jmp      0x18160ecb0   ; ->rva 0x160ecb0
0x0160ecde  mov      qword ptr [rbp - 0x48], rax
0x0160ece2  lea      rdi, [rbp - 0x38]
0x0160ece6  mov      rcx, rdi
0x0160ece9  mov      rdx, rbx
0x0160ecec  call     0x180038c30   ; ->rva 0x38c30
0x0160ecf1  nop      
0x0160ecf2  mov      qword ptr [rbp + 0x120], 0
0x0160ecfd  mov      qword ptr [rbp + 0x140], 0
0x0160ed08  mov      ecx, 0x108
0x0160ed0d  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x0160ed12  nop      
0x0160ed13  mov      r9, rax
0x0160ed16  lea      rax, [rip + 0x6cb167b]   ; ->rva 0x82c0398
0x0160ed1d  mov      qword ptr [r9], rax
0x0160ed20  xorps    xmm0, xmm0
0x0160ed23  movups   xmmword ptr [r9 + 8], xmm0
0x0160ed28  mov      qword ptr [r9 + 0x18], 0
0x0160ed30  mov      rbx, qword ptr [rbp - 0x48]
0x0160ed34  mov      rcx, qword ptr [rbp - 0x50]
0x0160ed38  mov      rax, rbx
0x0160ed3b  sub      rax, rcx
0x0160ed3e  sub      rbx, rcx
0x0160ed41  mov      qword ptr [rbp + 0x148], r9
0x0160ed48  je       0x18160edf2
0x0160ed4e  sar      rax, 4
0x0160ed52  mov      rcx, rax
0x0160ed55  shr      rcx, 0x3c
0x0160ed59  jne      0x18160eedd
0x0160ed5f  cmp      rax, 0x100
0x0160ed65  jb       0x18160ed8b
0x0160ed67  lea      rcx, [rbx + 0x27]
0x0160ed6b  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x0160ed70  nop      
0x0160ed71  test     rax, rax
0x0160ed74  je       0x18160eee3
0x0160ed7a  mov      rcx, rax
0x0160ed7d  add      rax, 0x27
0x0160ed81  and      rax, 0xffffffffffffffe0
0x0160ed85  mov      qword ptr [rax - 8], rcx
0x0160ed89  jmp      0x18160ed94   ; ->rva 0x160ed94
0x0160ed8b  mov      rcx, rbx
0x0160ed8e  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x0160ed93  nop      
0x0160ed94  mov      r9, qword ptr [rbp + 0x148]
0x0160ed9b  mov      qword ptr [r9 + 8], rax
0x0160ed9f  mov      qword ptr [r9 + 0x10], rax
0x0160eda3  add      rbx, rax
0x0160eda6  mov      qword ptr [r9 + 0x18], rbx
0x0160edaa  mov      rcx, qword ptr [rbp - 0x50]
0x0160edae  mov      rdx, qword ptr [rbp - 0x48]
0x0160edb2  cmp      rcx, rdx
0x0160edb5  je       0x18160edee
0x0160edb7  xorps    xmm0, xmm0
0x0160edba  jmp      0x18160eddb   ; ->rva 0x160eddb
0x0160edbc  nop      dword ptr [rax]
0x0160edc0  mov      r8, qword ptr [rcx]
0x0160edc3  mov      qword ptr [rax], r8
0x0160edc6  mov      r8, qword ptr [rcx + 8]
0x0160edca  mov      qword ptr [rax + 8], r8
0x0160edce  add      rax, 0x10
0x0160edd2  add      rcx, 0x10
0x0160edd6  cmp      rcx, rdx
0x0160edd9  je       0x18160edee
0x0160eddb  movups   xmmword ptr [rax], xmm0
0x0160edde  mov      r8, qword ptr [rcx + 8]
0x0160ede2  test     r8, r8
0x0160ede5  je       0x18160edc0
0x0160ede7  lock inc dword ptr [r8 + 8]
0x0160edec  jmp      0x18160edc0   ; ->rva 0x160edc0
0x0160edee  mov      qword ptr [r9 + 0x10], rax
0x0160edf2  lea      rax, [r9 + 8]
0x0160edf6  mov      qword ptr [rbp + 0x138], rax
0x0160edfd  lea      rcx, [r9 + 0x20]
0x0160ee01  mov      rdx, rdi
0x0160ee04  call     0x180038c30   ; ->rva 0x38c30
0x0160ee09  nop      
0x0160ee0a  mov      rax, qword ptr [rbp + 0x148]
0x0160ee11  mov      qword ptr [rbp + 0x120], rax
0x0160ee18  mov      byte ptr [rbp + 0x157], 1
0x0160ee1f  lea      rdx, [rip + 0x6955fd4]   ; ->rva 0x7f64dfa
0x0160ee26  lea      r8, [rip + 0x6cb604f]   ; ->rva 0x82c4e7c
0x0160ee2d  lea      rcx, [rbp + 0xb8]
0x0160ee34  mov      r9d, 0x1f6
0x0160ee3a  call     0x1801845d0   ; ->rva 0x1845d0
0x0160ee3f  nop      
0x0160ee40  mov      byte ptr [rbp + 0x157], 0
0x0160ee47  mov      dword ptr [rsp + 0x20], 1
0x0160ee4f  lea      rdx, [rbp + 0xd8]
0x0160ee56  lea      r8, [rbp + 0xb8]
0x0160ee5d  lea      r9, [rbp + 0xe8]
0x0160ee64  mov      rcx, rsi
0x0160ee67  call     0x180290390   ; ->rva 0x290390
0x0160ee6c  nop      
0x0160ee6d  mov      rsi, qword ptr [rbp + 0xe0]
0x0160ee74  test     rsi, rsi
0x0160ee77  je       0x18160ee96
0x0160ee79  lock dec dword ptr [rsi + 8]
0x0160ee7d  jne      0x18160ee96
0x0160ee7f  mov      rax, qword ptr [rsi]
0x0160ee82  mov      rcx, rsi
0x0160ee85  call     qword ptr [rax]
0x0160ee87  lock dec dword ptr [rsi + 0xc]
0x0160ee8b  jne      0x18160ee96
0x0160ee8d  mov      rax, qword ptr [rsi]
0x0160ee90  mov      rcx, rsi
0x0160ee93  call     qword ptr [rax + 8]
0x0160ee96  lea      rcx, [rbp - 0x50]
0x0160ee9a  call     0x18160f1b0   ; ->rva 0x160f1b0
0x0160ee9f  mov      rsi, qword ptr [rbp + 0x130]
0x0160eea6  test     rsi, rsi
0x0160eea9  je       0x18160eec9
0x0160eeab  lock dec dword ptr [rsi + 8]
0x0160eeaf  jne      0x18160eec9
0x0160eeb1  mov      rax, qword ptr [rsi]
0x0160eeb4  mov      rcx, rsi
0x0160eeb7  call     qword ptr [rax]
0x0160eeb9  lock dec dword ptr [rsi + 0xc]
0x0160eebd  jne      0x18160eec9
0x0160eebf  mov      rax, qword ptr [rsi]
0x0160eec2  mov      rcx, rsi
0x0160eec5  call     qword ptr [rax + 8]
0x0160eec8  nop      
0x0160eec9  add      rsp, 0x1e0
0x0160eed0  pop      rbx
0x0160eed1  pop      rdi
0x0160eed2  pop      rsi
0x0160eed3  pop      r14
0x0160eed5  pop      rbp
0x0160eed6  ret      
0x0160eed7  call     0x18000ac70   ; ->rva 0xac70
0x0160eedc  nop      
0x0160eedd  call     0x18000ac70   ; ->rva 0xac70
0x0160eee2  nop      
0x0160eee3  call     0x186667ee8   ; ->rva 0x6667ee8
0x0160eee8  int3     
0x0160eee9  nop      dword ptr [rax]
0x0160eef0  mov      qword ptr [rsp + 0x10], rdx
0x0160eef5  push     rbp
0x0160eef6  push     r14
0x0160eef8  push     rsi
0x0160eef9  push     rdi
0x0160eefa  push     rbx
0x0160eefb  sub      rsp, 0x30
0x0160eeff  lea      rbp, [rdx + 0x80]
0x0160ef06  mov      rcx, qword ptr [rbp + 0x138]
0x0160ef0d  call     0x1801d4350   ; ->rva 0x1d4350
0x0160ef12  nop      
0x0160ef13  add      rsp, 0x30
0x0160ef17  pop      rbx
0x0160ef18  pop      rdi
0x0160ef19  pop      rsi
0x0160ef1a  pop      r14
