@echo off
rem Measure boot animation frame gaps. Result goes to _boot.log.
rem Keep this file pure ASCII: cmd reads .bat with the ANSI codepage, Chinese breaks it.
cd /d "%~dp0"
"D:\fish\svc\venv\Scripts\python.exe" -m py_compile boot.py
"D:\fish\svc\venv\Scripts\python.exe" boot.py --fps > _boot.log 2>&1
echo done. see _boot.log
pause
