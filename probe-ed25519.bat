@echo off
rem Read-only: which ed25519 options are already in the venv?
rem Result -> data\ed25519.txt
cd /d "%~dp0"
set PY="D:\fish\svc\venv\Scripts\python.exe"
set OUT=data\ed25519.txt
echo ==== probe ==== > "%OUT%"
%PY% -c "import cryptography, sys; print('cryptography', cryptography.__version__)" >> "%OUT%" 2>&1
%PY% -c "import nacl; print('pynacl', nacl.__version__)" >> "%OUT%" 2>&1
%PY% -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; print('ed25519 ok')" >> "%OUT%" 2>&1
echo done >> "%OUT%"
