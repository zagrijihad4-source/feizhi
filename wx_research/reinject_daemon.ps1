param(
    [switch]$Once,
    [int]$IntervalSec = 20
)

# wxhook auto re-inject daemon.
#   WeChat restart -> click through the login confirm page -> inject hook DLL.
# Runs forever unless -Once is given.

$ErrorActionPreference = "Continue"
$LogDir    = "<PROJECT_ROOT>\logs"
$Log       = Join-Path $LogDir "reinject.log"
$PidFile   = Join-Path $LogDir "reinject.pid"
$Injector  = "<PROJECT_ROOT>\reinject.py"
$HookName  = "wx_hook_bridge"
$Supported = "4.1.9.23"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function W($m) {
    "$([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss')) $m" | Out-File -FilePath $Log -Append -Encoding UTF8
}

function Resolve-Python {
    $c = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $cands = @("F:\AI课程软件\Python313\python.exe", "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe")
    foreach ($p in $cands) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}
$Python = Resolve-Python

function Test-AlreadyRunning {
    if (-not (Test-Path $PidFile)) { return $false }
    $old = (Get-Content $PidFile -Raw -ErrorAction SilentlyContinue)
    if (-not $old) { return $false }
    $old = $old.Trim()
    if ($old -notmatch '^\d+$') { return $false }
    return [bool](Get-Process -Id ([int]$old) -ErrorAction SilentlyContinue)
}

function Get-MainTargets {
    $out = @()
    $procs = Get-Process Weixin -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        try {
            if ($p.MainWindowHandle -eq 0) { continue }
            $dll = $p.Modules | Where-Object { $_.ModuleName -eq 'Weixin.dll' }
            if (-not $dll) { continue }
            $hasHook = [bool]($p.Modules | Where-Object { $_.ModuleName -like "$HookName*" })
            $out += [pscustomobject]@{
                Pid     = $p.Id
                Version = $dll.FileVersionInfo.FileVersion
                HasHook = $hasHook
            }
        } catch {
        }
    }
    return $out
}

function Invoke-HookInject($targetPid) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Python
    $psi.Arguments = '"' + $Injector + '"'
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.WorkingDirectory = "<PROJECT_ROOT>"

    try {
        $proc = [System.Diagnostics.Process]::Start($psi)
    } catch {
        W "pid=$targetPid injector start FAILED: $($_.Exception.Message)"
        return $false
    }

    $outTask = $proc.StandardOutput.ReadToEndAsync()
    $errTask = $proc.StandardError.ReadToEndAsync()

    $loaded = $false
    $deadline = (Get-Date).AddSeconds(100)
    while ((Get-Date) -lt $deadline) {
        if ($proc.WaitForExit(3000)) { break }
        try {
            $t = Get-Process -Id $targetPid -ErrorAction Stop
            if ($t.Modules | Where-Object { $_.ModuleName -like "$HookName*" }) {
                $loaded = $true
                break
            }
        } catch {
            break
        }
    }

    if (-not $proc.HasExited) {
        try { $proc.Kill() } catch { }
        try { $proc.WaitForExit(5000) | Out-Null } catch { }
    }

    if (-not $loaded) {
        try {
            $t = Get-Process -Id $targetPid -ErrorAction Stop
            if ($t.Modules | Where-Object { $_.ModuleName -like "$HookName*" }) { $loaded = $true }
        } catch {
        }
    }

    $o = ""
    $e = ""
    try { $o = $outTask.Result } catch { }
    try { $e = $errTask.Result } catch { }
    if ($o) { W "pid=$targetPid out: $(($o.Trim() -replace "`r?`n", ' | '))" }
    if ($e) { W "pid=$targetPid err: $(($e.Trim() -replace "`r?`n", ' | '))" }

    if ($loaded) {
        W "pid=$targetPid INJECT VERIFIED"
        return $true
    }
    W "pid=$targetPid inject NOT verified"
    return $false
}

if (Test-AlreadyRunning) {
    W "another daemon already running; exit"
    exit 0
}
$PID | Out-File -FilePath $PidFile -Encoding ASCII -Force
W "=== daemon start pid=$PID once=$Once interval=${IntervalSec}s python=$Python ==="

$loop = 0
$running = $true
while ($running) {
    $loop++

    # 微信重启后会自行进入主界面（登录态被记住），实测 20s 出现 LoginWindow、
    # 30s 自动切到 MainWindow，全程无需任何 UI 点击。
    # 因此这里不调用 auto_login（那属于 computer use），只等窗口就绪后注入。

    $targets = Get-MainTargets
    if (-not $targets -or $targets.Count -eq 0) {
        if ($loop % 15 -eq 1) { W "no Weixin host with Weixin.dll" }
    } else {
        foreach ($t in $targets) {
            if ($t.Version -ne $Supported) {
                # 版本被改（微信自行升级）-> 兜底触发降级，带频率限制
                W "pid=$($t.Pid) version=$($t.Version) != $Supported -> auto-downgrade"
                $now = Get-Date
                $cooldownMin = 10
                if (-not $script:lastDowngrade -or ($now - $script:lastDowngrade).TotalMinutes -gt $cooldownMin) {
                    $script:lastDowngrade = $now
                    $script:downgradeAt = $now
                    try {
                        Start-Process -FilePath "powershell.exe" `
                            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass",
                                            "-File", "<PROJECT_ROOT>\lockdown2.ps1") `
                            -Verb RunAs -WindowStyle Hidden -ErrorAction Stop
                        W "triggered lockdown2.ps1 (elevated, silent UAC)"
                    } catch {
                        W "downgrade trigger FAILED: $($_.Exception.Message)"
                    }
                } else {
                    $wait = [int]($cooldownMin - ($now - $script:lastDowngrade).TotalMinutes)
                    W "downgrade attempted recently; cooldown ${wait}min left"
                }
                continue
            }
            if ($t.HasHook) {
                if ($loop % 15 -eq 1) { W "pid=$($t.Pid) hook already loaded" }
                continue
            }
            W "pid=$($t.Pid) hook MISSING -> inject"
            [void](Invoke-HookInject $t.Pid)
        }
    }

    # 降级刚跑过 -> 微信会被关掉，这里负责把它拉起来（只做一次）
    if ($targets.Count -eq 0 -and $script:downgradeAt) {
        $elapsed = ((Get-Date) - $script:downgradeAt).TotalSeconds
        if ($elapsed -gt 60 -and $elapsed -lt 300) {
            W "relaunching Weixin after downgrade"
            try {
                $rr = ([wmiclass]'Win32_Process').Create("C:\Program Files\Tencent\Weixin\Weixin.exe")
                W "relaunch return=$($rr.ReturnValue)"
            } catch {
                W "relaunch failed: $($_.Exception.Message)"
            }
            $script:downgradeAt = $null
        }
    }

    if ($Once) { $running = $false } else { Start-Sleep -Seconds $IntervalSec }
}

W "=== daemon exit loop=$loop ==="
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
