$ErrorActionPreference = "Continue"
$log = "<PROJECT_ROOT>\acl_remove.log"
function W($m){ "$([DateTime]::Now.ToString('HH:mm:ss')) $m" | Out-File -FilePath $log -Append -Encoding UTF8 }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
W "=== acl_remove start IsAdmin=$isAdmin ==="

$install = "C:\Program Files\Tencent\Weixin"
$acl = Get-Acl -LiteralPath $install
$denies = $acl.Access | Where-Object { $_.AccessControlType -eq 'Deny' }
W ("existing deny rules: " + (($denies | ForEach-Object { "$($_.IdentityReference):$($_.FileSystemRights)" }) -join ' | '))

foreach ($rule in $denies) {
    try {
        $acl.RemoveAccessRule($rule) | Out-Null
        W "removed deny: $($rule.IdentityReference) $($rule.FileSystemRights)"
    } catch {
        W "remove failed: $($_.Exception.Message)"
    }
}
try {
    Set-Acl -LiteralPath $install -AclObject $acl
    W "acl written back"
} catch {
    W "Set-Acl failed: $($_.Exception.Message)"
}

$now = (Get-Acl -LiteralPath $install).Access | Where-Object { $_.AccessControlType -eq 'Deny' }
W ("deny rules now: " + (($now | Measure-Object).Count) + " counts")

$test = Join-Path $install "_wtest.tmp"
try {
    [IO.File]::WriteAllText($test, "x")
    Remove-Item $test -Force -ErrorAction SilentlyContinue
    W "WRITE TEST: install dir is writable again"
} catch {
    W "WRITE TEST: still blocked"
}
W "=== acl_remove done ==="
