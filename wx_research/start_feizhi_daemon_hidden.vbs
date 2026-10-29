' 静默启动 feizhi_pc 保活守护（无窗口、常驻）
' 由启动文件夹调用；也可手动 wscript 运行。
'
' 与 start_feizhi_hidden.vbs 的关系：
'   那个脚本负责启动 feizhi 本体（run.py both）；
'   本脚本负责「它挂掉后自动拉起来」，两者互补。
'
' 用 sh.Run(..., 0, False)：0 = 隐藏窗口，False = 不等待 —— 立即返回，
' 不会像 Start-Process 带重定向那样阻塞调用方。
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""<PROJECT_ROOT>\feizhi_daemon.ps1""", 0, False
