$ErrorActionPreference = "Continue"
$log = "<PROJECT_ROOT>\acl_fix.log"
function W($m){ "$([DateTime]::Now.ToString('HH:mm:ss')) $m" | Out-File -FilePath $log -Append -Encoding UTF8 }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
W "=== acl_fix start IsAdmin=$isAdmin ==="

$install = "C:\Program Files\Tencent\Weixin"
W ("version before = " + (Get-Item "$install\Weixin.exe").VersionInfo.FileVersion)

# 拒绝规则必须用 3 参数重载，继承标志单独传
$rights = [Security.AccessControl.FileSystemRights]::Write -bor `
          [Security.AccessControl.FileSystemRights]::Delete -bor `
          [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor `
          [Security.AccessControl.FileSystemRights]::CreateDirectories -bor `
          [Security.AccessControl.FileSystemRights]::CreateFiles -bor `
          [Security.AccessControl.FileSystemRights]::ChangePermissions -bor `
          [Security.AccessControl.FileSystemRights]::TakeOwnership

$inherit = [Security.AccessControl.InheritanceFlags]"ContainerInherit, ObjectInherit"
$propagate = [Security.AccessControl.PropagationFlags]::None
$deny = [Security.AccessControl.AccessControlType]::Deny

foreach ($sid in @("Everyone")) {
    try {
        $acl = Get-Acl -LiteralPath $install
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, $rights, $inherit, $propagate, $deny)
        $acl.AddAccessRule($rule)
        Set-Acl -LiteralPath $install -AclObject $acl
        W "deny rule added for $sid : $rights"
    } catch {
        W "ACL add failed for ${sid}: $($_.Exception.Message)"
    }
}

W "--- VERIFY ---"
W ("deny rules: " + (((Get-Acl -LiteralPath $install).Access | Where-Object { $_.AccessControlType -eq 'Deny' } |
    ForEach-Object { "$($_.IdentityReference) => $($_.FileSystemRights)" }) -join ' | '))
$test = "$install\_writetest.tmp"
try {
    [IO.File]::WriteAllText($test, "x")
    Remove-Item $test -Force -ErrorAction SilentlyContinue
    W "WRITE TEST: STILL WRITABLE (bad)"
} catch {
    W "WRITE TEST: blocked (good)"
}
# 确认微信能否读取自身文件（必须仍可读，否则会起不来）
try {
    $a = [IO.File]::ReadAllText("$install\Weixin.exe.frozen") 2>$null
} catch {}
$readable = Test-Path "$install\4.1.9.23\Weixin.dll"
W "read test (Weixin.dll reachable): $readable"
W "=== acl_fix done ==="
