@echo off
rem End-to-end door test on the FROZEN build:
rem   1) sign a real code for this machine (source tree, private key present)
rem   2) drop it next to the exe as license.key
rem   3) run the exe in self-test mode -> it must now say the code passes
rem Results -> data\door-frozen.txt and dist\YuYu\data\license-selftest.txt
cd /d "%~dp0"
set PY="D:\fish\svc\venv\Scripts\python.exe"

rem start clean: no code on the desk
if exist "dist\YuYu\license.key" del /q "dist\YuYu\license.key"
start "" /wait "dist\YuYu\YuYu.exe" --license-selftest
copy /Y "dist\YuYu\data\license-selftest.txt" "data\door-frozen-before.txt" >nul

%PY% prep-door-test.py >nul 2>&1
start "" /wait "dist\YuYu\YuYu.exe" --license-selftest
copy /Y "dist\YuYu\data\license-selftest.txt" "data\door-frozen-after.txt" >nul
