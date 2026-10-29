param(
    [int]$TimeoutSec = 60
)

# 微信 4.1.9.23 重启后会停在"进入微信"确认页 (mmui::LoginWindow)。
# 这里用 UI Automation 直接 Invoke 那个按钮，把这一步自动化掉。
# 前提：本机已验证 AutomationElement.FromHandle + InvokePattern 可用。

$ErrorActionPreference = "Continue"
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes -ErrorAction SilentlyContinue

$LoginClass = "mmui::LoginWindow"
# 主窗口实际是 Qt 窗口 (Qt51514QWindowIcon)；mmui::MainWindow 也保留做兼容。
$MainClasses = @("Qt51514QWindowIcon", "mmui::MainWindow")
$ButtonText = "进入微信"

function Get-WeixinWindowClass($h) {
    try {
        $el = [System.Windows.Automation.AutomationElement]::FromHandle($h)
        return $el.Current.ClassName
    } catch { return $null }
}

function Click-EnterWeixin($h) {
    # 该按钮是 mmui 自绘控件：
    #   - UIA InvokePattern 会"成功"但不触发任何行为
    #   - 合成鼠标事件 (SetCursorPos/mouse_event) 也不生效
    #   - 只有把 WM_LBUTTONDOWN/UP 直接 PostMessage 到窗口才有效（已验证）
    # 坐标要用客户区坐标，所以先取屏幕坐标再 ScreenToClient。
    $ok = $false
    try {
        $root = [System.Windows.Automation.AutomationElement]::FromHandle($h)
        $cond = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty, $ButtonText)
        $found = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
        foreach ($el in $found) {
            if ($el.Current.ControlType -ne [System.Windows.Automation.ControlType]::Button) { continue }
            $r = $el.Current.BoundingRectangle
            if ($r.Width -le 0 -or $r.Height -le 0) { continue }
            $cx = [int]($r.X + $r.Width / 2)
            $cy = [int]($r.Y + $r.Height / 2)
            $pt = New-Object AutoClick2+POINT
            $pt.X = $cx
            $pt.Y = $cy
            [AutoClick2]::ScreenToClient($h, [ref]$pt) | Out-Null
            $lp = [IntPtr](($pt.Y -shl 16) -bor ($pt.X -band 0xFFFF))
            [AutoClick2]::PostMessage($h, 0x0201, [IntPtr]1, $lp) | Out-Null
            Start-Sleep -Milliseconds 200
            [AutoClick2]::PostMessage($h, 0x0202, [IntPtr]0, $lp) | Out-Null
            $ok = $true
            break
        }
    } catch { }
    return $ok
}

if (-not ("AutoClick2" -as [type])) {
    Add-Type @"
using System;using System.Runtime.InteropServices;
public class AutoClick2 {
 [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h,uint m,IntPtr w,IntPtr l);
 [DllImport("user32.dll")] public static extern bool ScreenToClient(IntPtr h, ref POINT p);
 public struct POINT { public int X,Y; }
}
"@
}

$deadline = (Get-Date).AddSeconds($TimeoutSec)
$attempt = 0
while ((Get-Date) -lt $deadline) {
    $procs = Get-Process Weixin -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 }
    if (-not $procs) { Start-Sleep -Seconds 3; continue }

    $loginHwnd = 0
    $sawMain = $false
    foreach ($p in $procs) {
        $cls = Get-WeixinWindowClass $p.MainWindowHandle
        if ($cls -eq $LoginClass) { $loginHwnd = $p.MainWindowHandle }
        elseif ($MainClasses -contains $cls) { $sawMain = $true }
    }

    if ($sawMain -and $loginHwnd -eq 0) {
        Write-Output "already at main window"
        exit 0
    }

    if ($loginHwnd -ne 0) {
        if (Click-EnterWeixin $loginHwnd) {
            $attempt++
            Write-Output "posted click '进入微信' attempt=$attempt"
            Start-Sleep -Seconds 8
            $cls2 = Get-WeixinWindowClass $loginHwnd
            if ($cls2 -ne $LoginClass) {
                Write-Output "advanced to class=$cls2"
                exit 0
            }
            continue
        }
    }
    Start-Sleep -Seconds 3
}

Write-Output "timeout: login window not cleared within ${TimeoutSec}s"
exit 1
