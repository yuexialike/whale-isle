@echo off
rem Make a pure black 2560x1600 frame for the first-frame slot. Result: data\boot\00-black.png
rem Pure ASCII only: cmd reads .bat with the ANSI codepage.
cd /d "%~dp0"
"D:\fish\svc\venv\Scripts\python.exe" make_black.py > _black.log 2>&1
echo ---
type _black.log
pause
