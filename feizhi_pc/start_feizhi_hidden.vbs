' 静默启动 feizhi_pc（绯栀自动回复 + 主动消息），无窗口
' 由启动文件夹调用。
'
' 设计约束（重要）：
'   发消息只走 hook 桥 —— 写 bridge\outbox 由微信进程内的 worker 消费，
'   全程不使用 UI 自动化（不模拟鼠标点击、不模拟键盘输入、
'   不做窗口控件操作），即不使用 computer use 发消息。
'
' 用 pythonw.exe 而非 python.exe：避免控制台窗口，也避免 Start-Process
' 带重定向时的阻塞问题。
Set sh = CreateObject("WScript.Shell")
sh.Run """F:\AI课程软件\Python313\pythonw.exe"" ""<PROJECT_ROOT>\feizhi_pc\run.py"" both", 0, False
