' 静默启动 wxhook 重注入守护（无窗口）
' 由启动文件夹/计划任务调用，避免弹黑框
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""<PROJECT_ROOT>\reinject_daemon.ps1"" -IntervalSec 15", 0, False
