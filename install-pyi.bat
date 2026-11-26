@echo off
rem Install PyInstaller into the shared venv (D:\fish\svc\venv).
rem It is a build-only tool: nothing in the singing pipeline imports it.
rem Result -> data\pyi-install.txt
setlocal
cd /d "%~dp0"
set PY="D:\fish\svc\venv\Scripts\python.exe"
set OUT=data\pyi-install.txt
if not exist data mkdir data
echo ==== %DATE% %TIME% ==== > "%OUT%"
%PY% -m pip install --upgrade pyinstaller >> "%OUT%" 2>&1
echo ---- version ---- >> "%OUT%"
%PY% -m PyInstaller --version >> "%OUT%" 2>&1
echo done >> "%OUT%"
type "%OUT%"
pause
