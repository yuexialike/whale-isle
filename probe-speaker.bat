@echo off
rem 探一探局域网里的小米设备，结果写 data\speaker-probe.txt
cd /d "%~dp0"
"D:\fish\svc\venv\Scripts\python.exe" "%~dp0probe-speaker.py"
