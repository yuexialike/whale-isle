@echo off
rem Build the app folder: dist\WhaleIsle\ (exe + files).
rem NOTE 2026-11-01: this is only the raw build. To make something you can hand to
rem someone else, run pack_beta.py - it builds, stages, scrubs and zips in one go.
rem 1) needs PyInstaller in this venv  2) packages  3) copies template  4) makes sure
rem the private key and the signing tool never travel with it.
rem ASCII only on purpose: Chinese text in .bat makes cmd parse wrong.
setlocal
cd /d "%~dp0"

set PY="D:\fish\svc\venv\Scripts\python.exe"
set OUT=data\build.txt
if not exist data mkdir data
echo ==== build %DATE% %TIME% ==== > "%OUT%"

%PY% -m PyInstaller --version >> "%OUT%" 2>&1
if errorlevel 1 (
  echo NO PYINSTALLER in this venv: %PY%
  echo Install it first:  %PY% -m pip install pyinstaller
  echo %PY% -m pip install pyinstaller >> "%OUT%"
  echo ---- stopped, nothing built ----
  pause
  exit /b 1
)

echo ---- compiling ---- >> "%OUT%"
%PY% -m PyInstaller --noconfirm --clean newhouse.spec >> "%OUT%" 2>&1
if errorlevel 1 (
  echo BUILD FAILED, see %OUT%
  pause
  exit /b 1
)

set DIST=dist\WhaleIsle
if not exist "%DIST%" (
  echo No %DIST% after build - something is off.
  pause
  exit /b 1
)

rem template/ sits NEXT TO the exe: after freezing, home = the exe folder,
rem and firstrun looks for template there, not inside the packed archive.
if exist template (
  if not exist "%DIST%\template" mkdir "%DIST%\template"
  copy /Y template\*.md "%DIST%\template\" >> "%OUT%" 2>&1
)

rem the 2D figure also sits NEXT TO the exe: firstrun writes figure_image = home\figure-default.png
rem (2026-11-01: the shippable build uses the current 2D figure). Missing file just means
rem body.py falls back to drawing the blob, so this copy is allowed to fail quietly.
if exist figure-me-child-v23.png copy /Y figure-me-child-v23.png "%DIST%\figure-default.png" >> "%OUT%" 2>&1

rem plugins arrive from the author, so ship the folder empty
if not exist "%DIST%\plugins" mkdir "%DIST%\plugins"

rem never ship these two
if exist "%DIST%\license-key.txt" del /q "%DIST%\license-key.txt"
if exist "%DIST%\make-code.py" del /q "%DIST%\make-code.py"
if exist "%DIST%\license.key" del /q "%DIST%\license.key"

rem leave it looking like a fresh install (no test config, no test data)
call "%~dp0clean-dist.bat" >nul 2>&1

echo. >> "%OUT%"
echo ---- what is in %DIST% ---- >> "%OUT%"
dir /b "%DIST%" >> "%OUT%"

echo Built: %DIST%
echo Log: %OUT%
pause
