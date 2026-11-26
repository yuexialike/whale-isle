@echo off
setlocal
rem Debug launcher: keeps the console so errors stay visible.
set SRC=%~dp0
set DST=D:\fish\home

if not exist "%DST%" mkdir "%DST%"

copy /Y "%SRC%*.py" "%DST%\" >nul
copy /Y "%SRC%config.json" "%DST%\" >nul
rem figure/ must follow too: it holds the layered figure art and the kit js (11-02)
if exist "%SRC%figure" xcopy /E /I /Y /Q "%SRC%figure" "%DST%figure\" >nul
rem plugins/ must follow too: 11-03 漏了这一步，D:\fish\home 里跑的一直是旧的 qq.py
if exist "%SRC%plugins" xcopy /E /I /Y /Q "%SRC%plugins" "%DST%plugins\" >nul

cd /d "%DST%"
echo ===== starting =====
"D:\fish\svc\venv\Scripts\python.exe" main.py

echo.
echo ===== exited =====
pause
