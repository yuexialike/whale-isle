@echo off
rem Draw the app icon (make_icon.py); every word it says also lands in data\icon-run.txt
cd /d "%~dp0"
set PY="D:\fish\svc\venv\Scripts\python.exe"
if not exist data mkdir data
echo ---- icon %DATE% %TIME% ---- > data\icon-run.txt
%PY% make_icon.py >> data\icon-run.txt 2>&1
type data\icon-run.txt
echo.
pause
