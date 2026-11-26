@echo off
rem Install cryptography (Ed25519) into the shared venv. Additive only.
rem Result -> data\crypto-install.txt
setlocal
cd /d "%~dp0"
set PY="D:\fish\svc\venv\Scripts\python.exe"
set OUT=data\crypto-install.txt
echo ==== %DATE% %TIME% ==== > "%OUT%"
%PY% -m pip install --upgrade cryptography >> "%OUT%" 2>&1
echo ---- check ---- >> "%OUT%"
%PY% -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; import cryptography; print('cryptography', cryptography.__version__, 'ed25519 ok')" >> "%OUT%" 2>&1
echo done >> "%OUT%"
