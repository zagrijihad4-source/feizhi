# feizhi_daemon.ps1 -- feizhi_pc 常驻保活守护
#
# 背景：2026-10-14 早 09:01，feizhi 进程静默消失（日志无异常记录），
#       直到用户察觉「不回消息」才被发现。本守护每 IntervalSec 检查一次，
#       发现进程不在就重新拉起，并记录日志。
#
# 启动方式约束（沿用项目铁律）：
#   用 ([wmiclass]'Win32_Process').Create() 拉起子进程，
#   **不要**用 Start-Process 或 cmd /c start —— 后者在调用方带管道重定向时
#   会因等待管道 EOF 而阻塞，甚至卡死整机。
#
# 日志：<PROJECT_ROOT>\logs\feizhi_daemon.log
# 单实例：state\feizhi_daemon.pid

param(
    [int]$IntervalSec = 30,
    [switch]$Once
)

$ErrorActionPreference = "Continue"

$Root     = "<PROJECT_ROOT>\feizhi_pc"
$Pythonw  = "F:\AI课程软件\Python313\pythonw.exe"
$Runner   = Join-Path $Root "run.py"
$StateDir = Join-Path $Root "state"
$PidFile  = Join-Path $StateDir "feizhi_daemon.pid"
$LogDir   = "<PROJECT_ROOT>\logs"
$Log      = Join-Path $LogDir "feizhi_daemon.log"

New-Item -ItemType Directory -Force -Path $LogDir, $StateDir | Out-Null

function Write-Log([string]$m) {
    "$([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss')) $m" |
        Out-File -FilePath $Log -Append -Encoding UTF8
}

function Find-Feizhi {
    @(Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and ($_.CommandLine -like "*feizhi_pc\run.py*") })
}

function Start-Feizhi {
    if (-not (Test-Path -LiteralPath $Pythonw)) {
        Write-Log "pythonw 不存在: $Pythonw"
        return $false
    }
    try {
        $r = ([wmiclass]'Win32_Process').Create("`"$Pythonw`" `"$Runner`" both")
        if ($r.ReturnValue -eq 0) {
            Write-Log "STARTED pid=$($r.ProcessId)"
            return $true
        }
        Write-Log "START FAILED return=$($r.ReturnValue)"
        return $false
    } catch {
        Write-Log "START EXCEPTION $($_.Exception.Message)"
        return $false
    }
}

# ---- 单实例保护 ----
if (Test-Path -LiteralPath $PidFile) {
    $old = (Get-Content -LiteralPath $PidFile -Raw -ErrorAction SilentlyContinue)
    if ($old -and $old.Trim() -match '^\d+$') {
        if (Get-Process -Id ([int]$old.Trim()) -ErrorAction SilentlyContinue) {
            Write-Log "another daemon running pid=$($old.Trim()); exit"
            exit 0
        }
    }
}
$PID | Out-File -FilePath $PidFile -Encoding ASCII -Force
Write-Log "=== daemon start pid=$PID interval=${IntervalSec}s ==="

$loop = 0
$consecutiveFails = 0

while ($true) {
    $loop++
    $found = Find-Feizhi

    if ($found.Count -eq 0) {
        Write-Log "feizhi NOT running -> restart (loop=$loop)"
        if (Start-Feizhi) {
            # 只做一次轻量确认，**失败不累加计数** —— pythonw 从启动到
            # Process.CommandLine 可被 CIM 查到可能要 30 秒以上（实测 60 秒内起来），
            # 原来把「还在启动」误判成「拉起失败」，连判 5 次就自我暂停 10 分钟，
            # 守护反而比它要守护的进程先停摆。真实失败由下一轮循环自然发现。
            Start-Sleep -Seconds 20
            $after = Find-Feizhi
            if ($after.Count -gt 0) {
                Write-Log "restart verified pid=$($after[0].ProcessId)"
            } else {
                Write-Log "启动中（20s 内未就绪），下一轮再确认"
            }
        }
    } else {
        $consecutiveFails = 0
        if ($loop % 20 -eq 1) {
            Write-Log "feizhi alive pid=$($found[0].ProcessId)"
        }
    }

    if ($Once) { break }
    Start-Sleep -Seconds $IntervalSec
}

Write-Log "=== daemon exit loop=$loop ==="
Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
