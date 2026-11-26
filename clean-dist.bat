@echo off
rem Make dist\YuYu look like a fresh install: nothing but the program, template and
rem an empty plugins folder. Run this right before zipping it up.
rem Deletes ONLY inside dist\YuYu: config.json, workspace, data, license.key,
rem license-key.txt (private), make-code.py, license_pub.py (it lives inside the exe).
cd /d "%~dp0"
set D=dist\YuYu
if not exist "%D%" (
  echo No %D% - build first.
  exit /b 1
)
if exist "%D%\config.json" del /q "%D%\config.json"
if exist "%D%\config.seal" del /q "%D%\config.seal"
if exist "%D%\license.key" del /q "%D%\license.key"
if exist "%D%\license-key.txt" del /q "%D%\license-key.txt"
if exist "%D%\make-code.py" del /q "%D%\make-code.py"
if exist "%D%\license_pub.py" del /q "%D%\license_pub.py"
if exist "%D%\workspace" rmdir /s /q "%D%\workspace"
if exist "%D%\data" rmdir /s /q "%D%\data"
if not exist data mkdir data
echo ---- %DATE% %TIME% ---- > data\dist-clean.txt
dir /b "%D%" >> data\dist-clean.txt
type data\dist-clean.txt
