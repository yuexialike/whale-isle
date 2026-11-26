@echo off
rem Play the boot animation once with frame timing, write _boot.log, then close.
rem No pause: the window goes away by itself. Pure ASCII only (cmd reads .bat as ANSI).
cd /d "%~dp0"
"D:\fish\svc\venv\Scripts\python.exe" -m py_compile boot.py
if errorlevel 1 (
  "D:\fish\svc\venv\Scripts\python.exe" -m py_compile boot.py > _boot.log 2>&1
  exit
)
"D:\fish\svc\venv\Scripts\python.exe" boot.py --fps > _boot.log 2>&1
