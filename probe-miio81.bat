@echo off
rem 问一下 192.168.1.81 是不是小爱，结果写 data\miio-81.txt
cd /d "%~dp0"
"D:\fish\svc\venv\Scripts\python.exe" "%~dp0probe-miio81.py"
if errorlevel 1 pause
