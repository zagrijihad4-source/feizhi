0x0000db40  push     rbp
0x0000db41  push     r15
0x0000db43  push     r14
0x0000db45  push     r12
0x0000db47  push     rsi
0x0000db48  push     rdi
0x0000db49  push     rbx
0x0000db4a  sub      rsp, 0x40
0x0000db4e  lea      rbp, [rsp + 0x40]
0x0000db53  mov      qword ptr [rbp - 8], 0xfffffffffffffffe
0x0000db5b  mov      qword ptr [rbp - 0x18], r9
0x0000db5f  mov      qword ptr [rbp - 0x10], r8
0x0000db63  mov      qword ptr [rbp - 0x20], rdx
0x0000db67  mov      rsi, rcx
0x0000db6a  mov      ecx, 0x18
0x0000db6f  call     0x1864a7d1c   ; ->rva 0x64a7d1c
0x0000db74  nop      
0x0000db75  movabs   rcx, 0x100000001
0x0000db7f  mov      qword ptr [rax + 8], rcx
0x0000db83  lea      rcx, [rip + 0x7f5180e]   ; ->rva 0x7f5f398
0x0000db8a  mov      qword ptr [rax], rcx
0x0000db8d  mov      rcx, rax
0x0000db90  add      rcx, 0x10
0x0000db94  mov      byte ptr [rax + 0x10], 0
0x0000db98  mov      qword ptr [rsi], rcx
0x0000db9b  mov      qword ptr [rsi + 8], rax
0x0000db9f  mov      qword ptr [rsi + 0x48], 0
0x0000dba7  mov      r12, qword ptr [rbp - 0x20]
0x0000dbab  mov      rcx, qword ptr [r12 + 0x38]
0x0000dbb0  test     rcx, rcx
0x0000dbb3  mov      r15, qword ptr [rbp - 0x10]
0x0000dbb7  je       0x18000dbf1
0x0000dbb9  cmp      rcx, r12
0x0000dbbc  je       0x18000dbc4
0x0000dbbe  mov      qword ptr [rsi + 0x48], rcx
0x0000dbc2  jmp      0x18000dbe8   ; ->rva 0xdbe8
0x0000dbc4  lea      rdx, [rsi + 0x10]
0x0000dbc8  mov      rax, qword ptr [rcx]
0x0000dbcb  call     qword ptr [rax + 8]
0x0000dbce  mov      qword ptr [rsi + 0x48], rax
0x0000dbd2  mov      rcx, qword ptr [r12 + 0x38]
0x0000dbd7  test     rcx, rcx
0x0000dbda  je       0x18000dbf1
0x0000dbdc  cmp      rcx, r12
0x0000dbdf  setne    dl
0x0000dbe2  mov      rax, qword ptr [rcx]
0x0000dbe5  call     qword ptr [rax + 0x20]
0x0000dbe8  mov      qword ptr [r12 + 0x38], 0
0x0000dbf1  mov      qword ptr [rsi + 0x88], 0
0x0000dbfc  mov      rcx, qword ptr [r15 + 0x38]
0x0000dc00  test     rcx, rcx
0x0000dc03  mov      r14, qword ptr [rbp - 0x18]
0x0000dc07  je       0x18000dc45
0x0000dc09  cmp      rcx, r15
0x0000dc0c  je       0x18000dc17
0x0000dc0e  mov      qword ptr [rsi + 0x88], rcx
0x0000dc15  jmp      0x18000dc3d   ; ->rva 0xdc3d
0x0000dc17  lea      rdx, [rsi + 0x50]
0x0000dc1b  mov      rax, qword ptr [rcx]
0x0000dc1e  call     qword ptr [rax + 8]
0x0000dc21  mov      qword ptr [rsi + 0x88], rax
0x0000dc28  mov      rcx, qword ptr [r15 + 0x38]
0x0000dc2c  test     rcx, rcx
0x0000dc2f  je       0x18000dc45
0x0000dc31  cmp      rcx, r15
0x0000dc34  setne    dl
0x0000dc37  mov      rax, qword ptr [rcx]
0x0000dc3a  call     qword ptr [rax + 0x20]
0x0000dc3d  mov      qword ptr [r15 + 0x38], 0
0x0000dc45  mov      rbx, qword ptr [rbp + 0x68]
0x0000dc49  mov      rdi, qword ptr [rbp + 0x60]
0x0000dc4d  mov      qword ptr [rsi + 0xc8], 0
0x0000dc58  mov      rcx, qword ptr [r14 + 0x38]
0x0000dc5c  test     rcx, rcx
0x0000dc5f  je       0x18000dca0
0x0000dc61  cmp      rcx, r14
0x0000dc64  je       0x18000dc6f
0x0000dc66  mov      qword ptr [rsi + 0xc8], rcx
0x0000dc6d  jmp      0x18000dc98   ; ->rva 0xdc98
0x0000dc6f  lea      rdx, [rsi + 0x90]
0x0000dc76  mov      rax, qword ptr [rcx]
0x0000dc79  call     qword ptr [rax + 8]
0x0000dc7c  mov      qword ptr [rsi + 0xc8], rax
0x0000dc83  mov      rcx, qword ptr [r14 + 0x38]
0x0000dc87  test     rcx, rcx
0x0000dc8a  je       0x18000dca0
0x0000dc8c  cmp      rcx, r14
0x0000dc8f  setne    dl
0x0000dc92  mov      rax, qword ptr [rcx]
0x0000dc95  call     qword ptr [rax + 0x20]
0x0000dc98  mov      qword ptr [r14 + 0x38], 0
0x0000dca0  mov      qword ptr [rsi + 0xd0], rbx
0x0000dca7  xorps    xmm0, xmm0
0x0000dcaa  movups   xmmword ptr [rsi + 0xd8], xmm0
0x0000dcb1  mov      rax, qword ptr [rdi]
0x0000dcb4  test     rax, rax
0x0000dcb7  je       0x18000dcfe
0x0000dcb9  mov      rcx, qword ptr [rdi + 8]
0x0000dcbd  test     rcx, rcx
0x0000dcc0  je       0x18000dccf
0x0000dcc2  lock inc dword ptr [rcx + 8]
0x0000dcc6  mov      rax, qword ptr [rdi]
0x0000dcc9  mov      rcx, qword ptr [rdi + 8]
0x0000dccd  jmp      0x18000dcd1   ; ->rva 0xdcd1
0x0000dccf  xor      ecx, ecx
0x0000dcd1  mov      qword ptr [rsi], rax
0x0000dcd4  mov      rdi, qword ptr [rsi + 8]
0x0000dcd8  mov      qword ptr [rsi + 8], rcx
0x0000dcdc  test     rdi, rdi
0x0000dcdf  je       0x18000dcfe
0x0000dce1  lock dec dword ptr [rdi + 8]
0x0000dce5  jne      0x18000dcfe
0x0000dce7  mov      rax, qword ptr [rdi]
0x0000dcea  mov      rcx, rdi
0x0000dced  call     qword ptr [rax]
0x0000dcef  lock dec dword ptr [rdi + 0xc]
0x0000dcf3  jne      0x18000dcfe
0x0000dcf5  mov      rax, qword ptr [rdi]
0x0000dcf8  mov      rcx, rdi
0x0000dcfb  call     qword ptr [rax + 8]
0x0000dcfe  mov      rcx, qword ptr [r12 + 0x38]
0x0000dd03  test     rcx, rcx
0x0000dd06  je       0x18000dd1d
0x0000dd08  cmp      rcx, r12
0x0000dd0b  setne    dl
0x0000dd0e  mov      rax, qword ptr [rcx]
0x0000dd11  call     qword ptr [rax + 0x20]
0x0000dd14  mov      qword ptr [r12 + 0x38], 0
0x0000dd1d  mov      rcx, qword ptr [r15 + 0x38]
0x0000dd21  test     rcx, rcx
0x0000dd24  je       0x18000dd3a
0x0000dd26  cmp      rcx, r15
0x0000dd29  setne    dl
0x0000dd2c  mov      rax, qword ptr [rcx]
0x0000dd2f  call     qword ptr [rax + 0x20]
0x0000dd32  mov      qword ptr [r15 + 0x38], 0
0x0000dd3a  mov      rcx, qword ptr [r14 + 0x38]
0x0000dd3e  test     rcx, rcx
0x0000dd41  je       0x18000dd4f
0x0000dd43  cmp      rcx, r14
0x0000dd46  setne    dl
0x0000dd49  mov      rax, qword ptr [rcx]
0x0000dd4c  call     qword ptr [rax + 0x20]
0x0000dd4f  mov      rax, rsi
0x0000dd52  add      rsp, 0x40
0x0000dd56  pop      rbx
0x0000dd57  pop      rdi
0x0000dd58  pop      rsi
0x0000dd59  pop      r12
0x0000dd5b  pop      r14
0x0000dd5d  pop      r15
0x0000dd5f  pop      rbp
0x0000dd60  ret      
0x0000dd61  nop      word ptr cs:[rax + rax]
0x0000dd70  mov      qword ptr [rsp + 0x10], rdx
0x0000dd75  push     rbp
0x0000dd76  push     r15
0x0000dd78  push     r14
0x0000dd7a  push     r12
0x0000dd7c  push     rsi
0x0000dd7d  push     rdi
0x0000dd7e  push     rbx
0x0000dd7f  sub      rsp, 0x20
0x0000dd83  lea      rbp, [rdx + 0x40]
0x0000dd87  mov      rcx, qword ptr [rbp - 0x20]
0x0000dd8b  mov      rax, rcx
0x0000dd8e  mov      rcx, qword ptr [rcx + 0x38]
0x0000dd92  test     rcx, rcx
0x0000dd95  je       0x18000ddae
0x0000dd97  mov      rsi, rax
0x0000dd9a  cmp      rcx, rax
0x0000dd9d  setne    dl
0x0000dda0  mov      rax, qword ptr [rcx]
0x0000dda3  call     qword ptr [rax + 0x20]
0x0000dda6  mov      qword ptr [rsi + 0x38], 0
0x0000ddae  mov      rax, qword ptr [rbp - 0x10]
0x0000ddb2  mov      rcx, qword ptr [rax + 0x38]
0x0000ddb6  test     rcx, rcx
0x0000ddb9  je       0x18000ddd3
0x0000ddbb  mov      rsi, qword ptr [rbp - 0x10]
0x0000ddbf  cmp      rcx, rsi
0x0000ddc2  setne    dl
0x0000ddc5  mov      rax, qword ptr [rcx]
0x0000ddc8  call     qword ptr [rax + 0x20]
0x0000ddcb  mov      qword ptr [rsi + 0x38], 0
0x0000ddd3  mov      rax, qword ptr [rbp - 0x18]
0x0000ddd7  mov      rcx, qword ptr [rax + 0x38]
0x0000dddb  test     rcx, rcx
0x0000ddde  je       0x18000ddee
0x0000dde0  cmp      rcx, qword ptr [rbp - 0x18]
0x0000dde4  setne    dl
0x0000dde7  mov      rax, qword ptr [rcx]
0x0000ddea  call     qword ptr [rax + 0x20]
0x0000dded  nop      
0x0000ddee  add      rsp, 0x20
0x0000ddf2  pop      rbx
0x0000ddf3  pop      rdi
0x0000ddf4  pop      rsi
0x0000ddf5  pop      r12
0x0000ddf7  pop      r14
0x0000ddf9  pop      r15
0x0000ddfb  pop      rbp
0x0000ddfc  ret      
0x0000ddfd  int3     
0x0000ddfe  int3     
0x0000ddff  int3     
0x0000de00  push     rsi
0x0000de01  sub      rsp, 0x20
0x0000de05  mov      rsi, rcx
0x0000de08  mov      rcx, qword ptr [rcx + 0xe0]
0x0000de0f  test     rcx, rcx
0x0000de12  je       0x18000de20
0x0000de14  lock dec dword ptr [rcx + 0xc]
0x0000de18  jne      0x18000de20
0x0000de1a  mov      rax, qword ptr [rcx]
0x0000de1d  call     qword ptr [rax + 8]
0x0000de20  mov      rcx, qword ptr [rsi + 0xc8]
0x0000de27  test     rcx, rcx
0x0000de2a  je       0x18000de4a
0x0000de2c  lea      rax, [rsi + 0x90]
0x0000de33  cmp      rcx, rax
0x0000de36  setne    dl
0x0000de39  mov      rax, qword ptr [rcx]
0x0000de3c  call     qword ptr [rax + 0x20]
0x0000de3f  mov      qword ptr [rsi + 0xc8], 0
0x0000de4a  mov      rcx, qword ptr [rsi + 0x88]
0x0000de51  test     rcx, rcx
0x0000de54  je       0x18000de71
0x0000de56  lea      rax, [rsi + 0x50]
0x0000de5a  cmp      rcx, rax
0x0000de5d  setne    dl
0x0000de60  mov      rax, qword ptr [rcx]
0x0000de63  call     qword ptr [rax + 0x20]
0x0000de66  mov      qword ptr [rsi + 0x88], 0
0x0000de71  mov      rcx, qword ptr [rsi + 0x48]
0x0000de75  test     rcx, rcx
0x0000de78  je       0x18000de92
0x0000de7a  lea      rax, [rsi + 0x10]
0x0000de7e  cmp      rcx, rax
0x0000de81  setne    dl
0x0000de84  mov      rax, qword ptr [rcx]
0x0000de87  call     qword ptr [rax + 0x20]
0x0000de8a  mov      qword ptr [rsi + 0x48], 0
0x0000de92  mov      rsi, qword ptr [rsi + 8]
0x0000de96  test     rsi, rsi
0x0000de99  je       0x18000debe
0x0000de9b  lock dec dword ptr [rsi + 8]
0x0000de9f  jne      0x18000debe
0x0000dea1  mov      rax, qword ptr [rsi]
0x0000dea4  mov      rcx, rsi
0x0000dea7  call     qword ptr [rax]
0x0000dea9  lock dec dword ptr [rsi + 0xc]
0x0000dead  jne      0x18000debe
0x0000deaf  mov      rax, qword ptr [rsi]
0x0000deb2  mov      rcx, rsi
0x0000deb5  add      rsp, 0x20
0x0000deb9  pop      rsi
0x0000deba  jmp      qword ptr [rax + 8]
0x0000debe  add      rsp, 0x20
0x0000dec2  pop      rsi
