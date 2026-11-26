@echo off
rem Make the glowing line art for the boot intro. Result: data\boot\02-lines.png
rem Pure ASCII only: cmd reads .bat with the ANSI codepage.
cd /d "%~dp0"
"D:\fish\svc\venv\Scripts\python.exe" make_lineart.py 06-front.png.png > _lineart.log 2>&1
type _lineart.log
pause
