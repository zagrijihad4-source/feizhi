$ErrorActionPreference = "Continue"
$log = "<PROJECT_ROOT>\freeze_update.log"
function W($m){ "$([DateTime]::Now.ToString('HH:mm:ss')) $m" | Out-File -FilePath $log -Append -Encoding UTF8 }

W "=== freeze_update start ==="
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
W "running as $($id.Name) IsAdmin=$isAdmin"

$dir = "C:\Program Files\Tencent\Weixin\4.1.9.23"
$upd = Join-Path $dir "WeixinUpdate.exe"

# 1) rename the updater so it cannot launch
if (Test-Path $upd) {
    try {
        Rename-Item -LiteralPath $upd -NewName "WeixinUpdate.exe.frozen" -ErrorAction Stop
        W "RENAMED ok -> WeixinUpdate.exe.frozen"
    } catch {
        W "RENAME failed: $($_.Exception.Message)"
    }
} else {
    W "updater not found at $upd (maybe already frozen)"
}

# 2) stop any live updater process
Get-Process -Name "WeixinUpdate" -ErrorAction SilentlyContinue | ForEach-Object {
    try { Stop-Process -Id $_.Id -Force; W "killed updater pid=$($_.Id)" } catch { W "kill failed pid=$($_.Id): $($_.Exception.Message)" }
}

# 3) list what updater-ish files exist now
Get-ChildItem -LiteralPath $dir -Filter "*pdate*" -ErrorAction SilentlyContinue | ForEach-Object { W "file: $($_.Name) ($($_.Length))" }

# 4) verify
$frozen = Test-Path (Join-Path $dir "WeixinUpdate.exe.frozen")
$orig   = Test-Path $upd
W "VERIFY frozen_present=$frozen original_present=$orig"
W "=== freeze_update done ==="
