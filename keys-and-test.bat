@echo off
rem Make a fresh Ed25519 keypair, then run the six door tests with it.
rem Result -> data\keys.txt
rem WARNING: new keypair = every code issued before is dead.
cd /d "%~dp0"
set PY="D:\fish\svc\venv\Scripts\python.exe"
set OUT=data\keys.txt
echo ==== keys %DATE% %TIME% ==== > "%OUT%"
%PY% make-keys.py --force >> "%OUT%" 2>&1
echo ---- tests ---- >> "%OUT%"
%PY% test_license.py >> "%OUT%" 2>&1
echo ---- exit %ERRORLEVEL% ---- >> "%OUT%"
