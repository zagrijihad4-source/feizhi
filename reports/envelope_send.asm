0x016d4b80  call     0x1816d5a40   ; ->rva 0x16d5a40
0x016d4b85  nop      
0x016d4b86  lea      rcx, [rbp + 0x170]
0x016d4b8d  lea      rbx, [rbp - 0x40]
0x016d4b91  mov      rdx, rbx
0x016d4b94  call     0x1809d7930   ; ->rva 0x9d7930
0x016d4b99  mov      rcx, rbx
0x016d4b9c  call     0x180001f60   ; ->rva 0x1f60
0x016d4ba1  mov      rax, qword ptr [rbp + 0x170]
0x016d4ba8  mov      dword ptr [rax + 0xd8], 0x2b
0x016d4bb2  mov      byte ptr [rax + 0x660], 0
0x016d4bb9  jmp      0x1816d4bc2   ; ->rva 0x16d4bc2
0x016d4bbb  mov      rax, qword ptr [rbp + 0x170]
0x016d4bc2  mov      r14, qword ptr [rbp + 0x210]
0x016d4bc9  test     rax, rax
0x016d4bcc  je       0x1816d4c44
0x016d4bce  mov      rcx, qword ptr [rbp + 0xa4]
0x016d4bd5  mov      qword ptr [rax + 0x66c], rcx
0x016d4bdc  mov      ecx, dword ptr [rbp + 0xac]
0x016d4be2  mov      dword ptr [rax + 0x674], ecx
0x016d4be8  movzx    ecx, byte ptr [rbp + 0xa1]
0x016d4bef  mov      byte ptr [rax + 0x662], cl
0x016d4bf5  mov      rcx, qword ptr [rbp + 0x178]
0x016d4bfc  test     rcx, rcx
0x016d4bff  je       0x1816d4c15
0x016d4c01  lock inc dword ptr [rcx + 8]
0x016d4c05  mov      rax, qword ptr [rbp + 0x170]
0x016d4c0c  mov      rcx, qword ptr [rbp + 0x178]
0x016d4c13  jmp      0x1816d4c17   ; ->rva 0x16d4c17
0x016d4c15  xor      ecx, ecx
0x016d4c17  mov      qword ptr [r14], rax
0x016d4c1a  mov      rbx, qword ptr [r14 + 8]
0x016d4c1e  mov      qword ptr [r14 + 8], rcx
0x016d4c22  test     rbx, rbx
0x016d4c25  je       0x1816d4c44
0x016d4c27  lock dec dword ptr [rbx + 8]
0x016d4c2b  jne      0x1816d4c44
0x016d4c2d  mov      rax, qword ptr [rbx]
0x016d4c30  mov      rcx, rbx
0x016d4c33  call     qword ptr [rax]
0x016d4c35  lock dec dword ptr [rbx + 0xc]
0x016d4c39  jne      0x1816d4c44
0x016d4c3b  mov      rax, qword ptr [rbx]
0x016d4c3e  mov      rcx, rbx
0x016d4c41  call     qword ptr [rax + 8]
0x016d4c44  xorps    xmm0, xmm0
0x016d4c47  movaps   xmmword ptr [rbp + 0x80], xmm0
0x016d4c4e  mov      rax, qword ptr [rbp + 0x208]
0x016d4c55  test     rax, rax
0x016d4c58  je       0x1816d4c67
0x016d4c5a  lock inc dword ptr [rax + 8]
0x016d4c5e  mov      rax, qword ptr [rbp + 0x208]
0x016d4c65  jmp      0x1816d4c69   ; ->rva 0x16d4c69
0x016d4c67  xor      eax, eax
0x016d4c69  mov      rcx, qword ptr [rbp + 0x200]
0x016d4c70  mov      qword ptr [rbp + 0x80], rcx
0x016d4c77  mov      qword ptr [rbp + 0x88], rax
0x016d4c7e  lea      rcx, [rbp + 0x80]
0x016d4c85  call     0x1809ffc80   ; ->rva 0x9ffc80
0x016d4c8a  nop      
0x016d4c8b  mov      ebx, eax
0x016d4c8d  and      eax, 0xfffffffe
0x016d4c90  cmp      eax, 2
0x016d4c93  jne      0x1816d4ee7
0x016d4c99  movaps   xmmword ptr [rbp - 0x40], xmm6
0x016d4c9d  lea      rcx, [rbp - 0x40]
0x016d4ca1  mov      rdx, rdi
0x016d4ca4  call     0x1816d5b80   ; ->rva 0x16d5b80
0x016d4ca9  nop      
0x016d4caa  mov      rax, qword ptr [rbp - 0x40]
0x016d4cae  cmp      ebx, 2
0x016d4cb1  jne      0x1816d4cbf
0x016d4cb3  mov      dword ptr [rax + 0xd8], 0x2f
0x016d4cbd  jmp      0x1816d4cd0   ; ->rva 0x16d4cd0
0x016d4cbf  movabs   rcx, 0x800000031
0x016d4cc9  mov      qword ptr [rax + 0xd8], rcx
0x016d4cd0  mov      rdx, qword ptr [rbp + 0x210]
0x016d4cd7  mov      rcx, qword ptr [rbp - 0x38]
0x016d4cdb  test     rcx, rcx
0x016d4cde  je       0x1816d4e92
0x016d4ce4  lock inc dword ptr [rcx + 8]
0x016d4ce8  mov      rax, qword ptr [rbp - 0x40]
0x016d4cec  mov      rcx, qword ptr [rbp - 0x38]
0x016d4cf0  jmp      0x1816d4e94   ; ->rva 0x16d4e94
0x016d4cf5  xor      eax, eax
0x016d4cf7  mov      rcx, qword ptr [rbp + 0x200]
0x016d4cfe  mov      qword ptr [rbp + 0x90], rcx
0x016d4d05  mov      qword ptr [rbp + 0x98], rax
0x016d4d0c  lea      rcx, [rbp + 0x90]
0x016d4d13  call     0x1809ffc80   ; ->rva 0x9ffc80
0x016d4d18  nop      
0x016d4d19  cmp      eax, 1
0x016d4d1c  jne      0x1816d4e77
0x016d4d22  mov      ecx, 3
0x016d4d27  call     0x180046ac0   ; ->rva 0x46ac0
0x016d4d2c  test     eax, eax
0x016d4d2e  mov      r14, qword ptr [rbp + 0x210]
0x016d4d35  je       0x1816d50ea
0x016d4d3b  lea      rbx, [rbp + 0x130]
0x016d4d42  mov      rcx, rbx
0x016d4d45  call     0x180046bf0   ; ->rva 0x46bf0
0x016d4d4a  nop      
0x016d4d4b  cmp      qword ptr [rbp + 0x148], 0x10
0x016d4d53  jb       0x1816d4d5c
0x016d4d55  mov      rbx, qword ptr [rbp + 0x130]
0x016d4d5c  lea      rax, [rip + 0x6bfaee3]   ; ->rva 0x82cfc46
0x016d4d63  mov      qword ptr [rsp + 0x20], rax
0x016d4d68  mov      qword ptr [rsp + 0x38], 0
0x016d4d71  mov      byte ptr [rsp + 0x30], 0
0x016d4d76  mov      dword ptr [rsp + 0x28], 0x1633
0x016d4d7e  lea      r9, [rip + 0x6bf6fc7]   ; ->rva 0x82cbd4c
0x016d4d85  lea      rcx, [rbp + 0xa0]
0x016d4d8c  mov      edx, 3
0x016d4d91  mov      r8, rbx
0x016d4d94  call     0x180046f40   ; ->rva 0x46f40
0x016d4d99  nop      
0x016d4d9a  mov      ecx, 0xe0
0x016d4d9f  add      rcx, qword ptr [rbp + 0x200]
0x016d4da6  lea      rdx, [rbp + 0x10]
0x016d4daa  call     0x180098620   ; ->rva 0x98620
0x016d4daf  nop      
0x016d4db0  lea      rbx, [rbp + 0x150]
0x016d4db7  lea      rdx, [rbp + 0x10]
0x016d4dbb  mov      rcx, rbx
0x016d4dbe  call     0x180318dc0   ; ->rva 0x318dc0
0x016d4dc3  nop      
0x016d4dc4  cmp      qword ptr [rbp + 0x168], 0x10
0x016d4dcc  jb       0x1816d4dd5
0x016d4dce  mov      rbx, qword ptr [rbp + 0x150]
0x016d4dd5  mov      qword ptr [rbp - 0x40], rbx
0x016d4dd9  mov      byte ptr [rbp - 0x38], 0
0x016d4ddd  xorps    xmm0, xmm0
0x016d4de0  movaps   xmmword ptr [rbp + 0x170], xmm0
0x016d4de7  movaps   xmmword ptr [rbp + 0x1e0], xmm0
0x016d4dee  movaps   xmmword ptr [rbp + 0x1d0], xmm0
0x016d4df5  movaps   xmmword ptr [rbp + 0x1c0], xmm0
0x016d4dfc  movaps   xmmword ptr [rbp + 0x1b0], xmm0
0x016d4e03  movaps   xmmword ptr [rbp + 0x1a0], xmm0
0x016d4e0a  movaps   xmmword ptr [rbp + 0x190], xmm0
0x016d4e11  movaps   xmmword ptr [rbp + 0x180], xmm0
