@echo off
rem Run the frozen exe once in self-test mode (no window, no pet).
rem Tells us: is the public key inside the package, does the code on disk check out,
rem and is the private key luckily absent.
rem Result -> dist\YuYu\data\license-selftest.txt
cd /d "%~dp0"
start "" /wait "dist\YuYu\YuYu.exe" --license-selftest
