$ErrorActionPreference = "Continue"
$log = "<PROJECT_ROOT>\protect_update.log"
function W($m){ "$([DateTime]::Now.ToString('HH:mm:ss')) $m" | Out-File -FilePath $log -Append -Encoding UTF8 }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
W "=== protect_v2 start IsAdmin=$isAdmin ==="

$install = "C:\Program Files\Tencent\Weixin"

# ---- 1) 确认安装目录没有残留的全局 Deny（那会挡住微信自身启动时的写入） ----
$acl = Get-Acl -LiteralPath $install
$denies = @($acl.Access | Where-Object { $_.AccessControlType -eq 'Deny' })
W "install-dir deny rules: $($denies.Count)"
foreach ($r in $denies) {
    try { $acl.RemoveAccessRule($r) | Out-Null; W "removed deny on install dir: $($r.IdentityReference)" } catch { }
}
try { Set-Acl -LiteralPath $install -AclObject $acl } catch { }
W ("install-dir deny after cleanup: " + (@((Get-Acl -LiteralPath $install).Access | Where-Object { $_.AccessControlType -eq 'Deny' }).Count))

# ---- 2) 清更新缓存 ----
foreach ($c in @("$env:APPDATA\Tencent\xwechat\update")) {
    if (Test-Path -LiteralPath $c) {
        try { Remove-Item -LiteralPath $c -Recurse -Force -ErrorAction Stop; W "purged $c" }
        catch { W "purge failed $c : $($_.Exception.Message)" }
    }
}

# ---- 3) 冻结更新器：改名 + 对上锁的文件加 Deny Execute ----
$denyExec = [Security.AccessControl.FileSystemRights]::ExecuteFile -bor [Security.AccessControl.FileSystemRights]::ReadAndExecute
$updaters = Get-ChildItem -LiteralPath $install -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "*Update*.exe" }

foreach ($u in $updaters) {
    $target = $u.FullName
    if ($target -notlike "*.frozen") {
        $newName = $target + ".frozen"
        try {
            Rename-Item -LiteralPath $target -NewName ([IO.Path]::GetFileName($newName)) -ErrorAction Stop
            W "renamed: $target"
            $target = $newName
        } catch {
            W "rename failed $target : $($_.Exception.Message)"
        }
    }
}

# 对所有更新器文件（含 .frozen）加 Deny Execute，双保险
foreach ($u in (Get-ChildItem -LiteralPath $install -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like "*Update*" })) {
    try {
        $fa = Get-Acl -LiteralPath $u.FullName
        $existing = @($fa.Access | Where-Object { $_.AccessControlType -eq 'Deny' })
        if ($existing.Count -eq 0) {
            $rule = New-Object Security.AccessControl.FileSystemAccessRule(
                "Everyone", $denyExec, [Security.AccessControl.AccessControlType]::Deny)
            $fa.AddAccessRule($rule)
            Set-Acl -LiteralPath $u.FullName -AclObject $fa
            W "deny-exec on: $($u.Name)"
        }
    } catch { W "acl fail $($u.Name): $($_.Exception.Message)" }
}

# ---- 4) hosts 封更新下载域 ----
$hosts = "$env:SystemRoot\System32\drivers\etc\hosts"
$marker = "# wxhook-freeze"
try {
    $cur = Get-Content -LiteralPath $hosts -Raw -ErrorAction SilentlyContinue
    if ($cur -notmatch [regex]::Escape($marker)) {
        $block = "`r`n$marker`r`n127.0.0.1 dldir1.qq.com $marker`r`n127.0.0.1 dldir1v6.qq.com $marker`r`n127.0.0.1 dldir.qq.com $marker`r`n127.0.0.1 dldir2.qq.com $marker`r`n127.0.0.1 dldir3.qq.com $marker`r`n# wxhook-freeze-end`r`n"
        Add-Content -LiteralPath $hosts -Value $block -ErrorAction Stop
        W "hosts blocked (dldir*)"
    } else { W "hosts already blocked" }
} catch { W "hosts write failed: $($_.Exception.Message)" }

# ---- 5) 校验：目录必须仍可写（否则微信启动会异常） ----
$t = Join-Path $install "_protect_test.tmp"
try {
    [IO.File]::WriteAllText($t, "x")
    Remove-Item $t -Force -ErrorAction SilentlyContinue
    W "install dir WRITABLE (good - wechat can start)"
} catch { W "install dir NOT writable (BAD)" }

# ---- 6) 用 Start-Process 确认微信本体仍可执行 ----
try {
    $p = Start-Process -FilePath (Join-Path $install "Weixin.exe") -PassThru -ErrorAction Stop
    W "Weixin.exe launch ok pid=$($p.Id)"
    Start-Sleep -Seconds 6
    $p.Refresh()
    W "after 6s exited=$($p.HasExited)"
} catch { W "Weixin.exe launch FAILED: $($_.Exception.Message)" }

W ("version = " + (Get-Item (Join-Path $install "Weixin.exe")).VersionInfo.FileVersion)
W "=== protect_v2 done ==="
