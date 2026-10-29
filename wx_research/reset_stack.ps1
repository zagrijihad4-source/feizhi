$ErrorActionPreference = "Continue"
$log = "<PROJECT_ROOT>\reset_stack.log"
function W($m){ "$([DateTime]::Now.ToString('HH:mm:ss')) $m" | Out-File -FilePath $log -Append -Encoding UTF8 }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
W "=== reset_stack start IsAdmin=$isAdmin ==="

# 1) 杀掉所有微信相关进程（含提权实例）
foreach ($n in @("Weixin","WeixinUpdate","WeChatUpdate","WeChat")) {
    Get-Process -Name $n -ErrorAction SilentlyContinue | ForEach-Object {
        try { Stop-Process -Id $_.Id -Force -ErrorAction Stop; W "killed $n pid=$($_.Id)" }
        catch { W "kill $n pid=$($_.Id) failed: $($_.Exception.Message)" }
    }
}
Start-Sleep -Seconds 4

$left = @(Get-Process Weixin -ErrorAction SilentlyContinue)
W "weixin remaining: $($left.Count)"
foreach ($p in $left) { W "  still alive pid=$($p.Id)" }

# 2) 清 hook 状态与 bridge 队列
$ctrl = "<PROJECT_ROOT>\wx-basic-bridge\bridge\control"
foreach ($f in @("heartbeat.txt","status.txt","worker_owner.txt","stop.txt")) {
    $t = Join-Path $ctrl $f
    if (Test-Path $t) { try { Remove-Item $t -Force; W "removed $f" } catch { W "cannot remove $f" } }
}
Get-ChildItem "<PROJECT_ROOT>\wx-basic-bridge\bridge\outbox" -Force -ErrorAction SilentlyContinue |
    ForEach-Object { try { Remove-Item $_.FullName -Force; W "cleared outbox/$($_.Name)" } catch { } }

# 3) 清更新缓存
$uc = "$env:APPDATA\Tencent\xwechat\update"
if ($uc -and (Test-Path -LiteralPath $uc)) {
    try { Remove-Item -LiteralPath $uc -Recurse -Force -ErrorAction Stop; W "purged update cache" } catch { W "cache purge failed" }
}

W ("version = " + (Get-Item "C:\Program Files\Tencent\Weixin\Weixin.exe").VersionInfo.FileVersion)
$deny = @((Get-Acl "C:\Program Files\Tencent\Weixin").Access | Where-Object { $_.AccessControlType -eq 'Deny' })
W "install-dir deny rules: $($deny.Count)"
W "=== reset_stack done ==="
