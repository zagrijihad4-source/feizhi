@echo off
rem run_inject.cmd <pid>
rem 用纯 ASCII 的 cmd 包装器启动注入器，避开 PowerShell 侧的中文路径/重定向问题。
setlocal
set PYEXE=F:\AI课程软件\Python313\python.exe
set INJ=<PROJECT_ROOT>\wx-basic-bridge\python\tools\inject_bridge.py
if not exist "%PYEXE%" set PYEXE=python
"%PYEXE%" "%INJ%" --pid %1
