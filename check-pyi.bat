@echo off
rem Read-only: is PyInstaller there, and which python is it in?
rem Result -> data\pyi.txt
cd /d "%~dp0"
set OUT=data\pyi.txt
"D:\fish\svc\venv\Scripts\python.exe" -c "import sys; print('python', sys.version.split()[0]); print('exe', sys.executable)" > "%OUT%" 2>&1
"D:\fish\svc\venv\Scripts\python.exe" -m PyInstaller --version >> "%OUT%" 2>&1
if errorlevel 1 echo NO-PYINSTALLER >> "%OUT%"
"D:\fish\svc\venv\Scripts\python.exe" -c "import PySide6; print('pyside6', PySide6.__version__)" >> "%OUT%" 2>&1
echo done >> "%OUT%"
