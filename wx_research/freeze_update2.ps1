$ErrorActionPreference = "Continue"
$log = "<PROJECT_ROOT>\freeze_update2.log"
function W($m){ "$([DateTime]::Now.ToString('HH:mm:ss')) $m" | Out-File -FilePath $log -Append -Encoding UTF8 }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
W "=== freeze v2 start as $($id.Name) IsAdmin=$isAdmin ==="

# ---- 1) kill anything updater-shaped ----
foreach ($n in @("WeixinUpdate","WeChatUpdate","DeskUpdate","wxupdate")) {
    Get-Process -Name $n -ErrorAction SilentlyContinue | ForEach-Object {
        try { Stop-Process -Id $_.Id -Force -ErrorAction Stop; W "killed $n pid=$($_.Id)" }
        catch { W "kill $n pid=$($_.Id) failed: $($_.Exception.Message)" }
    }
}

# ---- 2) rename updater executables (both generations) ----
$targets = @(
    "C:\Program Files\Tencent\Weixin\4.1.9.23\WeixinUpdate.exe",
    "C:\ProgramData\Tencent\WeChat\WeChatUpdate.exe"
)
foreach ($t in $targets) {
    if (-not (Test-Path -LiteralPath $t)) { W "absent: $t"; continue }
    if ($t -like "*.frozen") { continue }
    try {
        Rename-Item -LiteralPath $t -NewName ([IO.Path]::GetFileName($t) + ".frozen") -ErrorAction Stop
        W "renamed -> $t.frozen"
    } catch { W "rename failed $t : $($_.Exception.Message)" }
}

# ---- 3) deny execute on updater files we just renamed (belt and braces) ----
Get-ChildItem "C:\Program Files\Tencent\Weixin\4.1.9.23" -Filter "*Update*.frozen" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $acl = Get-Acl -LiteralPath $_.FullName
        $rule = New-Object Security.AccessControl.FileSystemAccessRule("BUILTIN\Users","ExecuteFile","Deny")
        $acl.SetAccessRule($rule)
        Set-Acl -LiteralPath $_.FullName -AclObject $acl
        W "ACL deny-exec added: $($_.Name)"
    } catch { W "ACL failed $($_.Name): $($_.Exception.Message)" }
}

# ---- 4) purge stale download caches so nothing can be silently applied ----
$caches = @(
    "$env:APPDATA\Tencent\xwechat\update",
    "$env:APPDATA\Tencent\DeskUpdate"
)
foreach ($c in $caches) {
    if (-not (Test-Path -LiteralPath $c)) { W "cache absent: $c"; continue }
    try {
        $sz = (Get-ChildItem -LiteralPath $c -Recurse -File -Force -ErrorAction SilentlyContinue |
               Measure-Object -Property Length -Sum).Sum
        Remove-Item -LiteralPath $c -Recurse -Force -ErrorAction Stop
        W "purged cache: $c ($([int]($sz/1MB)) MB freed)"
    } catch { W "purge failed $c : $($_.Exception.Message)" }
}

# ---- 5) block update endpoints in hosts ----
$hosts = "$env:SystemRoot\System32\drivers\etc\hosts"
$marker = "# wxhook-freeze"
$entries = @(
    "127.0.0.1 dldir1.qq.com",
    "127.0.0.1 dldir1v6.qq.com",
    "127.0.0.1 dldir.qq.com",
    "127.0.0.1 dldir2.qq.com",
    "127.0.0.1 dldir3.qq.com"
)
# NOTE: deliberately NOT blocking *.weixin.qq.com / *.wechat.com -- those carry
# login and message transport; blocking them would break the client entirely.
try {
    $cur = Get-Content -LiteralPath $hosts -Raw -ErrorAction SilentlyContinue
    if ($cur -notmatch [regex]::Escape($marker)) {
        $block = "`r`n$marker`r`n" + (($entries | ForEach-Object { "$_ $marker" }) -join "`r`n") + "`r`n# wxhook-freeze-end`r`n"
        Add-Content -LiteralPath $hosts -Value $block -ErrorAction Stop
        W "hosts: added $($entries.Count) block entries"
    } else {
        W "hosts: already blocked"
    }
} catch { W "hosts write failed: $($_.Exception.Message)" }

# ---- 6) verify ----
W "--- VERIFY ---"
W ("Weixin.exe version = " + (Get-Item "C:\Program Files\Tencent\Weixin\Weixin.exe").VersionInfo.FileVersion)
W ("4.1.9.23 dir: " + ((Get-ChildItem "C:\Program Files\Tencent\Weixin\4.1.9.23" -Filter "*Update*" -ErrorAction SilentlyContinue | ForEach-Object { $_.Name }) -join ', '))
W ("update cache exists: " + (Test-Path "$env:APPDATA\Tencent\xwechat\update"))
W ("hosts blocked: " + ((Select-String -Path $hosts -Pattern 'dldir1' -SimpleMatch -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0))
W "=== freeze v2 done ==="
