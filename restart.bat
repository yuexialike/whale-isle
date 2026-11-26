@echo off
rem Compile first; only restart when it compiles clean.
rem NOTE: keep this file pure ASCII. cmd.exe reads .bat in the system codepage, so
rem UTF-8 Chinese comments here turn into garbage commands and the whole bat dies
rem (hit again 2026-11-04 18:33 -- run.bat had the same trap at 17:53).
cd /d "%~dp0"
"D:\fish\svc\venv\Scripts\python.exe" -m py_compile main.py shell.py chat.py memory.py llm.py tools.py gate.py body.py page.py tts.py ears.py hearing.py ask.py settings_page.py persona.py diag.py plug.py
if errorlevel 1 (
  echo ===== compile failed, see above =====
  pause
  exit /b 1
)
echo ===== compiled ok, restarting =====
call "%~dp0run.bat"
