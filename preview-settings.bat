@echo off
rem Show the settings page and keep every word it says in data\settings-run.txt.
rem pythonw.exe silently dies on this box (Defender behaviour monitoring) and
rem pyfish.exe never showed a window, so this runs python.exe in the foreground.
cd /d "%~dp0"
set PY="D:\fish\svc\venv\Scripts\python.exe"
if not exist data mkdir data
echo ---- preview %DATE% %TIME% ---- > data\settings-run.txt
%PY% -m py_compile settings_page.py memory.py page.py main.py >> data\settings-run.txt 2>&1
if errorlevel 1 (
  echo ---- COMPILE FAILED ---- >> data\settings-run.txt
  type data\settings-run.txt
  pause
  exit /b 1
)
echo compile ok >> data\settings-run.txt
%PY% settings_page.py >> data\settings-run.txt 2>&1
echo ---- exited %ERRORLEVEL% ---- >> data\settings-run.txt
type data\settings-run.txt
