0x016d5b40  pop      r14
0x016d5b42  pop      rbp
0x016d5b43  ret      
0x016d5b44  nop      word ptr cs:[rax + rax]
0x016d5b50  mov      qword ptr [rsp + 0x10], rdx
0x016d5b55  push     rbp
0x016d5b56  push     r14
0x016d5b58  push     rsi
0x016d5b59  push     rdi
0x016d5b5a  push     rbx
0x016d5b5b  sub      rsp, 0x20
0x016d5b5f  lea      rbp, [rdx + 0x40]
0x016d5b63  mov      rcx, qword ptr [rbp - 0x10]
0x016d5b67  call     0x1864a7d60   ; ->rva 0x64a7d60
0x016d5b6c  nop      
0x016d5b6d  add      rsp, 0x20
0x016d5b71  pop      rbx
0x016d5b72  pop      rdi
0x016d5b73  pop      rsi
0x016d5b74  pop      r14
0x016d5b76  pop      rbp
0x016d5b77  ret      
0x016d5b78  int3     
0x016d5b79  int3     
0x016d5b7a  int3     
0x016d5b7b  int3     
0x016d5b7c  int3     
0x016d5b7d  int3     
0x016d5b7e  int3     
0x016d5b7f  int3     
0x016d5b80  push     rbp
0x016d5b81  push     rsi
0x016d5b82  push     rdi
0x016d5b83  push     rbx
0x016d5b84  sub      rsp, 0x38
0x016d5b88  lea      rbp, [rsp + 0x30]
0x016d5b8d  mov      qword ptr [rbp], 0xfffffffffffffffe
0x016d5b95  mov      rdi, rdx
0x016d5b98  mov      rsi, rcx
0x016d5b9b  mov      ecx, 0x698
0x016d5ba0  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x016d5ba5  nop      
0x016d5ba6  mov      qword ptr [rbp - 8], rax
0x016d5baa  mov      rcx, rax
0x016d5bad  mov      rdx, rdi
0x016d5bb0  call     0x1817040a0   ; ->rva 0x17040a0
0x016d5bb5  nop      
0x016d5bb6  mov      rdx, qword ptr [rbp - 8]
0x016d5bba  lea      rax, [rdx + 0x10]
0x016d5bbe  mov      qword ptr [rsi], rax
0x016d5bc1  mov      qword ptr [rsi + 8], rdx
0x016d5bc5  mov      rcx, qword ptr [rdx + 0x20]
0x016d5bc9  test     rcx, rcx
0x016d5bcc  je       0x1816d5bd4
0x016d5bce  cmp      dword ptr [rcx + 8], 0
0x016d5bd2  jne      0x1816d5c32
0x016d5bd4  mov      bl, 1
0x016d5bd6  test     rdx, rdx
0x016d5bd9  je       0x1816d5bf0
0x016d5bdb  lock inc dword ptr [rdx + 8]
0x016d5bdf  mov      rdi, qword ptr [rsi + 8]
0x016d5be3  test     rdi, rdi
0x016d5be6  je       0x1816d5bf0
0x016d5be8  lock inc dword ptr [rdi + 0xc]
0x016d5bec  xor      ebx, ebx
0x016d5bee  jmp      0x1816d5bf4   ; ->rva 0x16d5bf4
0x016d5bf0  xor      edi, edi
0x016d5bf2  xor      eax, eax
0x016d5bf4  mov      qword ptr [rdx + 0x18], rax
0x016d5bf8  mov      rcx, qword ptr [rdx + 0x20]
0x016d5bfc  mov      qword ptr [rdx + 0x20], rdi
0x016d5c00  test     rcx, rcx
0x016d5c03  je       0x1816d5c11
0x016d5c05  lock dec dword ptr [rcx + 0xc]
0x016d5c09  jne      0x1816d5c11
0x016d5c0b  mov      rax, qword ptr [rcx]
0x016d5c0e  call     qword ptr [rax + 8]
0x016d5c11  test     bl, bl
0x016d5c13  jne      0x1816d5c32
0x016d5c15  lock dec dword ptr [rdi + 8]
0x016d5c19  jne      0x1816d5c32
0x016d5c1b  mov      rax, qword ptr [rdi]
0x016d5c1e  mov      rcx, rdi
0x016d5c21  call     qword ptr [rax]
0x016d5c23  lock dec dword ptr [rdi + 0xc]
0x016d5c27  jne      0x1816d5c32
0x016d5c29  mov      rax, qword ptr [rdi]
0x016d5c2c  mov      rcx, rdi
0x016d5c2f  call     qword ptr [rax + 8]
0x016d5c32  mov      rax, rsi
0x016d5c35  add      rsp, 0x38
0x016d5c39  pop      rbx
0x016d5c3a  pop      rdi
0x016d5c3b  pop      rsi
0x016d5c3c  pop      rbp
0x016d5c3d  ret      
0x016d5c3e  nop      
0x016d5c40  mov      qword ptr [rsp + 0x10], rdx
0x016d5c45  push     rbp
0x016d5c46  push     rsi
0x016d5c47  push     rdi
0x016d5c48  push     rbx
0x016d5c49  sub      rsp, 0x28
0x016d5c4d  lea      rbp, [rdx + 0x30]
0x016d5c51  mov      rcx, qword ptr [rbp - 8]
0x016d5c55  call     0x1864a7d60   ; ->rva 0x64a7d60
0x016d5c5a  nop      
0x016d5c5b  add      rsp, 0x28
0x016d5c5f  pop      rbx
0x016d5c60  pop      rdi
