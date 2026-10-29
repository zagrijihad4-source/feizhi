param(
    [switch]$SyntaxOnly,
    [string]$OutFile = "<PROJECT_ROOT>\dist\wx_hook_bridge.dll"
)

$ErrorActionPreference = "Stop"
$NativeRoot = "<PROJECT_ROOT>\wx-basic-bridge\native\wx_hook_bridge"
$IncludeDir = Join-Path $NativeRoot "src\include"
$BuildDir   = "<PROJECT_ROOT>\build"
$BinDir     = "C:\Users\api62\AppData\Local\Microsoft\WinGet\Packages\MartinStorsjo.LLVM-MinGW.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\llvm-mingw-20260908-ucrt-x86_64\bin"
$Clang      = Join-Path $BinDir "clang.exe"

$Sources = @(
    "src\wx_hook_bridge.c",
    "src\modules\runtime.c",
    "src\modules\paths.c",
    "src\modules\memory.c",
    "src\modules\text.c",
    "src\modules\file_io.c",
    "src\modules\wechat_string.c",
    "src\modules\protocol.c",
    "src\modules\owner.c",
    "src\modules\send_runtime.c",
    "src\modules\send_text.c",
    "src\modules\send_image.c",
    "src\modules\send_sticker.c",
    "src\modules\send_sticker_tpl.c",
    "src\modules\receive.c",
    "src\modules\outbox.c",
    "src\modules\lifecycle.c"
) | ForEach-Object { Join-Path $NativeRoot $_ }

if (-not (Test-Path $Clang)) { throw "clang not found: $Clang" }
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutFile) | Out-Null

# MinGW 静态自包含: 不依赖 msvcrt runtime DLL，注入更可靠
$CFlags = @(
    "--target=x86_64-w64-windows-gnu",
    "-c", "-O2", "-w", "-fms-extensions", "-DWIN32_LEAN_AND_MEAN",
    "-D_WIN32_WINNT=0x0A00", "-DUNICODE", "-D_UNICODE",
    "-fno-stack-protector", "-fno-asynchronous-unwind-tables",
    "-I$IncludeDir"
)

$objects = @()
$fail = 0
foreach ($src in $Sources) {
    $name = [System.IO.Path]::GetFileNameWithoutExtension($src)
    $obj  = Join-Path $BuildDir "$name.o"
    $objects += $obj
    if ($SyntaxOnly) {
        & $Clang @CFlags "-fsyntax-only" $src 2>&1 | ForEach-Object { "[$name] $_" }
    } else {
        $out = & $Clang @CFlags "-o" $obj $src 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[$name] COMPILE FAILED"
            $out | ForEach-Object { "  $_" }
            $fail = 1
            break
        } else {
            Write-Host "[$name] ok"
        }
    }
    if ($SyntaxOnly -and $LASTEXITCODE -ne 0) { $fail = 1 }
}

if ($SyntaxOnly) {
    if ($fail -eq 0) { Write-Host "SYNTAX OK - all sources parse" }
    exit $fail
}

if ($fail -ne 0) { exit 1 }

$link = @(
    "--target=x86_64-w64-windows-gnu",
    "-shared", "-o", $OutFile,
    "-static", "-static-libgcc",
    "-Wl,--kill-at",
    "-lkernel32", "-luser32", "-lpsapi"
) + $objects

& $Clang @link 2>&1 | ForEach-Object { "  $_" }
if ($LASTEXITCODE -ne 0) { Write-Host "LINK FAILED"; exit 1 }
Write-Host "built: $OutFile"
