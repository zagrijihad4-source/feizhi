$ErrorActionPreference = "Continue"
$log = "<PROJECT_ROOT>\cleanup_updater.log"
function W($m){ "$([DateTime]::Now.ToString('HH:mm:ss')) $m" | Out-File -FilePath $log -Append -Encoding UTF8 }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
W "=== cleanup start IsAdmin=$isAdmin ==="

# 1) 杀掉所有更新器进程（含孤儿）
foreach ($n in @("WeixinUpdate","WeChatUpdate")) {
    Get-Process -Name $n -ErrorAction SilentlyContinue | ForEach-Object {
        try { Stop-Process -Id $_.Id -Force -ErrorAction Stop; W "killed $n pid=$($_.Id)" }
        catch { W "kill $n pid=$($_.Id) FAILED: $($_.Exception.Message)" }
    }
}
Start-Sleep -Seconds 2
foreach ($n in @("WeixinUpdate","WeChatUpdate")) {
    $left = Get-Process -Name $n -ErrorAction SilentlyContinue
    W "$n remaining: $(($left | Measure-Object).Count)"
}

# 2) 清更新缓存
$uc = "$env:APPDATA\Tencent\xwechat\update"
if (Test-Path -LiteralPath $uc) {
    try { Remove-Item -LiteralPath $uc -Recurse -Force -ErrorAction Stop; W "purged update cache" }
    catch { W "purge cache failed: $($_.Exception.Message)" }
}

# 3) 重新确认安装目录的 deny ACL 仍在
$install = "C:\Program Files\Tencent\Weixin"
$denies = (Get-Acl -LiteralPath $install).Access | Where-Object { $_.AccessControlType -eq 'Deny' }
W ("deny rules: " + (($denies | ForEach-Object { "$($_.IdentityReference):$($_.FileSystemRights)" }) -join ' | '))

# 4) 更新器文件状态
W ("4.1.9.23 update files: " + ((Get-ChildItem "$install\4.1.9.23" -Filter '*Update*' -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }) -join ', '))
W ("version = " + (Get-Item "$install\Weixin.exe").VersionInfo.FileVersion)

W "=== cleanup done ==="
