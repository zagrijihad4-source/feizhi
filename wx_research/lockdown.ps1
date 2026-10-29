$ErrorActionPreference = "Continue"
$log = "<PROJECT_ROOT>\lockdown.log"
function W($m){ "$([DateTime]::Now.ToString('HH:mm:ss')) $m" | Out-File -FilePath $log -Append -Encoding UTF8 }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
W "=== lockdown start as $($id.Name) IsAdmin=$isAdmin ==="

$install = "C:\Program Files\Tencent\Weixin"
$pkg = "<PROJECT_ROOT>\weixin_4.1.9.23.exe"

# ---- 1) kill wechat + updaters ----
foreach ($n in @("WeixinUpdate","WeChatUpdate","Weixin")) {
    Get-Process -Name $n -ErrorAction SilentlyContinue | ForEach-Object {
        try { Stop-Process -Id $_.Id -Force -ErrorAction Stop; W "killed $n pid=$($_.Id)" } catch { W "kill $n pid=$($_.Id) failed" }
    }
}
Start-Sleep -Seconds 3

# ---- 2) strip any deny-ACL we previously placed, so reinstall can write ----
$existing = Get-Acl -LiteralPath $install -ErrorAction SilentlyContinue
if ($existing) {
    $existing.Access | Where-Object { $_.AccessControlType -eq 'Deny' } | ForEach-Object {
        try { $existing.RemoveAccessRule($_) | Out-Null; W "removed deny rule: $($_.IdentityReference) $($_.FileSystemRights)" } catch {}
    }
    try { Set-Acl -LiteralPath $install -AclObject $existing; W "cleaned deny rules on install dir" } catch { W "clean failed: $($_.Exception.Message)" }
}

# ---- 3) purge update caches again ----
foreach ($c in @("$env:APPDATA\Tencent\xwechat\update")) {
    if (Test-Path -LiteralPath $c) {
        try { Remove-Item -LiteralPath $c -Recurse -Force -ErrorAction Stop; W "purged $c" }
        catch { W "purge failed $c : $($_.Exception.Message)" }
    }
}

# ---- 4) reinstall 4.1.9.23 ----
W "reinstalling 4.1.9.23 ..."
$p = Start-Process -FilePath $pkg -ArgumentList '/S' -PassThru
$p | Wait-Process -Timeout 400 -ErrorAction SilentlyContinue
$ver = (Get-Item "$install\Weixin.exe").VersionInfo.FileVersion
W "post-install version = $ver"
if ($ver -ne "4.1.9.23") { W "ABORT: version is not 4.1.9.23"; exit 1 }

# ---- 5) THE FIX: deny write/delete to the install tree, for everyone ----
# 更新器是靠"静默提权"绕过 Users 只读限制的（本机 ConsentPromptBehaviorAdmin=0），
# 所以必须显式拒绝 Everyone，提权后也挡得住。
$rights = [Security.AccessControl.FileSystemRights]"Write,Delete,DeleteSubdirectoriesAndFiles,ChangePermissions,TakeOwnership"
foreach ($sid in @("Everyone", "BUILTIN\Users")) {
    try {
        $acl = Get-Acl -LiteralPath $install
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, $rights, "ContainerInherit,ObjectInherit", "None", "Deny")
        $acl.AddAccessRule($rule)
        Set-Acl -LiteralPath $install -AclObject $acl
        W "deny-write ACL added for $sid"
    } catch { W "ACL add failed for ${sid}: $($_.Exception.Message)" }
}

# ---- 6) verify ----
W "--- VERIFY ---"
W ("version = " + (Get-Item "$install\Weixin.exe").VersionInfo.FileVersion)
$test = "$install\_writetest.tmp"
try {
    [IO.File]::WriteAllText($test, "x")
    Remove-Item $test -Force -ErrorAction SilentlyContinue
    W "WRITE TEST: still writable -> deny ACL NOT effective"
} catch {
    W "WRITE TEST: write blocked (good) -> $($_.Exception.Message.Split([char]10)[0])"
}
$denies = (Get-Acl -LiteralPath $install).Access | Where-Object { $_.AccessControlType -eq 'Deny' }
W ("deny rules now: " + (($denies | ForEach-Object { "$($_.IdentityReference):$($_.FileSystemRights)" }) -join ' | '))
W "=== lockdown done ==="
