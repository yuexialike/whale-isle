@echo off
rem Start the web shell for the new house. Page: http://127.0.0.1:8900/
rem Keep this window open. Ctrl+C stops it.
cd /d "%~dp0"

rem Prefer pyfish.exe: plain python.exe gets killed by Defender behaviour monitoring.
if exist "D:\fish\webpet\rt\pyfish.exe" (
  set PYTHONHOME=C:\Users\user\AppData\Local\Programs\Python\Python312
  "D:\fish\webpet\rt\pyfish.exe" server.py
  goto done
)

"D:\fish\svc\venv\Scripts\python.exe" server.py

:done
if errorlevel 1 pause
