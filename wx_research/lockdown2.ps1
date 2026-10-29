$ErrorActionPreference = "Continue"
$log = "<PROJECT_ROOT>\lockdown2.log"

function Write-Log($m) {
    "$([DateTime]::Now.ToString('HH:mm:ss')) $m" | Out-File -FilePath $log -Append -Encoding UTF8
}

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Write-Log "=== lockdown2 start IsAdmin=$isAdmin ==="

$install = "C:\Program Files\Tencent\Weixin"
$pkg = "<PROJECT_ROOT>\weixin_4.1.9.23.exe"

# ---- 1) kill processes ----
$names = @("Weixin", "WeixinUpdate", "WeChatUpdate")
foreach ($n in $names) {
    $procs = Get-Process -Name $n -ErrorAction SilentlyContinue
    foreach ($pr in $procs) {
        try {
            Stop-Process -Id $pr.Id -Force -ErrorAction Stop
            Write-Log "killed $n pid=$($pr.Id)"
        } catch {
            Write-Log "kill $n pid=$($pr.Id) failed"
        }
    }
}
Start-Sleep -Seconds 4

# ---- 2) strip existing deny rules on install dir ----
$acl = Get-Acl -LiteralPath $install
$denyList = @()
foreach ($r in $acl.Access) {
    if ($r.AccessControlType -eq [Security.AccessControl.AccessControlType]::Deny) {
        $denyList += $r
    }
}
foreach ($r in $denyList) {
    try {
        $acl.RemoveAccessRule($r) | Out-Null
        Write-Log "removed deny $($r.IdentityReference)"
    } catch {
        Write-Log "remove deny failed"
    }
}
try { Set-Acl -LiteralPath $install -AclObject $acl } catch { }

# ---- 3) purge update caches ----
$caches = @("$env:APPDATA\Tencent\xwechat\update", "$env:APPDATA\Tencent\DeskUpdate")
foreach ($c in $caches) {
    if (Test-Path -LiteralPath $c) {
        try {
            Remove-Item -LiteralPath $c -Recurse -Force -ErrorAction Stop
            Write-Log "purged $c"
        } catch {
            Write-Log "purge failed $c"
        }
    }
}

# ---- 4) reinstall 4.1.9.23 ----
Write-Log "reinstalling 4.1.9.23 ..."
$proc = Start-Process -FilePath $pkg -ArgumentList '/S' -PassThru
$proc | Wait-Process -Timeout 400 -ErrorAction SilentlyContinue
$ver = (Get-Item "$install\Weixin.exe").VersionInfo.FileVersion
Write-Log "post-install version = $ver"
if ($ver -ne "4.1.9.23") {
    Write-Log "ABORT version mismatch"
    exit 1
}

# ---- 5) precise ACL: deny creating subdirectories (blocks new version dir) ----
$targets = @($install)
$subDirs = Get-ChildItem -LiteralPath $install -Directory -ErrorAction SilentlyContinue
foreach ($sd in $subDirs) { $targets += $sd.FullName }

$denyRights = [Security.AccessControl.FileSystemRights]::CreateDirectories -bor [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles
$inheritFlags = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
$propFlags = [Security.AccessControl.PropagationFlags]::None
$denyType = [Security.AccessControl.AccessControlType]::Deny

foreach ($t in $targets) {
    try {
        $a = Get-Acl -LiteralPath $t
        $rule = New-Object Security.AccessControl.FileSystemAccessRule("Everyone", $denyRights, $inheritFlags, $propFlags, $denyType)
        $a.AddAccessRule($rule)
        Set-Acl -LiteralPath $t -AclObject $a
        Write-Log "deny CreateDirectories on $t"
    } catch {
        Write-Log "acl fail $t : $($_.Exception.Message)"
    }
}

# ---- 6) freeze updater ----
$updaters = Get-ChildItem -LiteralPath $install -Recurse -Filter "*Update*.exe" -ErrorAction SilentlyContinue
foreach ($u in $updaters) {
    $t = $u.FullName
    if ($t -notlike "*.frozen") {
        try {
            Rename-Item -LiteralPath $t -NewName ([IO.Path]::GetFileName($t) + ".frozen") -ErrorAction Stop
            Write-Log "renamed $t"
        } catch {
            Write-Log "rename fail $t"
        }
    }
}

# ---- 7) verify ----
Write-Log "--- VERIFY ---"
Write-Log ("version = " + (Get-Item "$install\Weixin.exe").VersionInfo.FileVersion)

$testFile = Join-Path $install "_wtest.tmp"
try {
    [IO.File]::WriteAllText($testFile, "x")
    Remove-Item $testFile -Force -ErrorAction SilentlyContinue
    Write-Log "file write: OK"
} catch {
    Write-Log "file write: BLOCKED (would break wechat)"
}

$testDir = Join-Path $install ("_dtest_" + [int](Get-Date -UFormat %s))
try {
    New-Item -ItemType Directory -Path $testDir -ErrorAction Stop | Out-Null
    Remove-Item $testDir -Force -ErrorAction SilentlyContinue
    Write-Log "dir create: STILL ALLOWED (upgrade may succeed)"
} catch {
    Write-Log "dir create: BLOCKED (upgrade should fail)"
}

Write-Log "=== lockdown2 done ==="
