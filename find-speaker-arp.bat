@echo off
rem 不靠 ping，靠 ARP 找音箱；顺便看网卡和绑源的 miIO 广播。结果写 data\net-arp.txt
cd /d "%~dp0"
"D:\fish\svc\venv\Scripts\python.exe" "%~dp0find-speaker-arp.py"
if errorlevel 1 pause
